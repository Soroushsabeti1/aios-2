"""
تولید آیدی پیشونددار خودکار: CUS-0001, EMP-0001, PRD-0001, INV-0001
"""
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

_PREFIXES = {
    "customers": "CUS",
    "products": "PRD",
    "employees": "EMP",
    "invoices": "INV",
    "reminders": "REM",
}


async def generate_display_id(session: AsyncSession, tenant_id: int, table_name: str, model_class) -> str:
    """
    آیدی بعدی را بر اساس بیشترین شماره موجود تولید می‌کند.
    مثال: CUS-0001, CUS-0002, ...
    """
    prefix = _PREFIXES.get(table_name, "ID")

    last = await session.scalar(
        select(model_class.display_id)
        .where(
            model_class.tenant_id == tenant_id,
            model_class.display_id.isnot(None),
        )
        .order_by(model_class.id.desc())
        .limit(1)
    )

    if last and "-" in last:
        try:
            num = int(last.split("-")[1]) + 1
        except (ValueError, IndexError):
            num = 1
    else:
        count = await session.scalar(
            select(func.count(model_class.id)).where(model_class.tenant_id == tenant_id)
        )
        num = (count or 0) + 1

    return f"{prefix}-{num:04d}"
