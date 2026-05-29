"""سرویس ماژول مشتریان (CRM) — نسخه ۲ با آیدی پیشونددار."""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.models.business import Customer
from app.data.iran_geo import find_province
from app.utils.normalizer import format_amount
from app.utils.jalali import parse_jalali, to_jalali_str
from app.utils.id_generator import generate_display_id


async def add_customer(session: AsyncSession, tenant_id: int, name: str,
                       phone: str = None, email: str = None, national_id: str = None,
                       birth_date: str = None, city: str = None, address: str = None,
                       credit_limit: float = 0, code: str = None, note: str = None) -> str:
    existing = await session.scalar(
        select(Customer).where(Customer.tenant_id == tenant_id, Customer.name == name)
    )
    if existing:
        return f"⚠️ مشتری «{name}» از قبل ثبت شده. (شناسه: {existing.display_id})"

    province = find_province(city) if city else None
    bd = parse_jalali(birth_date) if birth_date else None
    did = await generate_display_id(session, tenant_id, "customers", Customer)

    customer = Customer(
        tenant_id=tenant_id, display_id=did, name=name, phone=phone, email=email,
        national_id=national_id, birth_date=bd, city=city, province=province,
        address=address, credit_limit=credit_limit or 0, code=code, note=note,
    )
    session.add(customer)
    await session.commit()

    parts = [f"✅ مشتری «{name}» ثبت شد (شناسه: {did})"]
    if city:
        parts.append(f"📍 {city}" + (f" ({province})" if province else ""))
    if phone:
        parts.append(f"📞 {phone}")
    if bd:
        parts.append(f"🎂 تولد: {to_jalali_str(bd)}")
    return "\n".join(parts)


async def list_customers(session: AsyncSession, tenant_id: int, filter: str = "all",
                         city: str = None, sort_by_debt: bool = False, limit: int = 20) -> str:
    query = select(Customer).where(Customer.tenant_id == tenant_id)
    if filter == "debtors":
        query = query.where(Customer.balance < 0)
    elif filter == "vip":
        query = query.order_by(Customer.total_purchase.desc())
    elif filter == "by_city" and city:
        query = query.where(Customer.city == city)
    if sort_by_debt:
        query = query.order_by(Customer.balance.asc())
    query = query.limit(limit)

    customers = (await session.scalars(query)).all()
    if not customers:
        return "مشتری‌ای با این مشخصات پیدا نشد."

    lines = []
    for c in customers:
        line = f"• [{c.display_id}] {c.name}"
        if c.city:
            line += f" ({c.city})"
        if c.balance < 0:
            line += f" — بدهکار: {format_amount(int(abs(c.balance)))}"
        lines.append(line)

    header = {"debtors": "👥 مشتریان بدهکار:", "vip": "⭐ مشتریان پرخرید:",
              "by_city": f"👥 مشتریان {city}:"}.get(filter, "👥 مشتریان:")
    return header + "\n" + "\n".join(lines)


async def update_customer(session: AsyncSession, tenant_id: int, name: str,
                          new_phone: str = None, new_city: str = None,
                          new_address: str = None, new_credit_limit: float = None) -> str:
    customer = await session.scalar(
        select(Customer).where(Customer.tenant_id == tenant_id, Customer.name == name)
    )
    if not customer:
        return f"مشتری «{name}» پیدا نشد."
    if new_phone:
        customer.phone = new_phone
    if new_city:
        customer.city = new_city
        customer.province = find_province(new_city)
    if new_address:
        customer.address = new_address
    if new_credit_limit is not None:
        customer.credit_limit = new_credit_limit
    await session.commit()
    return f"✅ اطلاعات «{name}» به‌روز شد. (شناسه: {customer.display_id})"


async def delete_customer(session: AsyncSession, tenant_id: int, name: str) -> str:
    customer = await session.scalar(
        select(Customer).where(Customer.tenant_id == tenant_id, Customer.name == name)
    )
    if not customer:
        return f"مشتری «{name}» پیدا نشد."
    await session.delete(customer)
    await session.commit()
    return f"🗑 مشتری «{name}» ({customer.display_id}) حذف شد."


async def get_customer_detail(session: AsyncSession, tenant_id: int,
                               name: str) -> str:
    """اطلاعات کامل یک مشتری."""
    cust = await session.scalar(
        select(Customer).where(
            Customer.tenant_id == tenant_id,
            Customer.name.ilike(f"%{name}%"),
        ).limit(1)
    )
    if not cust:
        return f"⚠️ مشتری با نام «{name}» پیدا نشد."

    lines = [f"🛒 اطلاعات کامل مشتری «{cust.name}» [{cust.display_id}]:"]
    if cust.code:
        lines.append(f"🔖 کد: {cust.code}")
    if cust.phone:
        lines.append(f"📞 تلفن: {cust.phone}")
    if cust.email:
        lines.append(f"📧 ایمیل: {cust.email}")
    if cust.national_id:
        lines.append(f"🪪 کد ملی: {cust.national_id}")
    if cust.birth_date:
        lines.append(f"🎂 تولد: {to_jalali_str(cust.birth_date)}")
    if cust.province or cust.city:
        lines.append(f"📍 {cust.city or ''} {('(' + cust.province + ')') if cust.province else ''}")
    if cust.address:
        lines.append(f"🏠 آدرس: {cust.address}")
    if cust.postal_code:
        lines.append(f"📮 کد پستی: {cust.postal_code}")
    lines.append(f"💰 مانده حساب: {format_amount(int(cust.balance))}")
    if cust.credit_limit:
        lines.append(f"📊 سقف بدهی: {format_amount(int(cust.credit_limit))}")
    if cust.total_purchase:
        lines.append(f"🛍 کل خرید: {format_amount(int(cust.total_purchase))}")
    if cust.note:
        lines.append(f"📝 یادداشت: {cust.note}")
    if cust.bale_id:
        lines.append(f"💬 بله: {cust.bale_id}")
    if cust.telegram_id:
        lines.append(f"📱 تلگرام: {cust.telegram_id}")
    if cust.rubika_id:
        lines.append(f"📲 روبیکا: {cust.rubika_id}")
    return "\n".join(lines)


async def search_customers(session: AsyncSession, tenant_id: int,
                            sort_by: str = "name", order: str = "asc",
                            filter_field: str = None, filter_value: str = None,
                            limit: int = 20) -> str:
    """جستجو و مرتب‌سازی مشتریان."""
    from sqlalchemy import desc as _desc

    query = select(Customer).where(Customer.tenant_id == tenant_id)

    if filter_field and filter_value:
        field_map = {
            "city": Customer.city, "province": Customer.province,
            "name": Customer.name,
        }
        col = field_map.get(filter_field)
        if col is not None:
            query = query.where(col.ilike(f"%{filter_value}%"))

    sort_map = {
        "name": Customer.name, "balance": Customer.balance,
        "total_purchase": Customer.total_purchase, "city": Customer.city,
    }
    sort_col = sort_map.get(sort_by, Customer.name)
    if order == "desc":
        query = query.order_by(_desc(sort_col))
    else:
        query = query.order_by(sort_col)

    query = query.limit(limit)
    customers = (await session.scalars(query)).all()
    if not customers:
        return "مشتری‌ای پیدا نشد."

    lines = [f"🛒 مشتریان (مرتب بر اساس {sort_by}):"]
    for i, c in enumerate(customers, 1):
        line = f"{i}. [{c.display_id}] {c.name}"
        if sort_by == "balance" and c.balance:
            line += f" — {format_amount(int(c.balance))}"
        if sort_by == "total_purchase" and c.total_purchase:
            line += f" — خرید: {format_amount(int(c.total_purchase))}"
        if c.city:
            line += f" [{c.city}]"
        lines.append(line)
    return "\n".join(lines)


async def customer_statistics(session: AsyncSession, tenant_id: int) -> str:
    """آمار کلی مشتریان."""
    customers = (await session.scalars(
        select(Customer).where(Customer.tenant_id == tenant_id)
    )).all()

    if not customers:
        return "هیچ مشتری‌ای ثبت نشده."

    total = len(customers)
    debtors = [c for c in customers if c.balance < 0]
    total_debt = sum(abs(c.balance) for c in debtors)
    total_purchase = sum(c.total_purchase or 0 for c in customers)
    cities = set(c.city for c in customers if c.city)

    lines = [
        f"📊 آمار مشتریان:",
        f"👥 تعداد کل: {total}",
        f"🔴 بدهکار: {len(debtors)} نفر — مجموع: {format_amount(int(total_debt))}",
        f"🛍 کل خرید: {format_amount(int(total_purchase))}",
        f"🏙 شهرها: {', '.join(cities) if cities else '—'}",
    ]
    return "\n".join(lines)


async def top_customers(session: AsyncSession, tenant_id: int,
                         by: str = "purchase", limit: int = 10) -> str:
    """رتبه‌بندی مشتریان."""
    from sqlalchemy import desc as _desc

    query = select(Customer).where(Customer.tenant_id == tenant_id)
    if by == "debt":
        query = query.where(Customer.balance < 0).order_by(Customer.balance.asc())
        header = "🔴 بیشترین بدهکاران:"
    else:
        query = query.order_by(_desc(Customer.total_purchase))
        header = "⭐ پرخریدترین مشتریان:"

    query = query.limit(limit)
    customers = (await session.scalars(query)).all()
    if not customers:
        return "مشتری‌ای پیدا نشد."

    lines = [header]
    for i, c in enumerate(customers, 1):
        if by == "debt":
            lines.append(f"{i}. {c.name} — بدهی: {format_amount(int(abs(c.balance)))}")
        else:
            lines.append(f"{i}. {c.name} — خرید: {format_amount(int(c.total_purchase or 0))}")
    return "\n".join(lines)


async def customer_purchase_history(session: AsyncSession, tenant_id: int,
                                      name: str, limit: int = 20) -> str:
    """تاریخچه خرید کامل یک مشتری."""
    from app.database.models.business import Invoice, InvoiceItem

    cust = await session.scalar(
        select(Customer).where(
            Customer.tenant_id == tenant_id,
            Customer.name.ilike(f"%{name}%"),
        ).limit(1)
    )
    if not cust:
        return f"⚠️ مشتری «{name}» پیدا نشد."

    invoices = (await session.scalars(
        select(Invoice).where(
            Invoice.tenant_id == tenant_id,
            Invoice.customer_id == cust.id,
        ).order_by(Invoice.created_at.desc()).limit(limit)
    )).all()

    if not invoices:
        return f"هیچ فاکتوری برای «{cust.name}» ثبت نشده."

    lines = [f"🛒 تاریخچه خرید «{cust.name}» [{cust.display_id}]:"]
    total_all = 0
    for inv in invoices:
        d = to_jalali_str(inv.invoice_date) if inv.invoice_date else to_jalali_str(inv.created_at.date()) if inv.created_at else "—"
        status_fa = {"draft": "پیش‌فاکتور", "confirmed": "تأیید", "paid": "پرداخت‌شده",
                     "installment": "اقساطی", "cancelled": "لغو"}.get(inv.status, inv.status)
        amt = int(inv.final_amount or inv.total or 0)
        total_all += amt
        lines.append(f"• [{inv.display_id}] {d} — {format_amount(amt)} — {status_fa}")

        # اقلام
        items = (await session.scalars(
            select(InvoiceItem).where(InvoiceItem.invoice_id == inv.id)
        )).all()
        for item in items:
            lines.append(f"   └ {item.product_name} × {item.quantity} = {format_amount(int(item.total_price))}")

    lines.append(f"\n💰 مجموع کل خریدها: {format_amount(total_all)}")
    return "\n".join(lines)
