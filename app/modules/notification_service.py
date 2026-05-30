"""
سرویس اطلاع‌رسانی هوشمند — فقط موضوعات مهم به کارفرما.
"""
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.models.business import Person, TenantSettings
from app.database.models.tenant import Tenant


# کلمات کلیدی مهم
IMPORTANT_KEYWORDS = [
    "مشکل", "خطا", "اشتباه", "فوری", "اورژانس", "نمیشه", "نمیتونم",
    "کمک", "استعفا", "قطع", "بحران", "ضرر", "بدهی", "شکایت",
    "urgent", "error", "problem", "critical",
]


def is_important(text: str) -> bool:
    """آیا این پیام مهمه و باید به کارفرما گزارش بشه؟"""
    if not text:
        return False
    text_lower = text.lower()
    return any(kw in text_lower for kw in IMPORTANT_KEYWORDS)


async def notify_owner_member_joined(bot, session: AsyncSession,
                                      tenant_id: int, person: Person):
    """اطلاع‌رسانی به کارفرما وقتی کسی وصل میشه."""
    tenant = await session.get(Tenant, tenant_id)
    if not tenant:
        return

    role_fa = {
        "employee": "کارمند",
        "customer": "مشتری",
        "collaborator": "همکار",
        "partner": "پارتنر",
    }.get(person.role, person.role)

    if person.role == "employee":
        msg = f"✅ {role_fa} «{person.full_name}» به سیستم وصل شد."
    elif person.role == "collaborator":
        msg = f"🤝 همکار «{person.full_name}» به سیستم وصل شد."
    else:
        # مشتریان → انباشته میشن، هر ساعت گزارش
        return

    try:
        await bot.send_message(chat_id=tenant.owner_telegram_id, text=msg)
    except Exception:
        pass


async def maybe_notify_owner_message(bot, session: AsyncSession,
                                      tenant_id: int, sender: Person,
                                      message_text: str):
    """
    اگه پیام مهم بود به کارفرما خبر بده.
    اولین بار سطح دسترسی پیشنهاد بشه.
    """
    if not is_important(message_text):
        return

    tenant = await session.get(Tenant, tenant_id)
    if not tenant:
        return

    ts = await session.scalar(
        select(TenantSettings).where(TenantSettings.tenant_id == tenant_id)
    )

    role_fa = {
        "employee": "کارمند",
        "customer": "مشتری",
        "collaborator": "همکار",
    }.get(sender.role, sender.role)

    msg = (
        f"⚠️ پیام مهم از {role_fa} «{sender.full_name}»:\n\n"
        f"{message_text[:200]}"
    )

    # اولین بار → پیشنهاد سطح دسترسی
    autonomy = {}
    if ts and ts.autonomy_rules:
        import json
        try:
            autonomy = json.loads(ts.autonomy_rules)
        except Exception:
            pass

    key = f"notify_{sender.role}_messages"
    if key not in autonomy:
        msg += (
            f"\n\n---\n"
            f"دفعه بعد هم خبرت بدم وقتی {role_fa} پیام مهم داره؟\n"
            f"یا فقط موارد فوری؟"
        )

    try:
        await bot.send_message(chat_id=tenant.owner_telegram_id, text=msg)
    except Exception:
        pass


async def hourly_customer_report(bot, session: AsyncSession, tenant_id: int,
                                  new_customers: list[Person]):
    """هر ساعت مجموع مشتریان جدید به کارفرما."""
    if not new_customers:
        return

    tenant = await session.get(Tenant, tenant_id)
    if not tenant:
        return

    names = "، ".join(c.full_name for c in new_customers[:5])
    extra = f" و {len(new_customers) - 5} نفر دیگه" if len(new_customers) > 5 else ""
    msg = f"👥 {len(new_customers)} مشتری جدید وصل شدن:\n{names}{extra}"

    try:
        await bot.send_message(chat_id=tenant.owner_telegram_id, text=msg)
    except Exception:
        pass
