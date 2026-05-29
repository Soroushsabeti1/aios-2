"""
سرویس بکاپ — خروجی کامل دیتابیس یک tenant یا کل سیستم.
"""
import io
import json
import zipfile
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.business import (
    Employee, Customer, Product, Invoice, InvoiceItem, Installment,
    Expense, WorkLog, SalaryPayment,
)
from app.database.models.tenant import Tenant
from app.modules.reports import excel_service
from app.utils.jalali import to_jalali_str


async def _export_table_json(session, model, tenant_id: int) -> list[dict]:
    """یک جدول رو به لیست dict تبدیل کن."""
    rows = (await session.scalars(
        select(model).where(model.tenant_id == tenant_id)
    )).all()
    result = []
    for row in rows:
        d = {}
        for col in row.__table__.columns:
            val = getattr(row, col.name, None)
            if val is None:
                d[col.name] = None
            elif isinstance(val, (datetime,)):
                d[col.name] = val.isoformat()
            elif isinstance(val, bytes):
                d[col.name] = f"<binary {len(val)} bytes>"
            else:
                try:
                    d[col.name] = float(val) if hasattr(val, '__float__') and not isinstance(val, (int, str)) else val
                except (TypeError, ValueError):
                    d[col.name] = str(val)
        result.append(d)
    return result


async def backup_tenant(session: AsyncSession, tenant_id: int) -> tuple[io.BytesIO, str]:
    """بکاپ کامل یک tenant — zip حاوی JSON + Excel."""
    tenant = await session.get(Tenant, tenant_id)
    tenant_name = tenant.name if tenant else f"tenant_{tenant_id}"

    tables = {
        "employees": Employee,
        "customers": Customer,
        "products": Product,
        "invoices": Invoice,
        "invoice_items": InvoiceItem,
        "expenses": Expense,
        "work_logs": WorkLog,
        "salary_payments": SalaryPayment,
    }

    # اگه Installment وجود داره
    try:
        tables["installments"] = Installment
    except Exception:
        pass

    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        # JSON بکاپ
        backup_data = {"tenant_name": tenant_name, "backup_date": datetime.now(timezone.utc).isoformat()}
        for name, model in tables.items():
            try:
                data = await _export_table_json(session, model, tenant_id)
                backup_data[name] = data
            except Exception:
                backup_data[name] = []

        zf.writestr("backup.json", json.dumps(backup_data, ensure_ascii=False, indent=2, default=str))

        # Excel‌ها
        for data_type in ["employees", "customers", "products", "invoices"]:
            try:
                exporter = excel_service.EXPORTERS.get(data_type)
                if exporter:
                    buf, fname = await exporter(session, tenant_id)
                    buf.seek(0)
                    zf.writestr(f"excel/{fname}", buf.read())
            except Exception:
                pass

    zip_buf.seek(0)
    fname = f"backup_{tenant_name}_{datetime.now().strftime('%Y%m%d_%H%M')}.zip"
    return zip_buf, fname


async def backup_full_system(session: AsyncSession) -> tuple[io.BytesIO, str]:
    """بکاپ کل سیستم — همه tenantها."""
    tenants = (await session.scalars(select(Tenant))).all()

    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for tenant in tenants:
            try:
                t_buf, t_fname = await backup_tenant(session, tenant.id)
                t_buf.seek(0)
                zf.writestr(f"{tenant.name}/{t_fname}", t_buf.read())
            except Exception:
                pass

    zip_buf.seek(0)
    fname = f"full_backup_{datetime.now().strftime('%Y%m%d_%H%M')}.zip"
    return zip_buf, fname
