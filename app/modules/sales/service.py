"""
سرویس فاکتور/فروش — نسخه کامل.
چرخه: draft(پیش‌فاکتور) → confirmed(تأیید) → paid(پرداخت) / cancelled(کنسل)
فقط بعد confirm: کسر از انبار + آپدیت بدهی مشتری + درآمد.
"""
from datetime import date, datetime, timezone
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.models.business import Invoice, InvoiceItem, Customer, Product
from app.utils.normalizer import format_amount
from app.utils.jalali import parse_jalali, to_jalali_str
from app.utils.id_generator import generate_display_id


async def create_invoice(session: AsyncSession, tenant_id: int,
                         customer_name: str, items: list[dict],
                         discount: float = 0, tax_percent: float = 9,
                         paid: float = 0, payment_method: str = None,
                         note: str = None, invoice_date: str = None) -> str:
    """
    ساخت پیش‌فاکتور (draft). هنوز از انبار کسر نمی‌شود.
    items: [{"product_name": "...", "quantity": N, "unit_price": X}]
    """
    # پیدا کردن مشتری
    customer = await session.scalar(
        select(Customer).where(Customer.tenant_id == tenant_id, Customer.name == customer_name)
    )
    customer_id = customer.id if customer else None
    customer_did = customer.display_id if customer else None

    # محاسبه آیتم‌ها
    total = 0
    inv_items = []
    item_lines = []

    for i, item in enumerate(items, 1):
        pname = item.get("product_name", "")
        qty = int(item.get("quantity", 1))
        up = float(item.get("unit_price", 0))

        # اگه قیمت نداد، از دیتابیس بگیر
        product = await session.scalar(
            select(Product).where(Product.tenant_id == tenant_id, Product.name == pname)
        )
        if product and up == 0:
            up = float(product.sell_price or 0)

        line_total = qty * up
        total += line_total

        inv_items.append({
            "product_id": product.id if product else None,
            "product_name": pname,
            "quantity": qty,
            "unit_price": up,
            "total_price": line_total,
        })

        pdid = product.display_id if product else "—"
        item_lines.append(f"  {i}. {pname} ({pdid}) × {qty} = {format_amount(int(line_total))}")

    # محاسبه مالیات و نهایی
    tax_amount = total * (tax_percent / 100)
    final = total - discount + tax_amount

    did = await generate_display_id(session, tenant_id, "invoices", Invoice)
    inv_date = parse_jalali(invoice_date) if invoice_date else date.today()

    # ساخت فاکتور (draft)
    invoice = Invoice(
        tenant_id=tenant_id, display_id=did, customer_id=customer_id,
        customer_name=customer_name, total=total, discount=discount,
        tax=tax_amount, final_amount=final, paid=paid,
        status="draft", payment_method=payment_method,
        invoice_date=inv_date, note=note,
    )
    session.add(invoice)
    await session.flush()

    # ساخت آیتم‌ها
    for it in inv_items:
        session.add(InvoiceItem(
            tenant_id=tenant_id, invoice_id=invoice.id, **it
        ))
    await session.commit()

    # ساخت پیام تأیید
    lines = [f"📋 پیش‌فاکتور {did} برای «{customer_name}»" + (f" ({customer_did})" if customer_did else "")]
    lines.append(f"📅 {to_jalali_str(inv_date)}")
    lines.append("─" * 25)
    lines.extend(item_lines)
    lines.append("─" * 25)
    lines.append(f"  جمع: {format_amount(int(total))}")
    if discount:
        lines.append(f"  تخفیف: −{format_amount(int(discount))}")
    if tax_amount:
        lines.append(f"  مالیات ({int(tax_percent)}٪): +{format_amount(int(tax_amount))}")
    lines.append(f"  💰 مبلغ نهایی: {format_amount(int(final))}")
    if paid:
        lines.append(f"  پرداخت: {format_amount(int(paid))}" + (f" ({payment_method})" if payment_method else ""))
        remaining = final - paid
        if remaining > 0:
            lines.append(f"  مانده (نسیه): {format_amount(int(remaining))}")
    lines.append("")
    lines.append("⚠️ این پیش‌فاکتوره. برای ثبت نهایی بگو «تأیید فاکتور».")

    return "\n".join(lines)


async def confirm_invoice(session: AsyncSession, tenant_id: int,
                          invoice_display_id: str = None) -> str:
    """
    تأیید فاکتور → کسر از انبار + آپدیت بدهی مشتری.
    اگه display_id نداد، آخرین draft رو تأیید می‌کنه.
    """
    if invoice_display_id:
        invoice = await session.scalar(
            select(Invoice).where(
                Invoice.tenant_id == tenant_id,
                Invoice.display_id == invoice_display_id,
            )
        )
    else:
        invoice = await session.scalar(
            select(Invoice).where(
                Invoice.tenant_id == tenant_id,
                Invoice.status == "draft",
            ).order_by(Invoice.id.desc()).limit(1)
        )

    if not invoice:
        return "⚠️ پیش‌فاکتوری برای تأیید پیدا نشد."

    if invoice.status != "draft":
        return f"⚠️ فاکتور {invoice.display_id} قبلاً تأیید شده (وضعیت: {invoice.status})."

    # کسر از انبار
    items = (await session.scalars(
        select(InvoiceItem).where(InvoiceItem.invoice_id == invoice.id)
    )).all()

    stock_changes = []
    for item in items:
        if item.product_id:
            product = await session.get(Product, item.product_id)
            if product:
                old_stock = product.stock
                product.stock = max(0, product.stock - item.quantity)
                stock_changes.append(f"📦 {product.name}: {old_stock} → {product.stock}")

    # آپدیت بدهی مشتری
    debt_msg = ""
    if invoice.customer_id:
        customer = await session.get(Customer, invoice.customer_id)
        if customer:
            remaining = float(invoice.final_amount) - float(invoice.paid)
            if remaining > 0:
                customer.balance = float(customer.balance or 0) - remaining
                debt_msg = f"💳 بدهی «{customer.name}»: {format_amount(int(abs(customer.balance)))}"
            customer.total_purchase = float(customer.total_purchase or 0) + float(invoice.final_amount)

    # تغییر وضعیت
    if float(invoice.paid) >= float(invoice.final_amount):
        invoice.status = "paid"
        status_label = "پرداخت‌شده ✅"
    else:
        invoice.status = "confirmed"
        status_label = "تأیید‌شده"

    await session.commit()

    lines = [f"✅ فاکتور {invoice.display_id} تأیید و ثبت نهایی شد! ({status_label})"]
    lines.extend(stock_changes)
    if debt_msg:
        lines.append(debt_msg)
    return "\n".join(lines)


async def cancel_invoice(session: AsyncSession, tenant_id: int,
                         invoice_display_id: str = None) -> str:
    """کنسل کردن فاکتور."""
    if invoice_display_id:
        invoice = await session.scalar(
            select(Invoice).where(
                Invoice.tenant_id == tenant_id,
                Invoice.display_id == invoice_display_id,
            )
        )
    else:
        invoice = await session.scalar(
            select(Invoice).where(
                Invoice.tenant_id == tenant_id,
                Invoice.status.in_(["draft", "confirmed"]),
            ).order_by(Invoice.id.desc()).limit(1)
        )

    if not invoice:
        return "⚠️ فاکتوری برای کنسل کردن پیدا نشد."

    if invoice.status == "cancelled":
        return f"⚠️ فاکتور {invoice.display_id} قبلاً کنسل شده."

    # اگه تأیید شده بود، موجودی رو برگردون
    if invoice.status in ("confirmed", "paid"):
        items = (await session.scalars(
            select(InvoiceItem).where(InvoiceItem.invoice_id == invoice.id)
        )).all()
        for item in items:
            if item.product_id:
                product = await session.get(Product, item.product_id)
                if product:
                    product.stock += item.quantity

        # برگرداندن بدهی مشتری
        if invoice.customer_id:
            customer = await session.get(Customer, invoice.customer_id)
            if customer:
                remaining = float(invoice.final_amount) - float(invoice.paid)
                if remaining > 0:
                    customer.balance = float(customer.balance or 0) + remaining
                customer.total_purchase = max(0, float(customer.total_purchase or 0) - float(invoice.final_amount))

    invoice.status = "cancelled"
    await session.commit()
    return f"🚫 فاکتور {invoice.display_id} کنسل شد."


async def list_invoices(session: AsyncSession, tenant_id: int,
                        status: str = None, customer_name: str = None,
                        limit: int = 15) -> str:
    """لیست فاکتورها با فیلتر."""
    query = select(Invoice).where(Invoice.tenant_id == tenant_id)
    if status:
        query = query.where(Invoice.status == status)
    if customer_name:
        query = query.where(Invoice.customer_name == customer_name)
    query = query.order_by(Invoice.id.desc()).limit(limit)

    invoices = (await session.scalars(query)).all()
    if not invoices:
        return "فاکتوری پیدا نشد."

    status_icons = {"draft": "📋", "confirmed": "✔️", "paid": "✅", "cancelled": "🚫"}
    status_labels = {"draft": "پیش‌فاکتور", "confirmed": "تأیید", "paid": "پرداخت", "cancelled": "کنسل"}

    lines = ["📄 فاکتورها:"]
    for inv in invoices:
        icon = status_icons.get(inv.status, "📄")
        label = status_labels.get(inv.status, inv.status)
        lines.append(
            f"• [{inv.display_id}] {inv.customer_name or '—'} — "
            f"{format_amount(int(inv.final_amount))} "
            f"{icon} {label}"
        )
    return "\n".join(lines)


async def get_invoice_detail(session: AsyncSession, tenant_id: int,
                             invoice_display_id: str) -> str:
    """جزئیات یک فاکتور."""
    invoice = await session.scalar(
        select(Invoice).where(
            Invoice.tenant_id == tenant_id,
            Invoice.display_id == invoice_display_id,
        )
    )
    if not invoice:
        return f"فاکتور {invoice_display_id} پیدا نشد."

    items = (await session.scalars(
        select(InvoiceItem).where(InvoiceItem.invoice_id == invoice.id)
    )).all()

    status_labels = {"draft": "📋 پیش‌فاکتور", "confirmed": "✔️ تأیید‌شده",
                     "paid": "✅ پرداخت‌شده", "cancelled": "🚫 کنسل"}

    lines = [
        f"📄 فاکتور {invoice.display_id} — {status_labels.get(invoice.status, '')}",
        f"👤 مشتری: {invoice.customer_name or '—'}",
        f"📅 تاریخ: {to_jalali_str(invoice.invoice_date) if invoice.invoice_date else '—'}",
        "─" * 25,
    ]
    for i, item in enumerate(items, 1):
        lines.append(f"  {i}. {item.product_name} × {item.quantity} = {format_amount(int(item.total_price))}")
    lines.append("─" * 25)
    lines.append(f"  جمع: {format_amount(int(invoice.total))}")
    if invoice.discount:
        lines.append(f"  تخفیف: −{format_amount(int(invoice.discount))}")
    if invoice.tax:
        lines.append(f"  مالیات: +{format_amount(int(invoice.tax))}")
    lines.append(f"  💰 نهایی: {format_amount(int(invoice.final_amount))}")
    if invoice.paid:
        lines.append(f"  پرداخت: {format_amount(int(invoice.paid))}")
    remaining = float(invoice.final_amount) - float(invoice.paid)
    if remaining > 0:
        lines.append(f"  مانده: {format_amount(int(remaining))}")

    # نوت فاکتور — فقط برای کارفرما (این تابع فقط در دسترس owner است)
    if invoice.note:
        lines.append(f"📝 یادداشت: {invoice.note}")

    return "\n".join(lines)
