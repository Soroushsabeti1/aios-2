"""
سرویس ذخیره و دریافت عکس برای موجودیت‌ها (مشتری / کالا / کارمند).
عکس‌ها به‌صورت binary در دیتابیس ذخیره می‌شوند.

نسخه ۲: جستجوی انعطاف‌پذیر نام (اگر نام دقیق پیدا نشد، جستجوی شبیه).
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.models.business import Customer, Product, Employee

# نگاشت نوع موجودیت به مدل
_ENTITY_MODELS = {
    "customer": (Customer, "مشتری"),
    "product": (Product, "کالا"),
    "employee": (Employee, "کارمند"),
}


async def _find_entity(session, model, tenant_id, name):
    """پیدا کردن موجودیت — اول دقیق، بعد انعطاف‌پذیر."""
    # تلاش ۱: تطابق دقیق
    obj = await session.scalar(
        select(model).where(model.tenant_id == tenant_id, model.name == name)
    )
    if obj:
        return obj
    # تلاش ۲: تطابق انعطاف‌پذیر (شامل بودن)
    name_clean = (name or "").strip()
    obj = await session.scalar(
        select(model).where(
            model.tenant_id == tenant_id,
            model.name.ilike(f"%{name_clean}%"),
        ).limit(1)
    )
    return obj


async def save_entity_photo(session: AsyncSession, tenant_id: int,
                            entity_type: str, entity_name: str,
                            photo_data: bytes, photo_mime: str = "image/jpeg") -> str:
    """عکس را برای یک موجودیت ذخیره می‌کند."""
    pair = _ENTITY_MODELS.get(entity_type)
    if not pair:
        return f"⚠️ نوع «{entity_type}» پشتیبانی نمی‌شود."
    model, label = pair

    if not photo_data:
        return "⚠️ عکسی برای ذخیره دریافت نشد. دوباره عکس رو بفرست."

    obj = await _find_entity(session, model, tenant_id, entity_name)
    if not obj:
        return f"⚠️ {label} «{entity_name}» پیدا نشد. اول باید ثبتش کنی."

    try:
        obj.photo = photo_data
        obj.photo_mime = photo_mime
        await session.commit()
    except Exception as e:
        await session.rollback()
        return f"⚠️ ذخیره‌ی عکس با مشکل مواجه شد. ({type(e).__name__})"

    return f"✅ عکس برای {label} «{obj.name}» ({obj.display_id}) ذخیره شد."


async def get_entity_photo(session: AsyncSession, tenant_id: int,
                           entity_type: str, entity_name: str):
    """
    عکس یک موجودیت را برمی‌گرداند.
    خروجی: (photo_bytes, mime, خطا)
    """
    pair = _ENTITY_MODELS.get(entity_type)
    if not pair:
        return None, None, f"نوع «{entity_type}» پشتیبانی نمی‌شود."
    model, label = pair

    obj = await _find_entity(session, model, tenant_id, entity_name)
    if not obj:
        return None, None, f"{label} «{entity_name}» پیدا نشد."
    if not obj.photo:
        return None, None, f"{label} «{obj.name}» عکسی نداره."

    return obj.photo, obj.photo_mime or "image/jpeg", None
