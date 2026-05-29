"""
سرویس خروجی دسته‌جمعی — PDF/Excel/فیش/فاکتور چندتایی با امکان zip.
"""
import io
import zipfile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.models.business import Employee, Customer, Invoice
from app.modules.reports.settlement_engine import SettlementInput, calculate_settlement
from app.modules.reports.settlement_pdf import generate_settlement_pdf


async def batch_settlement(session: AsyncSession, tenant_id: int,
                            year: int, month_start: int, month_end: int = None,
                            employee_names: list[str] = None,
                            mode: str = "auto",
                            output_format: str = "zip") -> tuple[io.BytesIO | None, str, str, list]:
    """
    فیش تصفیه دسته‌جمعی.

    output_format: "zip" → یه zip، "separate" → لیست فایل‌ها
    Returns: (buffer, filename, message, files_list)
    """
    from app.modules.reports.settlement_service import _find_employee, _get_employer_name
    from app.modules.reports.settlement_engine import DAYS_IN_MONTH
    from app.utils.jalali_core import today_jalali

    if not month_end:
        month_end = month_start
    if not year:
        year = today_jalali()[0]

    employer = await _get_employer_name(session, tenant_id)

    # پیدا کردن کارمندان
    if employee_names:
        employees = []
        for name in employee_names:
            emp = await _find_employee(session, tenant_id, name)
            if emp:
                employees.append(emp)
    else:
        employees = (await session.scalars(
            select(Employee).where(Employee.tenant_id == tenant_id)
        )).all()

    if not employees:
        return None, "", "⚠️ کارمندی پیدا نشد.", []

    files = []
    errors = []

    for emp in employees:
        try:
            day_end = DAYS_IN_MONTH.get(month_end, 30)
            work_days = day_end

            inp = SettlementInput(
                employee_name=emp.name,
                national_id=emp.national_id or "",
                employer_name=employer,
                work_type=getattr(emp, 'work_mode', None) or "تمام وقت",
                year=year,
                month_start=month_start, day_start=1,
                month_end=month_end, day_end=day_end,
                work_days=work_days,
                marital_status=emp.marital_status or "مجرد",
                children_status="فاقد فرزند",
                shift_type=emp.shift_type or "",
            )

            result = calculate_settlement(inp)
            pdf_buf, fname = generate_settlement_pdf(result)
            files.append((pdf_buf, fname))
        except Exception as e:
            errors.append(f"❌ {emp.name}: {e}")

    if not files:
        return None, "", "⚠️ هیچ فیشی تولید نشد.\n" + "\n".join(errors), []

    if output_format == "zip":
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, 'w', zipfile.ZIP_DEFLATED) as zf:
            for pdf_buf, fname in files:
                pdf_buf.seek(0)
                zf.writestr(fname, pdf_buf.read())
        zip_buf.seek(0)
        zip_name = f"فیش_تصفیه_دسته‌جمعی_{year}_{month_start:02d}.zip"
        msg = f"📦 {len(files)} فیش تصفیه در یک zip آماده شد."
        if errors:
            msg += "\n" + "\n".join(errors)
        return zip_buf, zip_name, msg, files
    else:
        msg = f"📄 {len(files)} فیش تصفیه آماده ارسال."
        if errors:
            msg += "\n" + "\n".join(errors)
        return None, "", msg, files


async def batch_export(session: AsyncSession, tenant_id: int,
                        export_type: str, filters: dict = None,
                        output_format: str = "zip") -> tuple[io.BytesIO | None, str, str, list]:
    """
    خروجی دسته‌جمعی عمومی.
    export_type: settlement, invoice_pdf, invoice_excel, employee_excel, customer_excel
    """
    if export_type == "settlement":
        return await batch_settlement(
            session, tenant_id,
            year=filters.get("year"),
            month_start=filters.get("month_start", 1),
            month_end=filters.get("month_end"),
            employee_names=filters.get("employee_names"),
            output_format=output_format,
        )

    # بقیه export typeها در آپدیت‌های بعدی
    return None, "", f"⚠️ نوع «{export_type}» هنوز پشتیبانی نمی‌شود.", []
