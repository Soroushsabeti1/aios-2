"""سرویس اطلاعیه مدیریت — پیام گروهی، Poll، اطلاع‌رسانی."""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.models.business import Person
from app.modules import roles


async def send_announcement(session: AsyncSession, tenant_id: int,
                              message: str, target_role: str = None,
                              is_official: bool = True) -> tuple[str, list[int]]:
    """
    ارسال اطلاعیه مدیریت.
    Returns: (preview_text, [telegram_ids])
    """
    q = select(Person).where(
        Person.tenant_id == tenant_id,
        Person.is_active == True,
        Person.telegram_id.isnot(None),
    )
    if target_role:
        q = q.where(Person.role == target_role)

    persons = (await session.scalars(q)).all()
    if not persons:
        return "⚠️ هیچ شخص متصلی پیدا نشد.", []

    header = "📢 اطلاعیه مدیریت\n\n" if is_official else ""
    full_msg = header + message

    telegram_ids = [p.telegram_id for p in persons if p.telegram_id]
    role_fa = roles.ROLE_LABELS.get(target_role, "همه") if target_role else "همه"

    preview = (f"پیام برای {len(telegram_ids)} نفر ({role_fa}):\n\n{full_msg}")
    return preview, telegram_ids


async def create_poll(session: AsyncSession, tenant_id: int,
                       question: str, options: list[str],
                       target_role: str = None,
                       is_anonymous: bool = False,
                       allows_multiple: bool = False) -> tuple[str, list[int], dict]:
    """
    ساخت نظرسنجی — شبیه‌سازی با پیام شماره‌دار.
    Returns: (poll_message, [telegram_ids], poll_data)
    """
    q = select(Person).where(
        Person.tenant_id == tenant_id,
        Person.is_active == True,
        Person.telegram_id.isnot(None),
    )
    if target_role:
        q = q.where(Person.role == target_role)

    persons = (await session.scalars(q)).all()
    telegram_ids = [p.telegram_id for p in persons if p.telegram_id]

    # پیام شماره‌دار
    options_text = "\n".join(f"{i+1}️⃣ {opt}" for i, opt in enumerate(options))
    poll_msg = (
        f"📊 نظرسنجی:\n\n"
        f"{question}\n\n"
        f"{options_text}\n\n"
        f"عدد مورد نظر رو بفرست."
    )

    poll_data = {
        "question": question,
        "options": options,
        "responses": {},
        "is_anonymous": is_anonymous,
    }

    return poll_msg, telegram_ids, poll_data


async def send_checklist(session: AsyncSession, tenant_id: int,
                          title: str, items: list[str],
                          target_role: str = None) -> tuple[str, list[int]]:
    """ارسال چک‌لیست شبیه‌سازی‌شده."""
    q = select(Person).where(
        Person.tenant_id == tenant_id,
        Person.is_active == True,
        Person.telegram_id.isnot(None),
    )
    if target_role:
        q = q.where(Person.role == target_role)

    persons = (await session.scalars(q)).all()
    telegram_ids = [p.telegram_id for p in persons if p.telegram_id]

    items_text = "\n".join(f"⬜ {item}" for item in items)
    msg = f"📋 {title}\n\n{items_text}\n\nوقتی هر مورد رو انجام دادی بگو."

    return msg, telegram_ids
