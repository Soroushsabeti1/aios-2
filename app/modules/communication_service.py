"""
سرویس ارتباطات — ذخیره‌ی گفت‌وگوی مشتری/کارمند، گزارش، پیام گروهی.

این سرویس قلب «سیستم ارتباطی» است:
  - هر پیام مشتری/کارمند ذخیره می‌شود
  - فوری‌ها فوراً به کارفرما می‌رسند
  - کارفرما گزارش دوره‌ای می‌گیرد
  - کارفرما پیام گروهی می‌فرستد و جواب‌ها جمع‌آوری می‌شوند
"""
from datetime import datetime, timezone, timedelta
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.models.business import (
    ContactMessage, Broadcast, BroadcastTarget, ReportSchedule, Person,
)
from app.modules import roles


# ─────────────────────────────────────────────
# ذخیره‌ی پیام مشتری/کارمند
# ─────────────────────────────────────────────

async def save_contact_message(session: AsyncSession, tenant_id: int,
                                person: Person, message_text: str,
                                bot_reply: str = None,
                                is_urgent: bool = False) -> ContactMessage:
    """یک پیام از مشتری/کارمند را ذخیره می‌کند."""
    msg = ContactMessage(
        tenant_id=tenant_id,
        person_id=person.id,
        sender_name=person.full_name,
        sender_role=person.role,
        sender_telegram_id=person.telegram_id,
        message_text=message_text,
        bot_reply=bot_reply,
        is_urgent=is_urgent,
    )
    session.add(msg)
    await session.commit()
    return msg


# ─────────────────────────────────────────────
# تشخیص فوریت
# ─────────────────────────────────────────────

# کلمات صریح فوریت
_URGENT_KEYWORDS = [
    "فوری", "فوریه", "اورژانس", "اورژانسی", "سریع", "همین الان",
    "عجله", "عاجل", "ضروری", "زود", "بحرانی", "مهمه خیلی",
]


def detect_explicit_urgency(text: str) -> bool:
    """آیا کاربر صراحتاً گفته فوری است؟"""
    if not text:
        return False
    return any(kw in text for kw in _URGENT_KEYWORDS)


async def notify_owner_urgent(bot, session: AsyncSession, tenant_id: int,
                              contact_msg: ContactMessage):
    """یک پیام فوری را بلافاصله به کارفرما اطلاع می‌دهد."""
    from app.database.models.tenant import Tenant
    tenant = await session.get(Tenant, tenant_id)
    if not tenant:
        return

    role_fa = roles.ROLE_LABELS.get(contact_msg.sender_role, contact_msg.sender_role)
    text = (
        f"🚨 پیام فوری از {role_fa} «{contact_msg.sender_name}»:\n\n"
        f"«{contact_msg.message_text}»\n\n"
        f"لطفاً سریع رسیدگی کن."
    )
    try:
        await bot.send_message(chat_id=tenant.owner_telegram_id, text=text)
        contact_msg.urgent_notified = True
        await session.commit()
    except Exception:
        pass


# ─────────────────────────────────────────────
# گزارش گفت‌وگوها برای کارفرما
# ─────────────────────────────────────────────

async def get_contact_summary(session: AsyncSession, tenant_id: int,
                               role_filter: str = None,
                               hours: int = None,
                               person_name: str = None) -> str:
    """
    خلاصه‌ی گفت‌وگوهای مشتری/کارمند برای کارفرما.
    role_filter: customer / employee — فیلتر نقش
    hours: فقط پیام‌های N ساعت اخیر
    person_name: فقط یک شخص خاص
    """
    q = select(ContactMessage).where(ContactMessage.tenant_id == tenant_id)
    if role_filter:
        q = q.where(ContactMessage.sender_role == role_filter)
    if person_name:
        q = q.where(ContactMessage.sender_name.ilike(f"%{person_name}%"))
    if hours:
        since = datetime.now(timezone.utc) - timedelta(hours=hours)
        q = q.where(ContactMessage.created_at >= since)
    q = q.order_by(ContactMessage.created_at.desc()).limit(40)

    messages = (await session.scalars(q)).all()
    if not messages:
        return "گفت‌وگویی ثبت نشده."

    # گروه‌بندی بر اساس فرستنده
    by_sender = {}
    for m in messages:
        by_sender.setdefault(m.sender_name, []).append(m)

    lines = [f"💬 خلاصه‌ی گفت‌وگوها ({len(messages)} پیام):"]
    for sender, msgs in by_sender.items():
        role_fa = roles.ROLE_LABELS.get(msgs[0].sender_role, msgs[0].sender_role)
        lines.append(f"\n👤 {sender} ({role_fa}) — {len(msgs)} پیام:")
        for m in msgs[:5]:
            urgent_mark = "🚨 " if m.is_urgent else ""
            lines.append(f"  {urgent_mark}• {m.message_text[:120]}")
    return "\n".join(lines)


async def get_unreported_messages(session: AsyncSession, tenant_id: int) -> list:
    """پیام‌هایی که هنوز در گزارش دوره‌ای نیامده‌اند."""
    return (await session.scalars(
        select(ContactMessage).where(
            ContactMessage.tenant_id == tenant_id,
            ContactMessage.reported == False,
        ).order_by(ContactMessage.created_at.asc())
    )).all()


async def mark_messages_reported(session: AsyncSession, messages: list):
    """پیام‌ها را به‌عنوان «گزارش‌شده» علامت می‌زند."""
    for m in messages:
        m.reported = True
    await session.commit()


# ─────────────────────────────────────────────
# تنظیمات گزارش دوره‌ای
# ─────────────────────────────────────────────

async def set_report_schedule(session: AsyncSession, tenant_id: int,
                               interval_hours: int) -> str:
    """تنظیم فاصله‌ی گزارش دوره‌ای."""
    if interval_hours < 1:
        return "⚠️ فاصله‌ی گزارش باید حداقل ۱ ساعت باشه."

    sched = await session.scalar(
        select(ReportSchedule).where(ReportSchedule.tenant_id == tenant_id)
    )
    if not sched:
        sched = ReportSchedule(tenant_id=tenant_id)
        session.add(sched)
    sched.interval_hours = interval_hours
    sched.is_enabled = True
    await session.commit()

    if interval_hours < 24:
        desc = f"هر {interval_hours} ساعت"
    else:
        days = interval_hours // 24
        desc = f"هر {days} روز"
    return f"✅ از این به بعد {desc} خلاصه‌ی گفت‌وگوهای مشتری‌ها و کارمندها رو برات می‌فرستم."


async def disable_report_schedule(session: AsyncSession, tenant_id: int) -> str:
    """غیرفعال کردن گزارش دوره‌ای."""
    sched = await session.scalar(
        select(ReportSchedule).where(ReportSchedule.tenant_id == tenant_id)
    )
    if sched:
        sched.is_enabled = False
        await session.commit()
    return "🔕 گزارش دوره‌ای خاموش شد."


# ─────────────────────────────────────────────
# پیام گروهی (Broadcast)
# ─────────────────────────────────────────────

async def create_broadcast(session: AsyncSession, tenant_id: int,
                            message_text: str, role_filter: str = None,
                            person_names: list = None,
                            expects_reply: bool = False) -> tuple[Broadcast, list]:
    """
    یک مأموریت پیام گروهی می‌سازد.
    role_filter: به همه‌ی یک نقش (مثلاً همه‌ی کارمندها)
    person_names: به اشخاص خاص
    خروجی: (broadcast, لیست targetها)
    """
    # پیدا کردن گیرنده‌ها — فقط اشخاص متصل
    q = select(Person).where(
        Person.tenant_id == tenant_id,
        Person.telegram_id.isnot(None),
        Person.is_active == True,
    )
    if role_filter:
        q = q.where(Person.role == role_filter)
    targets_persons = (await session.scalars(q)).all()

    if person_names:
        # فیلتر بر اساس نام
        targets_persons = [
            p for p in targets_persons
            if any(n.strip() in p.full_name for n in person_names)
        ]

    if not targets_persons:
        return None, []

    # شناسه‌ی نمایشی
    count = await session.scalar(
        select(func.count(Broadcast.id)).where(Broadcast.tenant_id == tenant_id)
    ) or 0

    broadcast = Broadcast(
        tenant_id=tenant_id,
        display_id=f"BRD-{count + 1:04d}",
        message_text=message_text,
        expects_reply=expects_reply,
    )
    session.add(broadcast)
    await session.flush()

    targets = []
    for p in targets_persons:
        t = BroadcastTarget(
            broadcast_id=broadcast.id,
            tenant_id=tenant_id,
            person_id=p.id,
            person_name=p.full_name,
            person_telegram_id=p.telegram_id,
        )
        session.add(t)
        targets.append(t)

    await session.commit()
    return broadcast, targets


async def record_broadcast_reply(session: AsyncSession, tenant_id: int,
                                  telegram_id: int, reply_text: str) -> bool:
    """
    اگر این شخص عضو یک broadcast فعالِ منتظر جواب است،
    پیامش را به‌عنوان جواب ثبت می‌کند.
    خروجی: True اگر این پیام جواب یک broadcast بود.
    """
    # دنبال targetـی بگرد که هنوز جواب نداده و broadcastـش منتظر جواب است
    target = await session.scalar(
        select(BroadcastTarget).join(Broadcast).where(
            BroadcastTarget.tenant_id == tenant_id,
            BroadcastTarget.person_telegram_id == telegram_id,
            BroadcastTarget.reply_text.is_(None),
            Broadcast.expects_reply == True,
            Broadcast.status == "active",
        ).order_by(BroadcastTarget.id.desc()).limit(1)
    )
    if not target:
        return False

    target.reply_text = reply_text
    target.replied_at = datetime.now(timezone.utc)
    await session.commit()

    # بررسی: آیا همه جواب دادند؟
    broadcast = await session.get(Broadcast, target.broadcast_id)
    remaining = await session.scalar(
        select(func.count(BroadcastTarget.id)).where(
            BroadcastTarget.broadcast_id == broadcast.id,
            BroadcastTarget.reply_text.is_(None),
        )
    ) or 0
    if remaining == 0:
        broadcast.status = "done"
        await session.commit()

    return True


async def get_broadcast_status(session: AsyncSession, tenant_id: int,
                               broadcast_display_id: str = None) -> str:
    """گزارش وضعیت یک مأموریت پیام گروهی (جواب‌ها)."""
    if broadcast_display_id:
        broadcast = await session.scalar(
            select(Broadcast).where(
                Broadcast.tenant_id == tenant_id,
                Broadcast.display_id == broadcast_display_id,
            )
        )
    else:
        # آخرین broadcast
        broadcast = await session.scalar(
            select(Broadcast).where(
                Broadcast.tenant_id == tenant_id,
            ).order_by(Broadcast.id.desc()).limit(1)
        )

    if not broadcast:
        return "هیچ پیام گروهی‌ای ثبت نشده."

    targets = (await session.scalars(
        select(BroadcastTarget).where(
            BroadcastTarget.broadcast_id == broadcast.id
        )
    )).all()

    replied = [t for t in targets if t.reply_text]
    pending = [t for t in targets if not t.reply_text]

    lines = [f"📢 پیام گروهی {broadcast.display_id}:"]
    lines.append(f"📝 «{broadcast.message_text}»")
    lines.append(f"👥 {len(replied)} از {len(targets)} نفر جواب دادن.")

    if replied:
        lines.append("\n✅ جواب‌ها:")
        for t in replied:
            lines.append(f"  • {t.person_name}: {t.reply_text}")
    if pending:
        lines.append("\n⏳ هنوز جواب نداده‌ن:")
        lines.append("  " + "، ".join(t.person_name for t in pending))

    return "\n".join(lines)
