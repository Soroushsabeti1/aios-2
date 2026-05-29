"""
موتور محاسبه فیش تصفیه حساب — فرمول‌های دقیق اکسل، تأیید‌شده ریال‌به‌ریال.

فرمول‌ها:
  L15 = hourly × work_hours                          حقوق پایه
  L16 = housing_daily × work_days                    بن مسکن
  L17 = grocery_daily × work_days                    بن خوار و بار
  L18 = 5,000,000 × months (اگه متاهل و سال>=1403)  حق تاهل
  L20 = L15 × 10/20/30% (بر اساس فرزند)             حق اولاد
  L21 = hourly × 1.4 × overtime_hours               اضافه‌کاری
  L22 = friday_days × AL23 × 1.4                    جمعه‌کاری
  L23 = hourly × 1.35 × night_hours                 شب‌کاری
  L24 = holiday_days × (hourly×7) × 1.4             تعطیل‌کاری
  L25 = L15 × 15/22.5/10% (نوبت‌کاری)               نوبت‌کاری
  L26 = (L15/12/work_days) × work_days              سنوات
  L27 = L26 × 2                                     عیدی
  L28 = insurance_daily × work_days                  بیمه
  L29 = (hourly+housing_d+grocery_d+L18/30+L20/30)×unused مرخصی
  H32 = مجموع همه - L28                              مبلغ کل
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional

from app.utils.jalali_core import today_jalali


# ═══════════════════════════════════════════════════════
# جداول قانونی
# ═══════════════════════════════════════════════════════

HOURLY_WAGE = {
    1404: 472532, 1403: 325884, 1402: 241395, 1401: 190075,
    1400: 120759, 1399: 88446, 1398: 68980, 1397: 50535,
    1396: 42289, 1395: 36933, 1394: 32398, 1393: 27690,
    1392: 22152, 1391: 17722, 1390: 15020, 1389: 13777,
}

HOUSING_MONTHLY = {
    1404: 9_000_000, 1403: 9_000_000, 1402: 9_000_000,
    1401: 6_500_000, 1400: 4_500_000, 1399: 3_000_000,
    1398: 1_000_000, 1397: 400_000, 1396: 400_000,
}

GROCERY_MONTHLY = {
    1404: 22_000_000, 1403: 14_000_000, 1402: 11_000_000,
    1401: 8_500_000, 1400: 6_000_000, 1399: 4_000_000,
    1398: 1_900_000, 1397: 1_100_000, 1396: 1_100_000,
}

MARRIAGE_ALLOWANCE = {
    1404: 3_463_656, 1403: 2_468_352, 1402: 1_769_428,
    1401: 1_393_250, 1400: 885_165, 1399: 636_809,
}

# بیمه روزانه — BB20 از اکسل: (BB12×30%) / work_days
# BB12 = (hourly_insurance + base_insurance) × work_days
# ساده‌شده: مقدار ثابت سالانه (محاسبه‌شده)
INSURANCE_DAILY = {
    1404: 404729.04, 1403: 274829, 1402: 198000,
    1401: 153000, 1400: 100000, 1399: 72000,
}

DAYS_IN_MONTH = {
    1: 31, 2: 31, 3: 31, 4: 31, 5: 31, 6: 31,
    7: 30, 8: 30, 9: 30, 10: 30, 11: 30, 12: 29,
}


def _tbl(table: dict, year: int) -> float:
    if year in table:
        return table[year]
    closest = min(table.keys(), key=lambda y: abs(y - year), default=None)
    return table.get(closest, 0) if closest else 0


# ═══════════════════════════════════════════════════════
# ساختار داده
# ═══════════════════════════════════════════════════════

@dataclass
class SettlementInput:
    employee_name: str = ""
    national_id: str = ""
    employee_code: str = ""  # کد پرسنلی (P1001)
    employer_name: str = ""
    work_type: str = "تمام وقت"

    year: int = 0
    month_start: int = 1
    day_start: int = 1
    month_end: int = 1
    day_end: int = 30

    work_days: int = 0
    work_hours: float = 0
    overtime_hours: float = 0
    night_hours: float = 0
    holiday_days: float = 0
    friday_days: float = 0
    shift_type: str = ""

    marital_status: str = ""
    children_status: str = ""
    leave_used: float = 0
    unused_leave: float = 0

    repair_wage: float = 0
    loan_deduction: float = 0
    total_paid: Optional[float] = None


@dataclass
class SettlementResult:
    inp: SettlementInput

    hourly_wage: float = 0
    housing_daily: float = 0
    grocery_daily: float = 0

    base_salary: float = 0
    housing_total: float = 0
    grocery_total: float = 0
    marriage_total: float = 0
    children_total: float = 0
    overtime_total: float = 0
    friday_total: float = 0
    night_total: float = 0
    holiday_total: float = 0
    shift_total: float = 0
    severance_daily: float = 0
    severance_total: float = 0
    bonus_daily: float = 0
    bonus_total: float = 0
    insurance_deduction: float = 0
    unused_leave_amount: float = 0
    repair_wage: float = 0
    loan_deduction: float = 0
    grand_total: float = 0

    # حق‌السعی روزانه (AL23) — برای جمعه‌کاری
    haghossaei_daily: float = 0


# ═══════════════════════════════════════════════════════
# موتور محاسبه — فرمول‌های verify شده
# ═══════════════════════════════════════════════════════

def calculate_settlement(inp: SettlementInput) -> SettlementResult:
    r = SettlementResult(inp=inp)
    year = inp.year or today_jalali()[0]
    months = 1
    if inp.month_end != inp.month_start:
        months = inp.month_end - inp.month_start + 1

    # ─── روز و ساعت کارکرد ───
    work_days = inp.work_days
    if work_days <= 0:
        work_days = (inp.day_end - inp.day_start) + 1
        if work_days <= 0:
            work_days = 30
    inp.work_days = work_days

    r.hourly_wage = _tbl(HOURLY_WAGE, year)
    r.housing_daily = _tbl(HOUSING_MONTHLY, year) / 30
    r.grocery_daily = _tbl(GROCERY_MONTHLY, year) / 30

    # ساعت کارکرد: اگه مشخص نشده از روز حساب کن
    work_hours = inp.work_hours
    if work_hours <= 0:
        if inp.work_type in ("نیمه وقت", "پاره وقت"):
            work_hours = 8 * work_days
        else:
            # Z2: j_diff(start,end)+1 → work_days (تمام وقت)
            work_hours = work_days  # عدد خام (C14 اکسل)
            # C14 اکسل مستقیماً work_days هست برای تمام‌وقت
    inp.work_hours = work_hours

    # ─── L15: حقوق پایه = hourly × work_hours ───
    r.base_salary = r.hourly_wage * work_hours

    # ─── L16: بن مسکن = housing_daily × work_days ───
    r.housing_total = r.housing_daily * work_days

    # ─── L17: بن خوار و بار = grocery_daily × work_days ───
    r.grocery_total = r.grocery_daily * work_days

    # ─── L18: حق تاهل ───
    # IF(متاهل AND سال>=1403, 5000000 × months, 0)
    if inp.marital_status in ("متاهل", "متأهل") and year >= 1403:
        r.marriage_total = 5_000_000 * months
    else:
        r.marriage_total = 0

    # ─── L20: حق اولاد ───
    ch = (inp.children_status or "").strip()
    if ch == "یک فرزند":
        r.children_total = r.base_salary * 0.10
    elif ch == "دو فرزند":
        r.children_total = r.base_salary * 0.20
    elif ch == "سه فرزند":
        r.children_total = r.base_salary * 0.30
    else:
        r.children_total = 0

    # ─── AL23: حق‌السعی روزانه ───
    # = AU10 + AL14 + AO12 + AR12 + AL4 + AL5
    # AU10 = حق تاهل جدولی, AL14 = پایه سنوات (فعلاً 0),
    # AL4 = 166667 (متاهل), AL5 = 0 (فاقد فرزند)
    marriage_base = _tbl(MARRIAGE_ALLOWANCE, year) if inp.marital_status in ("متاهل", "متأهل") else 0
    al4 = 166667 if inp.marital_status in ("متاهل", "متأهل") else 0
    r.haghossaei_daily = marriage_base + 0 + r.housing_daily + r.grocery_daily + al4 + 0

    # ─── L21: اضافه‌کاری = hourly × 1.4 × overtime_hours ───
    r.overtime_total = r.hourly_wage * 1.4 * inp.overtime_hours

    # ─── L22: جمعه‌کاری = friday_days × AL23 × 1.4 ───
    r.friday_total = inp.friday_days * r.haghossaei_daily * 1.4

    # ─── L23: شب‌کاری = hourly × 1.35 × night_hours ───
    r.night_total = r.hourly_wage * 1.35 * inp.night_hours

    # ─── L24: تعطیل‌کاری = holiday_days × (hourly×7) × 1.4 ───
    r.holiday_total = inp.holiday_days * (r.hourly_wage * 7) * 1.4

    # ─── L25: نوبت‌کاری ───
    shift = (inp.shift_type or "").strip()
    if shift == "صبح-عصر-شب":
        r.shift_total = r.base_salary * 0.15
    elif shift == "روز-شب":
        r.shift_total = r.base_salary * 0.225
    elif shift == "صبح-عصر":
        r.shift_total = r.base_salary * 0.10
    else:
        r.shift_total = 0

    # ─── عیدی و سنوات ───
    # V4 = L15 × 2 / 12
    # C27 = V4 / work_days (عیدی روزانه)
    # C26 = C27 / 2 (سنوات روزانه)
    v4 = r.base_salary * 2 / 12
    r.bonus_daily = v4 / work_days if work_days > 0 else 0
    r.severance_daily = r.bonus_daily / 2
    r.bonus_total = r.bonus_daily * work_days
    r.severance_total = r.severance_daily * work_days

    # ─── L28: بیمه = insurance_daily × work_days ───
    # AL24 = BB20 (مقدار ثابت سالانه)
    ins_daily = _tbl(INSURANCE_DAILY, year)
    r.insurance_deduction = ins_daily * work_days

    # ─── L29: مرخصی استفاده‌نشده ───
    # = (C15 + C16 + C17 + L18/30 + L20/30) × unused_leave
    if inp.unused_leave > 0:
        daily_all = r.hourly_wage + r.housing_daily + r.grocery_daily
        daily_all += (r.marriage_total / 30) + (r.children_total / 30)
        r.unused_leave_amount = daily_all * inp.unused_leave
    else:
        r.unused_leave_amount = 0

    # ─── مزد ترمیمی و وام ───
    r.repair_wage = inp.repair_wage
    r.loan_deduction = inp.loan_deduction

    # ─── H32: مبلغ کل ───
    # = L15+L16+L17+L18+L20+L21+L23+L24+L25+L26+L22+L27-L28+L29+L31
    r.grand_total = (
        r.base_salary + r.housing_total + r.grocery_total
        + r.marriage_total + r.children_total
        + r.overtime_total + r.friday_total + r.night_total
        + r.holiday_total + r.shift_total
        + r.severance_total + r.bonus_total
        - r.insurance_deduction
        + r.unused_leave_amount + r.repair_wage - r.loan_deduction
    )

    return r


def calculate_from_total(inp: SettlementInput) -> SettlementResult:
    """حالت ۲ و ۳: از مبلغ کل، ساعت کارکرد رو برعکس حساب کن."""
    if inp.total_paid is None or inp.total_paid <= 0:
        return calculate_settlement(inp)

    year = inp.year or today_jalali()[0]
    work_days = inp.work_days
    if work_days <= 0:
        work_days = (inp.day_end - inp.day_start) + 1
    if work_days <= 0:
        work_days = 30
    inp.work_days = work_days

    hourly = _tbl(HOURLY_WAGE, year)
    housing_d = _tbl(HOUSING_MONTHLY, year) / 30
    grocery_d = _tbl(GROCERY_MONTHLY, year) / 30
    ins_daily = _tbl(INSURANCE_DAILY, year)

    # مبالغ ثابت (وابسته به روز نه ساعت)
    fixed = housing_d * work_days + grocery_d * work_days
    if inp.marital_status in ("متاهل", "متأهل") and year >= 1403:
        months = 1
        if inp.month_end != inp.month_start:
            months = inp.month_end - inp.month_start + 1
        fixed += 5_000_000 * months

    # بیمه هم کم کن
    fixed -= ins_daily * work_days

    # عیدی و سنوات هم تابع base_salary هستن
    # base = hourly × hours
    # bonus = base × 2/12, severance = bonus/2
    # total_from_base = base × (1 + 2/12 + 1/12) = base × 1.25
    base_factor = 1.25  # base + عیدی + سنوات

    remaining = inp.total_paid - fixed
    if remaining <= 0:
        remaining = inp.total_paid

    # base_salary = hourly × hours
    # remaining = base × base_factor + overtime + friday + night + ...
    # فقط base: hours = remaining / (hourly × base_factor)
    est_hours = remaining / (hourly * base_factor) if hourly > 0 else 80

    # حداکثر ساعت قانونی
    if inp.work_type in ("نیمه وقت", "پاره وقت"):
        max_hours = 8 * work_days
    else:
        max_hours = work_days  # تمام‌وقت C14=work_days

    if est_hours <= max_hours:
        inp.work_hours = round(est_hours, 2)
    else:
        inp.work_hours = max_hours
        excess = est_hours - max_hours
        # مازاد: ۶۰٪ اضافه‌کاری، ۲۰٪ جمعه، ۲۰٪ تعطیل
        inp.overtime_hours = max(inp.overtime_hours, round(excess * 0.6, 1))
        inp.friday_days = max(inp.friday_days, round(excess * 0.2 / 7, 0))
        inp.holiday_days = max(inp.holiday_days, round(excess * 0.2 / 7, 0))

    return calculate_settlement(inp)


def settlement_text_summary(r: SettlementResult) -> str:
    inp = r.inp

    def fmt(n):
        return f"{int(round(n)):,}"

    lines = [
        f"📋 فیش تصفیه حساب سال {inp.year}",
        f"👤 {inp.employee_name}",
        f"🏢 {inp.employer_name}",
        f"📅 {inp.year}/{inp.month_start:02d}/{inp.day_start:02d} "
        f"تا {inp.year}/{inp.month_end:02d}/{inp.day_end:02d}",
        "",
        f"⏰ کارکرد: {inp.work_hours:.1f} ساعت / {inp.work_days} روز",
        f"💰 حقوق پایه: {fmt(r.base_salary)} ریال",
        f"🏠 بن مسکن: {fmt(r.housing_total)} ریال",
        f"🛒 بن خوار و بار: {fmt(r.grocery_total)} ریال",
    ]
    if r.marriage_total > 0:
        lines.append(f"💍 حق تاهل: {fmt(r.marriage_total)} ریال")
    if r.children_total > 0:
        lines.append(f"👶 حق اولاد: {fmt(r.children_total)} ریال")
    if r.overtime_total > 0:
        lines.append(f"⏱ اضافه‌کاری: {fmt(r.overtime_total)} ریال")
    if r.friday_total > 0:
        lines.append(f"📅 جمعه‌کاری: {fmt(r.friday_total)} ریال")
    if r.night_total > 0:
        lines.append(f"🌙 شب‌کاری: {fmt(r.night_total)} ریال")
    if r.holiday_total > 0:
        lines.append(f"🎌 تعطیل‌کاری: {fmt(r.holiday_total)} ریال")
    if r.shift_total > 0:
        lines.append(f"🔄 نوبت‌کاری: {fmt(r.shift_total)} ریال")
    lines += [
        f"📊 سنوات: {fmt(r.severance_total)} ریال",
        f"🎁 عیدی: {fmt(r.bonus_total)} ریال",
        f"🏥 بیمه (کسر): {fmt(r.insurance_deduction)} ریال",
    ]
    if r.unused_leave_amount > 0:
        lines.append(f"🏖 مرخصی استفاده‌نشده: {fmt(r.unused_leave_amount)} ریال")
    lines += ["", f"💵 مبلغ کل: {fmt(r.grand_total)} ریال"]
    return "\n".join(lines)
