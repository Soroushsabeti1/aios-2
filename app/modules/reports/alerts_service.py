"""
هشدارهای خودکار — بحرانی + هفتگی.
"""
from datetime import date, timedelta
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.models.business import (
    Product, Customer, Employee, Invoice, Expense, SalaryPayment,
)
from app.utils.normalizer import format_amount
from app.utils.jalali import to_jalali_str


async def check_critical_alerts(session: AsyncSession, tenant_id: int) -> list[str]:
    """هشدارهای بحرانی — بعد از هر عملیات چک می‌شه."""
    alerts = []
    today = date.today()

    # ۱. کالاهای رو به اتمام
    low_stock = (await session.scalars(
        select(Product).where(
            Product.tenant_id == tenant_id,
            Product.stock <= Product.min_stock,
            Product.min_stock > 0,
        )
    )).all()
    for p in low_stock:
        alerts.append(f"⚠️ موجودی «{p.name}» ({p.display_id}) به {p.stock} رسید (حداقل: {p.min_stock}). سفارش بدم؟")

    # ۲. مشتری‌هایی که بدهیشون از سقف رد شده
    over_limit = (await session.scalars(
        select(Customer).where(
            Customer.tenant_id == tenant_id,
            Customer.credit_limit > 0,
            Customer.balance < 0,  # بدهکار
        )
    )).all()
    for c in over_limit:
        if abs(float(c.balance)) > float(c.credit_limit):
            alerts.append(
                f"⚠️ بدهی «{c.name}» ({format_amount(int(abs(c.balance)))}) از سقف "
                f"({format_amount(int(c.credit_limit))}) رد شده!"
            )

    # ۳. قرارداد کارمندان نزدیک اتمام (۳۰ روز)
    threshold = today + timedelta(days=30)
    expiring = (await session.scalars(
        select(Employee).where(
            Employee.tenant_id == tenant_id,
            Employee.contract_end.isnot(None),
            Employee.contract_end <= threshold,
            Employee.contract_end >= today,
        )
    )).all()
    for e in expiring:
        days_left = (e.contract_end - today).days
        alerts.append(f"⚠️ قرارداد «{e.name}» ({e.display_id}) {days_left} روز دیگه تموم می‌شه. تمدید کنم؟")

    return alerts


async def generate_weekly_report(session: AsyncSession, tenant_id: int) -> str:
    """گزارش هفتگی خودکار."""
    today = date.today()
    week_ago = today - timedelta(days=7)
    two_weeks_ago = today - timedelta(days=14)

    # فروش این هفته
    sales_this = await session.scalar(
        select(func.coalesce(func.sum(Invoice.final_amount), 0)).where(
            Invoice.tenant_id == tenant_id,
            Invoice.status.in_(["confirmed", "paid"]),
            Invoice.invoice_date >= week_ago,
        )
    ) or 0
    sales_count = await session.scalar(
        select(func.count(Invoice.id)).where(
            Invoice.tenant_id == tenant_id,
            Invoice.status.in_(["confirmed", "paid"]),
            Invoice.invoice_date >= week_ago,
        )
    ) or 0

    # فروش هفته قبل
    sales_prev = await session.scalar(
        select(func.coalesce(func.sum(Invoice.final_amount), 0)).where(
            Invoice.tenant_id == tenant_id,
            Invoice.status.in_(["confirmed", "paid"]),
            Invoice.invoice_date >= two_weeks_ago,
            Invoice.invoice_date < week_ago,
        )
    ) or 0

    # هزینه‌ها
    expenses = await session.scalar(
        select(func.coalesce(func.sum(Expense.amount), 0)).where(
            Expense.tenant_id == tenant_id,
            Expense.expense_date >= week_ago,
        )
    ) or 0

    # فاکتورهای نسیه قدیمی
    unpaid_invoices = await session.scalar(
        select(func.count(Invoice.id)).where(
            Invoice.tenant_id == tenant_id,
            Invoice.status == "confirmed",
            Invoice.invoice_date <= today - timedelta(days=30),
        )
    ) or 0

    # تولدهای این هفته
    # (ساده‌سازی — فقط چک ماه/روز)
    upcoming_bdays = []
    next_week = today + timedelta(days=7)
    customers = (await session.scalars(
        select(Customer).where(
            Customer.tenant_id == tenant_id,
            Customer.birth_date.isnot(None),
        )
    )).all()
    for c in customers:
        bd = c.birth_date
        this_year_bd = bd.replace(year=today.year)
        if today <= this_year_bd <= next_week:
            upcoming_bdays.append(f"🎂 {c.name} — {to_jalali_str(bd)}")

    # ساخت گزارش
    lines = ["📊 خلاصه هفتگی:"]
    lines.append(f"• فروش: {format_amount(int(sales_this))} ({sales_count} فاکتور)")
    if sales_prev > 0:
        change = ((float(sales_this) - float(sales_prev)) / float(sales_prev)) * 100
        emoji = "📈" if change >= 0 else "📉"
        lines.append(f"  {emoji} نسبت به هفته قبل: {'+' if change >= 0 else ''}{int(change)}%")
    lines.append(f"• هزینه‌ها: {format_amount(int(expenses))}")
    profit = float(sales_this) - float(expenses)
    lines.append(f"• سود خالص: {format_amount(int(abs(profit)))}" + (" 📈" if profit >= 0 else " 📉"))

    if unpaid_invoices:
        lines.append(f"\n⚠️ {unpaid_invoices} فاکتور نسیه قدیمی‌تر از ۳۰ روز")

    if upcoming_bdays:
        lines.append("\n🎂 تولدهای این هفته:")
        lines.extend(upcoming_bdays[:5])

    return "\n".join(lines)
