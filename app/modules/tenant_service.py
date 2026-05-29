"""
سرویس مدیریت کارفرما (Tenant) — نسخه ۲.
کنترل دسترسی + اشتراک + آپدیت اطلاعات + لوگو + display_id.
"""
from datetime import timedelta
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.models.tenant import Tenant, TenantUser, SubscriptionStatus, utcnow
from app.core.config import settings
from app.utils.normalizer import format_amount


async def get_tenant_for_user(session: AsyncSession, telegram_id: int) -> Tenant | None:
    user = await session.scalar(
        select(TenantUser).where(
            TenantUser.telegram_id == telegram_id,
            TenantUser.is_active == True,
        )
    )
    if not user:
        return None
    return await session.get(Tenant, user.tenant_id)


async def create_tenant(session: AsyncSession, owner_telegram_id: int,
                        business_name: str) -> Tenant:
    # ساخت display_id
    count = await session.scalar(select(func.count(Tenant.id))) or 0
    display_id = f"BIZ-{count + 1:04d}"

    # trial_ends_at = None → منتظر تأیید ادمین
    tenant = Tenant(
        name=business_name,
        display_id=display_id,
        owner_telegram_id=owner_telegram_id,
        subscription_status=SubscriptionStatus.TRIAL,
        trial_ends_at=None,  # ادمین باید تأیید کند
    )
    session.add(tenant)
    await session.flush()

    owner = TenantUser(
        tenant_id=tenant.id,
        telegram_id=owner_telegram_id,
        role="owner",
    )
    session.add(owner)
    await session.commit()
    return tenant


async def check_access(session: AsyncSession, telegram_id: int) -> tuple[bool, str, Tenant | None]:
    tenant = await get_tenant_for_user(session, telegram_id)
    if not tenant:
        return False, "no_tenant", None
    # trial بدون تاریخ = منتظر تأیید ادمین
    if tenant.subscription_status == SubscriptionStatus.TRIAL and tenant.trial_ends_at is None:
        return False, "pending_approval", tenant
    if not tenant.is_active:
        return False, "expired", tenant
    return True, "ok", tenant


async def update_tenant_info(session: AsyncSession, tenant_id: int, **kwargs) -> str:
    """آپدیت اطلاعات کارفرما."""
    tenant = await session.get(Tenant, tenant_id)
    if not tenant:
        return "❌ کارفرما پیدا نشد."

    updated = []
    field_labels = {
        "name": "نام فروشگاه", "phone": "تلفن", "address": "آدرس",
        "city": "شهر", "province": "استان",
        "card_number": "شماره کارت", "sheba": "شبا",
        "account_holder": "صاحب حساب",
        "default_tax_percent": "درصد مالیات",
    }

    for key, value in kwargs.items():
        if value is not None and hasattr(tenant, key) and key not in ("logo", "logo_mime"):
            setattr(tenant, key, value)
            label = field_labels.get(key, key)
            updated.append(f"• {label}: {value}")

    await session.commit()

    if updated:
        return "✅ اطلاعات فروشگاه آپدیت شد:\n" + "\n".join(updated)
    return "تغییری ثبت نشد."


async def save_tenant_logo(session: AsyncSession, tenant_id: int,
                           logo_data: bytes, mime_type: str) -> str:
    """ذخیره لوگو در دیتابیس."""
    tenant = await session.get(Tenant, tenant_id)
    if not tenant:
        return "❌ کارفرما پیدا نشد."
    tenant.logo = logo_data
    tenant.logo_mime = mime_type
    await session.commit()
    return "✅ لوگوی فروشگاه ذخیره شد!"


async def get_tenant_info(session: AsyncSession, tenant_id: int) -> str:
    """نمایش اطلاعات کامل کارفرما."""
    tenant = await session.get(Tenant, tenant_id)
    if not tenant:
        return "❌ کارفرما پیدا نشد."

    lines = [f"🏢 {tenant.name} ({tenant.display_id or '—'})"]
    if tenant.phone:
        lines.append(f"📞 تلفن: {tenant.phone}")
    if tenant.address:
        lines.append(f"📍 آدرس: {tenant.address}")
    if tenant.city:
        lines.append(f"🌆 شهر: {tenant.city}" + (f" ({tenant.province})" if tenant.province else ""))
    if tenant.card_number:
        lines.append(f"💳 کارت: {tenant.card_number}")
    if tenant.sheba:
        lines.append(f"🏦 شبا: {tenant.sheba}")
    if tenant.account_holder:
        lines.append(f"👤 صاحب حساب: {tenant.account_holder}")
    lines.append(f"💹 مالیات پیش‌فرض: {tenant.default_tax_percent}٪")
    lines.append(f"🖼 لوگو: {'دارد ✅' if tenant.logo else 'ندارد ❌ (لوگو رو به من عکسش رو بفرست)'}")
    lines.append(f"📋 وضعیت: {tenant.subscription_status.value}")
    return "\n".join(lines)
