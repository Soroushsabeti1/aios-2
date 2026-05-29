"""
سرویس یادآور (Reminder).

کارفرما کارهایش را با زمان مشخص می‌گوید؛ سیستم سر موعد (و در صورت
درخواست، مدتی قبل از موعد) به او یادآوری می‌کند.

نکته‌ی زمان: AI زمان را به فرمت ISO تبدیل می‌کند و پاس می‌دهد
(مثلاً "2026-05-26T14:30"). این تابع آن را به‌عنوان وقت محلی ایران
تفسیر کرده و به UTC تبدیل می‌کند تا با background job هماهنگ باشد.
"""
from datetime import datetime, timezone, timedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.models.business import Reminder
from app.utils.id_generator import generate_display_id
from app.utils.jalali import to_jalali_str

# اختلاف وقت ایران با UTC (+3:30)
IRAN_OFFSET = timedelta(hours=3, minutes=30)


def _iran_now() -> datetime:
    """زمان فعلی به وقت ایران (به‌صورت naive برای نمایش)."""
    return datetime.now(timezone.utc) + IRAN_OFFSET


def _parse_iso_to_utc(iso_str: str) -> datetime | None:
    """
    رشته‌ی ISO (وقت محلی ایران) را به datetime با timezone=UTC تبدیل می‌کند.
    """
    if not iso_str:
        return None
    s = iso_str.strip().replace("/", "-")
    # حذف Z یا offset احتمالی
    s = s.replace("Z", "").split("+")[0].strip()
    formats = [
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
    ]
    for fmt in formats:
        try:
            naive = datetime.strptime(s, fmt)
            # تفسیر به‌عنوان وقت ایران → تبدیل به UTC
            return (naive - IRAN_OFFSET).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _fmt_iran(dt_utc: datetime) -> str:
    """datetime با UTC را به رشته‌ی خوانای فارسی (وقت ایران) تبدیل می‌کند."""
    if dt_utc.tzinfo is None:
        dt_utc = dt_utc.replace(tzinfo=timezone.utc)
    local = dt_utc + IRAN_OFFSET
    jdate = to_jalali_str(local.date())
    return f"{jdate} ساعت {local.hour:02d}:{local.minute:02d}"


async def add_reminder(session: AsyncSession, tenant_id: int, user_id: int,
                       title: str, due_at: str,
                       notify_before_minutes: int = 0,
                       note: str = None) -> str:
    """
    یک یادآور جدید ثبت می‌کند.
    due_at: زمان انجام کار به فرمت ISO (وقت ایران)
    notify_before_minutes: چند دقیقه قبل از موعد هشدار بده (۰ = فقط سر موعد)
    """
    due_utc = _parse_iso_to_utc(due_at)
    if due_utc is None:
        return "⚠️ زمان رو درست متوجه نشدم. می‌تونی واضح‌تر بگی؟ (مثلاً «فردا ساعت ۳ عصر»)"

    # اگر زمان در گذشته است
    if due_utc < datetime.now(timezone.utc):
        return "⚠️ این زمان گذشته! یه زمان توی آینده بگو."

    did = await generate_display_id(session, tenant_id, "reminders", Reminder)

    reminder = Reminder(
        tenant_id=tenant_id,
        user_telegram_id=user_id,
        display_id=did,
        title=title,
        due_at=due_utc,
        notify_before_minutes=notify_before_minutes or 0,
        note=note,
    )
    session.add(reminder)
    await session.commit()

    lines = [f"⏰ یادآور ثبت شد ({did}):"]
    lines.append(f"📌 {title}")
    lines.append(f"🗓 {_fmt_iran(due_utc)}")
    if notify_before_minutes:
        lines.append(f"🔔 {notify_before_minutes} دقیقه قبلش هم بهت خبر می‌دم")
    return "\n".join(lines)


async def list_reminders(session: AsyncSession, tenant_id: int, user_id: int,
                         period: str = "all") -> str:
    """
    لیست یادآورها.
    period: today (امروز) / tomorrow (فردا) / week (هفته) / all (همه فعال)
    """
    now_utc = datetime.now(timezone.utc)
    q = select(Reminder).where(
        Reminder.tenant_id == tenant_id,
        Reminder.user_telegram_id == user_id,
        Reminder.is_done == False,
    )

    iran_now = _iran_now()
    if period == "today":
        start = iran_now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
        label = "امروز"
    elif period == "tomorrow":
        start = (iran_now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
        label = "فردا"
    elif period == "week":
        start = iran_now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=7)
        label = "این هفته"
    else:
        start = end = None
        label = "فعال"

    if start is not None:
        start_utc = (start - IRAN_OFFSET).replace(tzinfo=timezone.utc)
        end_utc = (end - IRAN_OFFSET).replace(tzinfo=timezone.utc)
        q = q.where(Reminder.due_at >= start_utc, Reminder.due_at < end_utc)

    q = q.order_by(Reminder.due_at.asc())
    reminders = (await session.scalars(q)).all()

    if not reminders:
        return f"📋 کاری برای {label} ثبت نشده."

    lines = [f"⏰ یادآورهای {label} ({len(reminders)} مورد):"]
    for r in reminders:
        lines.append(f"• [{r.display_id}] {r.title}")
        lines.append(f"   🗓 {_fmt_iran(r.due_at)}")
    return "\n".join(lines)


async def complete_reminder(session: AsyncSession, tenant_id: int, user_id: int,
                            reminder_display_id: str) -> str:
    """یک یادآور را انجام‌شده علامت می‌زند."""
    reminder = await session.scalar(
        select(Reminder).where(
            Reminder.tenant_id == tenant_id,
            Reminder.user_telegram_id == user_id,
            Reminder.display_id == reminder_display_id,
        )
    )
    if not reminder:
        return f"⚠️ یادآور {reminder_display_id} پیدا نشد."
    reminder.is_done = True
    await session.commit()
    return f"✅ یادآور «{reminder.title}» انجام‌شده علامت خورد."


async def delete_reminder(session: AsyncSession, tenant_id: int, user_id: int,
                          reminder_display_id: str) -> str:
    """یک یادآور را حذف می‌کند."""
    reminder = await session.scalar(
        select(Reminder).where(
            Reminder.tenant_id == tenant_id,
            Reminder.user_telegram_id == user_id,
            Reminder.display_id == reminder_display_id,
        )
    )
    if not reminder:
        return f"⚠️ یادآور {reminder_display_id} پیدا نشد."
    title = reminder.title
    await session.delete(reminder)
    await session.commit()
    return f"🗑 یادآور «{title}» حذف شد."


async def get_due_reminders(session: AsyncSession):
    """
    یادآورهایی که باید همین حالا هشدارشان فرستاده شود را برمی‌گرداند.
    برای background job استفاده می‌شود.
    خروجی: لیستی از (reminder, نوع_هشدار) — نوع: "pre" یا "due"
    """
    now_utc = datetime.now(timezone.utc)
    results = []

    active = (await session.scalars(
        select(Reminder).where(
            Reminder.is_done == False,
            Reminder.due_notified == False,
        )
    )).all()

    for r in active:
        due = r.due_at
        if due.tzinfo is None:
            due = due.replace(tzinfo=timezone.utc)

        # هشدار قبل از موعد
        if r.notify_before_minutes and not r.pre_notified:
            pre_time = due - timedelta(minutes=r.notify_before_minutes)
            if now_utc >= pre_time and now_utc < due:
                results.append((r, "pre"))
                continue

        # هشدار سر موعد
        if now_utc >= due:
            results.append((r, "due"))

    return results


def format_reminder_alert(reminder: Reminder, alert_type: str) -> str:
    """متن هشدار یادآور را می‌سازد."""
    if alert_type == "pre":
        return (f"🔔 یادآوری زودهنگام:\n"
                f"📌 {reminder.title}\n"
                f"🗓 سر ساعت {_fmt_iran(reminder.due_at)} باید انجام بشه "
                f"({reminder.notify_before_minutes} دقیقه دیگه)")
    else:
        return (f"⏰ الان وقتشه!\n"
                f"📌 {reminder.title}\n"
                f"🗓 {_fmt_iran(reminder.due_at)}")
