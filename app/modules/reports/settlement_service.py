"""
سرویس فیش تصفیه حساب — رابط بین دیتابیس و موتور محاسبه.

چهار حالت:
  mode=auto   : از Employee + WorkLog (حالت ۱)
  mode=amount : مبلغ کل وارد شده (حالت ۲ و ۳)
  mode=manual : همه سلول‌ها دستی (حالت ۴)
"""
from __future__ import annotations
import io
import re
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.business import Employee, WorkLog
from app.database.models.tenant import Tenant
from app.utils.jalali import to_jalali_str
from app.utils.jalali_core import gregorian_to_jalali, today_jalali
from app.modules.reports.settlement_engine import (
    SettlementInput, SettlementResult,
    calculate_settlement, calculate_from_total,
    settlement_text_summary,
)
from app.modules.reports.settlement_pdf import generate_settlement_pdf


async def _find_employee(session: AsyncSession, tenant_id: int,
                          name: str) -> Employee | None:
    """جستجوی کارمند با نام (جزئی)."""
    stmt = select(Employee).where(
        Employee.tenant_id == tenant_id,
        Employee.name.ilike(f"%{name}%"),
    ).limit(1)
    return await session.scalar(stmt)


async def _get_employer_name(session: AsyncSession, tenant_id: int) -> str:
    tenant = await session.get(Tenant, tenant_id)
    if not tenant:
        return "کارفرما"
    return tenant.name or "کارفرما"


def _parse_children(count: int, status: str = None) -> str:
    if status:
        return status
    if count == 0:
        return "فاقد فرزند"
    if count == 1:
        return "یک فرزند"
    if count == 2:
        return "دو فرزند"
    return "سه فرزند"


async def generate_settlement(
    session: AsyncSession,
    tenant_id: int,
    user_id: int,
    employee_name: str,
    mode: str = "auto",
    year: int = None,
    month_start: int = None,
    day_start: int = None,
    month_end: int = None,
    day_end: int = None,
    total_amount: float = None,
    work_hours: float = 0,
    overtime_hours: float = 0,
    night_hours: float = 0,
    holiday_days: float = 0,
    friday_days: float = 0,
    leave_used: float = 0,
    unused_leave: float = 0,
    repair_wage: float = 0,
    loan_deduction: float = 0,
    work_days: int = 0,
    shift_type: str = "",
    marital_status: str = "",
    children_status: str = "",
    work_type: str = "",
) -> tuple[io.BytesIO | None, str, str]:
    """
    تولید فیش تصفیه حساب.

    Returns: (pdf_buffer, filename, message)
    اگه خطا داشت pdf_buffer=None و message حاوی خطاست.
    """
    # پیدا کردن کارمند
    emp = await _find_employee(session, tenant_id, employee_name)
    if not emp:
        return None, "", f"⚠️ کارمندی با نام «{employee_name}» پیدا نشد."

    employer = await _get_employer_name(session, tenant_id)
    cur_year, cur_month, cur_day = today_jalali()

    # تنظیم سال و تاریخ
    if not year:
        year = cur_year
    if not month_start:
        month_start = cur_month
    if not day_start:
        day_start = 1
    if not month_end:
        month_end = month_start
    if not day_end:
        # روز آخر ماه
        from app.modules.reports.settlement_engine import DAYS_IN_MONTH
        day_end = DAYS_IN_MONTH.get(month_end, 30)

    # تعداد روز
    if work_days <= 0:
        work_days = day_end - day_start + 1

    # ساخت ورودی پایه
    inp = SettlementInput(
        employee_name=emp.name,
        national_id=emp.national_id or "",
        employee_code=emp.code or emp.display_id or "",
        employer_name=employer,
        work_type=work_type or (emp.work_mode if emp.work_mode in ("تمام وقت", "پاره وقت") else "تمام وقت"),
        year=year,
        month_start=month_start,
        day_start=day_start,
        month_end=month_end,
        day_end=day_end,
        work_days=work_days,
        marital_status=marital_status or emp.marital_status or "مجرد",
        children_status=children_status or _parse_children(emp.children_count or 0),
        shift_type=shift_type or emp.shift_type or "",
        leave_used=leave_used,
        unused_leave=unused_leave,
        repair_wage=repair_wage,
        loan_deduction=loan_deduction,
    )

    # تاریخ‌های شروع کار و بیمه
    if emp.hire_date:
        inp.hire_date_str = to_jalali_str(emp.hire_date)
    if emp.insurance_start:
        inp.insurance_start_str = to_jalali_str(emp.insurance_start)

    if mode == "auto":
        # ─── حالت ۱: از دیتابیس ───
        # خلاصه WorkLog‌ها در بازه زمانی
        from app.utils.jalali_core import jalali_to_gregorian
        try:
            g_start = jalali_to_gregorian(year, month_start, day_start)
            g_end = jalali_to_gregorian(year, month_end, day_end)
        except Exception:
            g_start = g_end = None

        if g_start and g_end:
            stmt = select(
                func.sum(WorkLog.work_hours),
                func.sum(WorkLog.overtime_hours),
                func.sum(WorkLog.night_hours),
                func.sum(WorkLog.friday_work),
                func.sum(WorkLog.unused_leave),
                func.count(WorkLog.id),
            ).where(
                WorkLog.tenant_id == tenant_id,
                WorkLog.employee_id == emp.id,
                WorkLog.work_date >= g_start,
                WorkLog.work_date <= g_end,
            )
            row = (await session.execute(stmt)).first()
            if row and row[5] > 0:
                inp.work_hours = float(row[0] or 0)
                inp.overtime_hours = overtime_hours or float(row[1] or 0)
                inp.night_hours = night_hours or float(row[2] or 0)
                inp.friday_days = friday_days or float(row[3] or 0)
                inp.unused_leave = unused_leave or float(row[4] or 0)
            else:
                # WorkLog نداره — از ساعت دستی یا پیش‌فرض
                inp.work_hours = work_hours
                inp.overtime_hours = overtime_hours
                inp.night_hours = night_hours
                inp.friday_days = friday_days
                inp.holiday_days = holiday_days
        else:
            inp.work_hours = work_hours
            inp.overtime_hours = overtime_hours
            inp.night_hours = night_hours
            inp.friday_days = friday_days
            inp.holiday_days = holiday_days

        result = calculate_settlement(inp)

    elif mode == "amount":
        # ─── حالت ۲ و ۳: از مبلغ ───
        # مبلغ از system prompt به ریال تبدیل شده (AI تومان×۱۰ می‌کنه)
        # ولی اگه خیلی کوچیکه احتمالاً تومانه
        amt = total_amount or 0
        if 0 < amt < 50_000_000:
            # احتمالاً تومانه — تبدیل به ریال
            amt = amt * 10
        inp.total_paid = amt
        inp.work_hours = work_hours
        inp.overtime_hours = overtime_hours
        inp.night_hours = night_hours
        inp.friday_days = friday_days
        inp.holiday_days = holiday_days
        result = calculate_from_total(inp)

    else:
        # ─── حالت ۴: دستی ───
        inp.work_hours = work_hours
        inp.overtime_hours = overtime_hours
        inp.night_hours = night_hours
        inp.friday_days = friday_days
        inp.holiday_days = holiday_days
        result = calculate_settlement(inp)

    # تولید PDF
    try:
        pdf_buf, fname = generate_settlement_pdf(result)
    except Exception as e:
        summary = settlement_text_summary(result)
        return None, "", f"⚠️ خطا در تولید PDF: {e}\n\n{summary}"

    summary = settlement_text_summary(result)
    return pdf_buf, fname, summary
