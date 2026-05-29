"""سرویس حذف اکانت و بکاپ."""
import io
import json
import zipfile
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


async def create_full_backup(session: AsyncSession, tenant_id: int) -> io.BytesIO:
    """بکاپ کامل همه اطلاعات tenant."""
    from app.database.models.business import (
        Employee, Customer, Product, Invoice, InvoiceItem,
        Installment, Expense, SalaryPayment, Person,
    )
    from app.database.models.tenant import Tenant

    tenant = await session.get(Tenant, tenant_id)

    def to_dict(obj):
        result = {}
        for c in obj.__table__.columns:
            val = getattr(obj, c.name)
            if isinstance(val, datetime):
                val = val.isoformat()
            result[c.name] = val
        return result

    backup = {
        "backup_date": datetime.now(timezone.utc).isoformat(),
        "tenant": to_dict(tenant) if tenant else {},
        "employees": [],
        "customers": [],
        "products": [],
        "invoices": [],
        "expenses": [],
    }

    for emp in (await session.scalars(select(Employee).where(Employee.tenant_id == tenant_id))).all():
        backup["employees"].append(to_dict(emp))

    for cust in (await session.scalars(select(Customer).where(Customer.tenant_id == tenant_id))).all():
        backup["customers"].append(to_dict(cust))

    for prod in (await session.scalars(select(Product).where(Product.tenant_id == tenant_id))).all():
        backup["products"].append(to_dict(prod))

    for inv in (await session.scalars(select(Invoice).where(Invoice.tenant_id == tenant_id))).all():
        backup["invoices"].append(to_dict(inv))

    for exp in (await session.scalars(select(Expense).where(Expense.tenant_id == tenant_id))).all():
        backup["expenses"].append(to_dict(exp))

    # ساخت ZIP
    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("backup.json", json.dumps(backup, ensure_ascii=False, indent=2))
    zip_buf.seek(0)
    return zip_buf


async def delete_tenant_account(session: AsyncSession, tenant_id: int) -> str:
    """حذف کامل اکانت کارفرما."""
    from app.database.models.tenant import Tenant
    tenant = await session.get(Tenant, tenant_id)
    if not tenant:
        return "⚠️ اکانت پیدا نشد."

    # غیرفعال کردن
    tenant.is_active = False
    tenant.subscription_status = "deleted"
    await session.commit()
    return "✅ اکانت حذف شد."
