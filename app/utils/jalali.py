"""
موتور تاریخ شمسی هوشمند.

ورودی را به هر شکلی که کاربر بگوید می‌فهمد:
- «۱۴۰۵/۰۸/۱۷»
- «۱۷ آبان» یا «۱۷ام آبان ۱۴۰۵»
- «برج ۲» → ماه دوم (اردیبهشت)

ذخیره: تاریخ میلادی واقعی (date) تا قابل محاسبه و شمارش باشد.
نمایش: همیشه شمسی.
"""
import re
from datetime import datetime, date
from app.utils.jalali_core import (
    jalali_to_gregorian, gregorian_to_jalali, today_jalali,
)

_PERSIAN_MONTHS = {
    "فروردین": 1, "اردیبهشت": 2, "خرداد": 3, "تیر": 4,
    "مرداد": 5, "امرداد": 5, "شهریور": 6, "مهر": 7,
    "آبان": 8, "ابان": 8, "آذر": 9, "اذر": 9, "دی": 10,
    "بهمن": 11, "اسفند": 12,
}

_FA_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def _norm(text: str) -> str:
    return text.translate(_FA_DIGITS).replace("ي", "ی").replace("ك", "ک").strip()


def parse_jalali(text: str, default_year: int = None) -> date | None:
    """متن تاریخ را به date میلادی تبدیل می‌کند (برای ذخیره)."""
    text = _norm(text)
    if default_year is None:
        default_year = today_jalali()[0]

    m = re.search(r"(\d{4})[/\-.](\d{1,2})[/\-.](\d{1,2})", text)
    if m:
        return _safe(int(m.group(1)), int(m.group(2)), int(m.group(3)))

    m = re.search(r"(?:برج|ماه)\s*(\d{1,2})", text)
    if m:
        mo = int(m.group(1))
        if 1 <= mo <= 12:
            return _safe(default_year, mo, 1)

    for month_name, month_num in _PERSIAN_MONTHS.items():
        if month_name in text:
            day_match = re.search(r"(\d{1,2})\s*(?:ام|م)?\s*" + month_name, text)
            day = int(day_match.group(1)) if day_match else 1
            year_match = re.search(r"(\d{4})", text)
            year = int(year_match.group(1)) if year_match else default_year
            return _safe(year, month_num, day)

    m = re.search(r"(\d{4})[/\-.](\d{1,2})", text)
    if m:
        return _safe(int(m.group(1)), int(m.group(2)), 1)

    return None


def _safe(jy: int, jm: int, jd: int) -> date | None:
    try:
        if not (1 <= jm <= 12 and 1 <= jd <= 31):
            return None
        return jalali_to_gregorian(jy, jm, jd)
    except Exception:
        return None


def to_jalali_str(g) -> str:
    """تاریخ میلادی ذخیره‌شده → رشته‌ی شمسی برای نمایش."""
    if g is None:
        return ""
    if isinstance(g, datetime):
        g = g.date()
    jy, jm, jd = gregorian_to_jalali(g)
    return f"{jy:04d}/{jm:02d}/{jd:02d}"


def today_jalali_str() -> str:
    jy, jm, jd = today_jalali()
    return f"{jy:04d}/{jm:02d}/{jd:02d}"


def days_since(g) -> int:
    if g is None:
        return None
    if isinstance(g, datetime):
        g = g.date()
    return (date.today() - g).days
