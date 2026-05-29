"""سرویس اقساط فاکتور."""
from datetime import date
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.models.business import Installment, Invoice
from app.utils.jalali import parse_jalali, to_jalali_str
from app.utils.normalizer import format_amount


async def add_installment(session: AsyncSession, tenant_id: int,
                           invoice_display_id: str, amount: float,
                           due_date: str, installment_number: int = None) -> str:
    inv = await session.scalar(
        select(Invoice).where(
            Invoice.tenant_id == tenant_id,
            Invoice.display_id == invoice_display_id,
        )
    )
    if not inv:
        return f"⚠️ فاکتور «{invoice_display_id}» پیدا نشد."

    if not installment_number:
        from sqlalchemy import func
        count = await session.scalar(
            select(func.count(Installment.id)).where(
                Installment.invoice_id == inv.id
            )
        ) or 0
        installment_number = count + 1

    inst = Installment(
        tenant_id=tenant_id, invoice_id=inv.id,
        installment_number=installment_number,
        amount=amount, due_date=parse_jalali(due_date),
        status="پرداخت نشده",
    )
    session.add(inst)
    inv.status = "installment"
    await session.commit()

    return (f"✅ قسط شماره {installment_number} فاکتور {invoice_display_id} ثبت شد.\n"
            f"💰 مبلغ: {format_amount(int(amount))}\n"
            f"📅 سررسید: {due_date}")


async def list_installments(session: AsyncSession, tenant_id: int,
                             invoice_display_id: str = None) -> str:
    if invoice_display_id:
        inv = await session.scalar(
            select(Invoice).where(
                Invoice.tenant_id == tenant_id,
                Invoice.display_id == invoice_display_id,
            )
        )
        if not inv:
            return f"⚠️ فاکتور «{invoice_display_id}» پیدا نشد."
        insts = (await session.scalars(
            select(Installment).where(Installment.invoice_id == inv.id)
            .order_by(Installment.installment_number)
        )).all()
    else:
        insts = (await session.scalars(
            select(Installment).where(Installment.tenant_id == tenant_id)
            .order_by(Installment.due_date)
        )).all()

    if not insts:
        return "قسطی ثبت نشده."

    lines = ["📋 اقساط:"]
    for i in insts:
        status_icon = "✅" if i.status == "پرداخت شده" else "🔴"
        due = to_jalali_str(i.due_date) if i.due_date else "—"
        lines.append(f"{status_icon} قسط {i.installment_number} — {format_amount(int(i.amount))} — سررسید: {due} — {i.status}")
    return "\n".join(lines)


async def pay_installment(session: AsyncSession, tenant_id: int,
                           invoice_display_id: str, installment_number: int) -> str:
    inv = await session.scalar(
        select(Invoice).where(
            Invoice.tenant_id == tenant_id,
            Invoice.display_id == invoice_display_id,
        )
    )
    if not inv:
        return f"⚠️ فاکتور «{invoice_display_id}» پیدا نشد."

    inst = await session.scalar(
        select(Installment).where(
            Installment.invoice_id == inv.id,
            Installment.installment_number == installment_number,
        )
    )
    if not inst:
        return f"⚠️ قسط شماره {installment_number} پیدا نشد."

    inst.status = "پرداخت شده"
    inst.payment_date = date.today()
    inv.paid = (inv.paid or 0) + float(inst.amount)
    inv.remaining_debt = max(0, (inv.remaining_debt or 0) - float(inst.amount))
    await session.commit()

    return f"✅ قسط {installment_number} فاکتور {invoice_display_id} پرداخت شد."


async def overdue_installments(session: AsyncSession, tenant_id: int) -> str:
    today = date.today()
    insts = (await session.scalars(
        select(Installment).where(
            Installment.tenant_id == tenant_id,
            Installment.due_date < today,
            Installment.status == "پرداخت نشده",
        ).order_by(Installment.due_date)
    )).all()

    if not insts:
        return "✅ قسط سررسید گذشته‌ای نداری."

    lines = [f"🔴 {len(insts)} قسط سررسید گذشته:"]
    for i in insts:
        due = to_jalali_str(i.due_date) if i.due_date else "—"
        lines.append(f"• قسط {i.installment_number} — {format_amount(int(i.amount))} — سررسید: {due}")
    return "\n".join(lines)
