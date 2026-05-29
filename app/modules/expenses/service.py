"""سرویس ماژول هزینه‌ها — کامل."""
from datetime import datetime, timezone
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.models.business import Expense
from app.utils.normalizer import format_amount
from app.utils.jalali import parse_jalali


async def add_expense(session: AsyncSession, tenant_id: int, title: str, amount: float,
                      category: str = None, expense_type: str = None, person: str = None,
                      payment_method: str = None, expense_date: str = None,
                      note: str = None) -> str:
    expense = Expense(
        tenant_id=tenant_id, title=title, amount=amount, category=category,
        expense_type=expense_type, person=person, payment_method=payment_method,
        expense_date=parse_jalali(expense_date) if expense_date else None, note=note,
    )
    session.add(expense)
    await session.commit()

    msg = f"✅ هزینه ثبت شد: {title} — {format_amount(int(amount))}"
    if category:
        msg += f"\n📂 دسته: {category}"
    return msg


async def get_expenses_today(session: AsyncSession, tenant_id: int) -> str:
    start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    total = await session.scalar(select(func.coalesce(func.sum(Expense.amount), 0)).where(
        Expense.tenant_id == tenant_id, Expense.created_at >= start))
    count = await session.scalar(select(func.count(Expense.id)).where(
        Expense.tenant_id == tenant_id, Expense.created_at >= start))
    return f"💸 هزینه‌های امروز: {format_amount(int(total or 0))} ({count} مورد)"


async def delete_expense(session: AsyncSession, tenant_id: int,
                         title: str = None) -> str:
    """حذف یک هزینه — بر اساس عنوان (آخرین موردِ همنام)."""
    from app.database.models.business import Expense
    q = select(Expense).where(Expense.tenant_id == tenant_id)
    if title:
        q = q.where(Expense.title == title)
    q = q.order_by(Expense.id.desc()).limit(1)
    expense = await session.scalar(q)
    if not expense:
        return f"⚠️ هزینه‌ای{(' به نام «'+title+'»') if title else ''} پیدا نشد."
    t = expense.title
    await session.delete(expense)
    await session.commit()
    return f"🗑 هزینه‌ی «{t}» حذف شد."
