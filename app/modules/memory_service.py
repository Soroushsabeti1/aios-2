"""
سرویس حافظه — ذخیره کامل چت‌ها، فایل‌ها، و نخ ارتباطی بین نقش‌ها.
"""
import json
from datetime import datetime, timezone
from sqlalchemy import select, desc, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.models.business import (
    ConversationMessage, SharedContext, FileRecord, Person
)


# ═══════════════════════════════════════
# ذخیره پیام‌ها
# ═══════════════════════════════════════

async def save_message(session: AsyncSession, tenant_id: int,
                       user_telegram_id: int, role: str,
                       content: str, raw_json: dict = None,
                       context_thread_id: int = None):
    """ذخیره یک پیام در حافظه دائمی."""
    msg = ConversationMessage(
        tenant_id=tenant_id,
        user_telegram_id=user_telegram_id,
        role=role,
        content=content,
        raw_json=json.dumps(raw_json, ensure_ascii=False) if raw_json else None,
        context_thread_id=context_thread_id,
    )
    session.add(msg)
    await session.commit()
    return msg


async def get_recent_messages(session: AsyncSession, tenant_id: int,
                               user_telegram_id: int,
                               limit: int = 50) -> list[dict]:
    """دریافت پیام‌های اخیر یک کاربر."""
    msgs = (await session.scalars(
        select(ConversationMessage)
        .where(
            ConversationMessage.tenant_id == tenant_id,
            ConversationMessage.user_telegram_id == user_telegram_id,
        )
        .order_by(desc(ConversationMessage.id))
        .limit(limit)
    )).all()

    result = []
    for msg in reversed(msgs):
        if msg.raw_json:
            try:
                result.append(json.loads(msg.raw_json))
                continue
            except Exception:
                pass
        if msg.content:
            result.append({"role": msg.role, "content": msg.content})
    return result


async def search_messages(session: AsyncSession, tenant_id: int,
                           query: str, user_telegram_id: int = None,
                           limit: int = 20) -> list[dict]:
    """جستجو در همه پیام‌های tenant."""
    q = select(ConversationMessage).where(
        ConversationMessage.tenant_id == tenant_id,
        ConversationMessage.content.ilike(f"%{query}%"),
    )
    if user_telegram_id:
        q = q.where(ConversationMessage.user_telegram_id == user_telegram_id)
    q = q.order_by(desc(ConversationMessage.created_at)).limit(limit)

    msgs = (await session.scalars(q)).all()
    results = []
    for msg in msgs:
        # پیدا کردن نام شخص
        person = await session.scalar(
            select(Person).where(Person.telegram_id == msg.user_telegram_id)
        )
        name = person.full_name if person else f"کاربر {msg.user_telegram_id}"
        results.append({
            "id": msg.id,
            "from": name,
            "role": msg.role,
            "content": msg.content or "",
            "date": msg.created_at.strftime("%Y-%m-%d %H:%M") if msg.created_at else "",
            "thread_id": msg.context_thread_id,
        })
    return results


# ═══════════════════════════════════════
# SharedContext — نخ ارتباطی
# ═══════════════════════════════════════

async def get_or_create_thread(session: AsyncSession, tenant_id: int,
                                topic: str, topic_type: str = None,
                                topic_ref_id: int = None) -> SharedContext:
    """پیدا کردن یا ساختن thread برای یه موضوع."""
    # جستجو در threadهای موجود
    existing = await session.scalar(
        select(SharedContext).where(
            SharedContext.tenant_id == tenant_id,
            SharedContext.topic.ilike(f"%{topic}%"),
            SharedContext.is_resolved == False,
        ).limit(1)
    )
    if existing:
        return existing

    ctx = SharedContext(
        tenant_id=tenant_id,
        topic=topic,
        topic_type=topic_type,
        topic_ref_id=topic_ref_id,
    )
    session.add(ctx)
    await session.commit()
    return ctx


async def get_thread_messages(session: AsyncSession, thread_id: int,
                               limit: int = 100) -> list[dict]:
    """همه پیام‌های یه thread از همه نقش‌ها."""
    msgs = (await session.scalars(
        select(ConversationMessage)
        .where(ConversationMessage.context_thread_id == thread_id)
        .order_by(ConversationMessage.created_at)
        .limit(limit)
    )).all()

    results = []
    for msg in msgs:
        person = await session.scalar(
            select(Person).where(Person.telegram_id == msg.user_telegram_id)
        )
        name = person.full_name if person else "سیستم"
        role = person.role if person else msg.role
        results.append({
            "from": name,
            "role": role,
            "content": msg.content or "",
            "date": msg.created_at.strftime("%Y-%m-%d %H:%M") if msg.created_at else "",
        })
    return results


async def get_thread_summary(session: AsyncSession, tenant_id: int,
                              topic: str) -> str:
    """خلاصه وضعیت یه موضوع از همه نقش‌ها."""
    thread = await session.scalar(
        select(SharedContext).where(
            SharedContext.tenant_id == tenant_id,
            SharedContext.topic.ilike(f"%{topic}%"),
        ).order_by(desc(SharedContext.updated_at)).limit(1)
    )
    if not thread:
        return f"هیچ سابقه‌ای از «{topic}» پیدا نشد."

    msgs = await get_thread_messages(session, thread.id, limit=50)
    if not msgs:
        return f"thread برای «{topic}» وجود داره ولی پیامی نداره."

    lines = [f"📋 سابقه «{thread.topic}»:\n"]
    for m in msgs[-10:]:  # ۱۰ پیام آخر
        lines.append(f"[{m['date']}] {m['from']}: {m['content'][:100]}")

    if thread.summary:
        lines.insert(1, f"خلاصه: {thread.summary}\n")

    return "\n".join(lines)


# ═══════════════════════════════════════
# FileRecord — ثبت فایل‌ها
# ═══════════════════════════════════════

async def save_file_record(session: AsyncSession, tenant_id: int,
                            sender_telegram_id: int, sender_role: str,
                            file_type: str, file_id: str = None,
                            file_name: str = None, caption: str = None,
                            receiver_telegram_id: int = None,
                            receiver_role: str = None,
                            context_thread_id: int = None) -> FileRecord:
    """ثبت یک فایل در حافظه."""
    rec = FileRecord(
        tenant_id=tenant_id,
        sender_telegram_id=sender_telegram_id,
        sender_role=sender_role,
        receiver_telegram_id=receiver_telegram_id,
        receiver_role=receiver_role,
        file_type=file_type,
        file_id=file_id,
        file_name=file_name,
        caption=caption,
        context_thread_id=context_thread_id,
    )
    session.add(rec)
    await session.commit()
    return rec


async def search_files(session: AsyncSession, tenant_id: int,
                        query: str = None,
                        sender_telegram_id: int = None,
                        file_type: str = None,
                        limit: int = 10) -> list[dict]:
    """جستجوی فایل‌های ارسال‌شده."""
    q = select(FileRecord).where(FileRecord.tenant_id == tenant_id)
    if sender_telegram_id:
        q = q.where(FileRecord.sender_telegram_id == sender_telegram_id)
    if file_type:
        q = q.where(FileRecord.file_type == file_type)
    if query:
        q = q.where(
            FileRecord.file_name.ilike(f"%{query}%") |
            FileRecord.caption.ilike(f"%{query}%")
        )
    q = q.order_by(desc(FileRecord.created_at)).limit(limit)

    records = (await session.scalars(q)).all()
    results = []
    for r in records:
        sender = await session.scalar(
            select(Person).where(Person.telegram_id == r.sender_telegram_id)
        )
        results.append({
            "id": r.id,
            "file_id": r.file_id,
            "file_type": r.file_type,
            "file_name": r.file_name or "",
            "caption": r.caption or "",
            "from": sender.full_name if sender else "ناشناس",
            "date": r.created_at.strftime("%Y-%m-%d %H:%M") if r.created_at else "",
        })
    return results


async def get_last_file(session: AsyncSession, tenant_id: int,
                         sender_telegram_id: int = None) -> dict | None:
    """آخرین فایل ارسال‌شده."""
    results = await search_files(session, tenant_id,
                                  sender_telegram_id=sender_telegram_id,
                                  limit=1)
    return results[0] if results else None
