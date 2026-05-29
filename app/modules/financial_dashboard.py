"""داشبورد مالی — سود/زیان، جریان نقدی، مقایسه ماهانه."""
import io
from datetime import datetime, timezone, date
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.models.business import Invoice, Expense, SalaryPayment
from app.utils.jalali import to_jalali_str
from app.utils.normalizer import format_amount


async def monthly_profit_loss(session: AsyncSession, tenant_id: int,
                               year: int = None, month: int = None) -> str:
    """سود و زیان ماهانه."""
    now = datetime.now(timezone.utc)
    if not year:
        year = now.year
    if not month:
        month = now.month

    from datetime import timedelta
    import calendar
    _, last_day = calendar.monthrange(year, month)
    start = datetime(year, month, 1, tzinfo=timezone.utc)
    end = datetime(year, month, last_day, 23, 59, 59, tzinfo=timezone.utc)

    # درآمد — فاکتورهای پرداخت‌شده
    invoices = (await session.scalars(
        select(Invoice).where(
            Invoice.tenant_id == tenant_id,
            Invoice.status.in_(["paid", "confirmed"]),
            Invoice.created_at >= start,
            Invoice.created_at <= end,
        )
    )).all()
    total_income = sum(float(i.final_amount or i.total or 0) for i in invoices)

    # هزینه‌ها
    expenses = (await session.scalars(
        select(Expense).where(
            Expense.tenant_id == tenant_id,
            Expense.expense_date >= start.date(),
            Expense.expense_date <= end.date(),
        )
    )).all()
    total_expense = sum(float(e.amount or 0) for e in expenses)

    # حقوق
    salaries = (await session.scalars(
        select(SalaryPayment).where(
            SalaryPayment.tenant_id == tenant_id,
            SalaryPayment.paid_at >= start,
            SalaryPayment.paid_at <= end,
        )
    )).all()
    total_salary = sum(float(s.amount or 0) for s in salaries)

    total_cost = total_expense + total_salary
    profit = total_income - total_cost
    margin = round((profit / total_income * 100), 1) if total_income else 0

    icon = "📈" if profit >= 0 else "📉"
    lines = [
        f"{icon} گزارش مالی {month}/{year}:",
        f"💰 درآمد: {format_amount(int(total_income))}",
        f"💸 هزینه: {format_amount(int(total_expense))}",
        f"👥 حقوق: {format_amount(int(total_salary))}",
        f"─────────────────",
        f"{'✅ سود' if profit >= 0 else '🔴 زیان'}: {format_amount(int(abs(profit)))}",
        f"📊 حاشیه سود: {margin}%",
    ]
    return "\n".join(lines)


async def cashflow_report(session: AsyncSession, tenant_id: int,
                           months: int = 3) -> str:
    """جریان نقدی {months} ماه اخیر."""
    now = datetime.now(timezone.utc)
    lines = ["💵 جریان نقدی:"]

    for i in range(months - 1, -1, -1):
        m = now.month - i
        y = now.year
        while m <= 0:
            m += 12
            y -= 1

        import calendar
        _, last_day = calendar.monthrange(y, m)
        start = datetime(y, m, 1, tzinfo=timezone.utc)
        end = datetime(y, m, last_day, 23, 59, 59, tzinfo=timezone.utc)

        invoices = (await session.scalars(
            select(Invoice).where(
                Invoice.tenant_id == tenant_id,
                Invoice.status.in_(["paid", "confirmed"]),
                Invoice.created_at >= start,
                Invoice.created_at <= end,
            )
        )).all()
        income = sum(float(inv.final_amount or inv.total or 0) for inv in invoices)

        expenses = (await session.scalars(
            select(Expense).where(
                Expense.tenant_id == tenant_id,
                Expense.expense_date >= start.date(),
                Expense.expense_date <= end.date(),
            )
        )).all()
        expense = sum(float(e.amount or 0) for e in expenses)

        net = income - expense
        icon = "🟢" if net >= 0 else "🔴"
        lines.append(f"{icon} {m}/{y}: درآمد {format_amount(int(income))} | هزینه {format_amount(int(expense))} | خالص {format_amount(int(net))}")

    return "\n".join(lines)


async def monthly_comparison(session: AsyncSession, tenant_id: int) -> str:
    """مقایسه این ماه با ماه قبل."""
    now = datetime.now(timezone.utc)

    async def get_income(year, month):
        import calendar
        _, last_day = calendar.monthrange(year, month)
        start = datetime(year, month, 1, tzinfo=timezone.utc)
        end = datetime(year, month, last_day, 23, 59, 59, tzinfo=timezone.utc)
        invs = (await session.scalars(
            select(Invoice).where(
                Invoice.tenant_id == tenant_id,
                Invoice.status.in_(["paid", "confirmed"]),
                Invoice.created_at >= start,
                Invoice.created_at <= end,
            )
        )).all()
        return sum(float(i.final_amount or i.total or 0) for i in invs)

    this_m, this_y = now.month, now.year
    prev_m = this_m - 1 if this_m > 1 else 12
    prev_y = this_y if this_m > 1 else this_y - 1

    this_income = await get_income(this_y, this_m)
    prev_income = await get_income(prev_y, prev_m)

    if prev_income > 0:
        change = round(((this_income - prev_income) / prev_income) * 100, 1)
        change_str = f"+{change}% 📈" if change >= 0 else f"{change}% 📉"
    else:
        change_str = "اولین ماه"

    lines = [
        f"📊 مقایسه ماهانه:",
        f"این ماه ({this_m}/{this_y}): {format_amount(int(this_income))}",
        f"ماه قبل ({prev_m}/{prev_y}): {format_amount(int(prev_income))}",
        f"تغییر: {change_str}",
    ]
    return "\n".join(lines)


async def top_selling_products(session: AsyncSession, tenant_id: int,
                                limit: int = 10) -> str:
    """پرفروش‌ترین محصولات."""
    from app.database.models.business import InvoiceItem
    from sqlalchemy import desc

    results = (await session.execute(
        select(
            InvoiceItem.product_name,
            func.sum(InvoiceItem.quantity).label("total_qty"),
            func.sum(InvoiceItem.total_price).label("total_revenue"),
        )
        .join(Invoice, InvoiceItem.invoice_id == Invoice.id)
        .where(Invoice.tenant_id == tenant_id)
        .group_by(InvoiceItem.product_name)
        .order_by(desc("total_revenue"))
        .limit(limit)
    )).all()

    if not results:
        return "هنوز فروشی ثبت نشده."

    lines = ["⭐ پرفروش‌ترین محصولات:"]
    for i, r in enumerate(results, 1):
        lines.append(f"{i}. {r.product_name} — {int(r.total_qty or 0)} عدد — {format_amount(int(r.total_revenue or 0))}")
    return "\n".join(lines)


async def financial_summary(session: AsyncSession, tenant_id: int) -> str:
    """خلاصه مالی کلی."""
    pl = await monthly_profit_loss(session, tenant_id)
    comp = await monthly_comparison(session, tenant_id)
    return f"{pl}\n\n{comp}"
