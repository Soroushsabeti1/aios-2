"""
گزارش‌های پیشرفته — فروش، مالی، انبار، فیلتر ترکیبی.
خروجی: متنی (چت).
"""
from datetime import date, datetime, timezone, timedelta
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.models.business import (
    Invoice, InvoiceItem, Expense, Customer, Product, Employee, SalaryPayment,
)
from app.utils.normalizer import format_amount
from app.utils.jalali import to_jalali_str


def _today():
    return date.today()


def _month_start():
    t = date.today()
    return t.replace(day=1)


def _week_start():
    t = date.today()
    return t - timedelta(days=t.weekday())


async def sales_report(session: AsyncSession, tenant_id: int,
                       period: str = "today", customer_name: str = None,
                       product_name: str = None) -> str:
    """گزارش فروش."""
    q = select(Invoice).where(
        Invoice.tenant_id == tenant_id,
        Invoice.status.in_(["confirmed", "paid"]),
    )
    if period == "today":
        q = q.where(Invoice.invoice_date == _today())
        period_label = "امروز"
    elif period == "week":
        q = q.where(Invoice.invoice_date >= _week_start())
        period_label = "این هفته"
    elif period == "month":
        q = q.where(Invoice.invoice_date >= _month_start())
        period_label = "این ماه"
    else:
        period_label = "کل"

    if customer_name:
        q = q.where(Invoice.customer_name == customer_name)

    invoices = (await session.scalars(q)).all()
    if not invoices:
        return f"📊 فروشی برای {period_label} ثبت نشده."

    total_sales = sum(float(i.final_amount) for i in invoices)
    total_paid = sum(float(i.paid) for i in invoices)
    total_debt = total_sales - total_paid
    cash = sum(float(i.paid) for i in invoices if i.payment_method == "نقد")
    count = len(invoices)

    lines = [f"📊 گزارش فروش {period_label}:"]
    lines.append(f"• تعداد فاکتور: {count}")
    lines.append(f"• جمع فروش: {format_amount(int(total_sales))}")
    lines.append(f"• نقد دریافتی: {format_amount(int(total_paid))}")
    if total_debt > 0:
        lines.append(f"• نسیه: {format_amount(int(total_debt))}")

    # پرفروش‌ترین کالا
    if not product_name:
        inv_ids = [i.id for i in invoices]
        if inv_ids:
            top = (await session.execute(
                select(InvoiceItem.product_name, func.sum(InvoiceItem.quantity).label("qty"))
                .where(InvoiceItem.invoice_id.in_(inv_ids))
                .group_by(InvoiceItem.product_name)
                .order_by(func.sum(InvoiceItem.quantity).desc())
                .limit(3)
            )).all()
            if top:
                lines.append("• پرفروش‌ترین:")
                for name, qty in top:
                    lines.append(f"  - {name}: {qty} عدد")

    # بیشترین خرید
    if not customer_name:
        top_cust = (await session.execute(
            select(Invoice.customer_name, func.sum(Invoice.final_amount).label("total"))
            .where(
                Invoice.tenant_id == tenant_id,
                Invoice.status.in_(["confirmed", "paid"]),
                Invoice.invoice_date >= (_today() if period == "today" else _month_start()),
            )
            .group_by(Invoice.customer_name)
            .order_by(func.sum(Invoice.final_amount).desc())
            .limit(3)
        )).all()
        if top_cust:
            lines.append("• بیشترین خرید:")
            for name, total in top_cust:
                lines.append(f"  - {name}: {format_amount(int(total))}")

    return "\n".join(lines)


async def financial_report(session: AsyncSession, tenant_id: int,
                           period: str = "month") -> str:
    """گزارش مالی — سود، هزینه، درآمد."""
    if period == "today":
        start = _today()
        label = "امروز"
    elif period == "week":
        start = _week_start()
        label = "این هفته"
    else:
        start = _month_start()
        label = "این ماه"

    # درآمد
    income = await session.scalar(
        select(func.coalesce(func.sum(Invoice.final_amount), 0)).where(
            Invoice.tenant_id == tenant_id,
            Invoice.status.in_(["confirmed", "paid"]),
            Invoice.invoice_date >= start,
        )
    ) or 0

    # هزینه
    expense_total = await session.scalar(
        select(func.coalesce(func.sum(Expense.amount), 0)).where(
            Expense.tenant_id == tenant_id,
            Expense.expense_date >= start,
        )
    ) or 0

    # حقوق
    salary_total = await session.scalar(
        select(func.coalesce(func.sum(SalaryPayment.amount), 0)).where(
            SalaryPayment.tenant_id == tenant_id,
            SalaryPayment.payment_date >= start,
        )
    ) or 0

    total_cost = float(expense_total) + float(salary_total)
    profit = float(income) - total_cost

    lines = [f"💰 گزارش مالی {label}:"]
    lines.append(f"• درآمد (فروش): {format_amount(int(income))}")
    lines.append(f"• هزینه‌ها: {format_amount(int(expense_total))}")
    lines.append(f"• حقوق پرداختی: {format_amount(int(salary_total))}")
    lines.append(f"• {'سود' if profit >= 0 else 'زیان'} خالص: {format_amount(int(abs(profit)))}"
                 + (" 📈" if profit >= 0 else " 📉"))

    return "\n".join(lines)


async def debtors_report(session: AsyncSession, tenant_id: int) -> str:
    """لیست بدهکاران به ترتیب بدهی."""
    customers = (await session.scalars(
        select(Customer).where(
            Customer.tenant_id == tenant_id,
            Customer.balance < 0,
        ).order_by(Customer.balance.asc())
    )).all()

    if not customers:
        return "✅ هیچ مشتری بدهکاری نداری!"

    total_debt = sum(abs(float(c.balance)) for c in customers)
    lines = [f"💳 لیست بدهکاران ({len(customers)} نفر — جمع: {format_amount(int(total_debt))}):"]
    for c in customers:
        lines.append(f"• [{c.display_id}] {c.name}: {format_amount(int(abs(c.balance)))}")
    return "\n".join(lines)


async def inventory_report(session: AsyncSession, tenant_id: int) -> str:
    """گزارش انبار — ارزش کل + رو به اتمام."""
    products = (await session.scalars(
        select(Product).where(Product.tenant_id == tenant_id)
    )).all()

    if not products:
        return "انباری ثبت نشده."

    total_value = sum(p.stock * float(p.buy_price or 0) for p in products)
    total_items = sum(p.stock for p in products)
    low_stock = [p for p in products if p.stock <= p.min_stock and p.min_stock > 0]

    lines = [f"📦 گزارش انبار:"]
    lines.append(f"• تعداد کالاها: {len(products)}")
    lines.append(f"• موجودی کل: {total_items} عدد")
    lines.append(f"• ارزش انبار (قیمت خرید): {format_amount(int(total_value))}")
    if low_stock:
        lines.append(f"\n⚠️ رو به اتمام ({len(low_stock)}):")
        for p in low_stock[:10]:
            lines.append(f"  - [{p.display_id}] {p.name}: {p.stock} (حداقل: {p.min_stock})")

    return "\n".join(lines)


async def smart_search(session: AsyncSession, tenant_id: int,
                       search_text: str = None,
                       entity_type: str = "all",
                       city: str = None,
                       min_amount: float = None,
                       max_amount: float = None,
                       near_birthday: bool = False,
                       near_contract_end: bool = False,
                       sort_by: str = None) -> str:
    """فیلتر و جستجوی پیشرفته."""
    results = []
    today = _today()

    # جستجوی مشتری
    if entity_type in ("all", "customers"):
        q = select(Customer).where(Customer.tenant_id == tenant_id)
        if search_text:
            q = q.where(Customer.name.ilike(f"%{search_text}%"))
        if city:
            q = q.where(Customer.city == city)
        if min_amount is not None:
            q = q.where(Customer.total_purchase >= min_amount)
        if near_birthday:
            # تولد طی ۳۰ روز آینده
            pass  # نیاز به محاسبه شمسی — ساده‌سازی
        if sort_by == "debt":
            q = q.order_by(Customer.balance.asc())
        elif sort_by == "purchase":
            q = q.order_by(Customer.total_purchase.desc())
        customers = (await session.scalars(q.limit(20))).all()
        for c in customers:
            line = f"👤 [{c.display_id}] {c.name}"
            if c.city:
                line += f" ({c.city})"
            if c.balance and float(c.balance) < 0:
                line += f" — بدهی: {format_amount(int(abs(c.balance)))}"
            results.append(line)

    # جستجوی کارمند
    if entity_type in ("all", "employees"):
        q = select(Employee).where(Employee.tenant_id == tenant_id)
        if search_text:
            q = q.where(Employee.name.ilike(f"%{search_text}%"))
        if city:
            q = q.where(Employee.city == city)
        if near_contract_end:
            end_threshold = today + timedelta(days=30)
            q = q.where(Employee.contract_end.isnot(None), Employee.contract_end <= end_threshold)
        employees = (await session.scalars(q.limit(20))).all()
        for e in employees:
            line = f"👔 [{e.display_id}] {e.name}"
            if e.role:
                line += f" — {e.role}"
            if e.city:
                line += f" ({e.city})"
            if near_contract_end and e.contract_end:
                days_left = (e.contract_end - today).days
                line += f" ⚠️ {days_left} روز تا پایان قرارداد"
            results.append(line)

    # جستجوی کالا
    if entity_type in ("all", "products"):
        q = select(Product).where(Product.tenant_id == tenant_id)
        if search_text:
            q = q.where(Product.name.ilike(f"%{search_text}%"))
        products = (await session.scalars(q.limit(20))).all()
        for p in products:
            line = f"📦 [{p.display_id}] {p.name} — موجودی: {p.stock}"
            results.append(line)

    if not results:
        return "نتیجه‌ای پیدا نشد."

    return f"🔍 {len(results)} نتیجه:\n" + "\n".join(results)
