"""
ابزار نرمال‌سازی متن و اعداد فارسی.
عدد فارسی، انگلیسی، حروفی و واحدهای پولی (تومن، هزار، میلیون) را به عدد خام تبدیل می‌کند.
"""
import re

# نگاشت ارقام فارسی/عربی به انگلیسی
_PERSIAN_DIGITS = "۰۱۲۳۴۵۶۷۸۹"
_ARABIC_DIGITS = "٠١٢٣٤٥٦٧٨٩"
_ENGLISH_DIGITS = "0123456789"

_DIGIT_MAP = {}
for fa, en in zip(_PERSIAN_DIGITS, _ENGLISH_DIGITS):
    _DIGIT_MAP[fa] = en
for ar, en in zip(_ARABIC_DIGITS, _ENGLISH_DIGITS):
    _DIGIT_MAP[ar] = en

# اعداد حروفی فارسی
_WORD_NUMBERS = {
    "صفر": 0, "یک": 1, "دو": 2, "سه": 3, "چهار": 4, "پنج": 5,
    "شش": 6, "شیش": 6, "هفت": 7, "هشت": 8, "نه": 9, "ده": 10,
    "یازده": 11, "دوازده": 12, "سیزده": 13, "چهارده": 14, "پانزده": 15,
    "پونزده": 15, "شانزده": 16, "شونزده": 16, "هفده": 17, "هجده": 18,
    "هیجده": 18, "نوزده": 19, "بیست": 20, "سی": 30, "چهل": 40,
    "پنجاه": 50, "شصت": 60, "هفتاد": 70, "هشتاد": 80, "نود": 90,
    "صد": 100, "یکصد": 100, "دویست": 200, "سیصد": 300, "چهارصد": 400,
    "پانصد": 500, "پونصد": 500, "ششصد": 600, "هفتصد": 700, "هشتصد": 800,
    "نهصد": 900,
}

_MULTIPLIERS = {
    "هزار": 1_000,
    "میلیون": 1_000_000,
    "ملیون": 1_000_000,
    "میلیارد": 1_000_000_000,
    "ملیارد": 1_000_000_000,
    "تومن": 1, "تومان": 1, "ت": 1,  # واحد پول، ضریب ندارد
}

_CURRENCY_WORDS = {"تومن", "تومان", "ت", "ریال"}


def normalize_digits(text: str) -> str:
    """ارقام فارسی/عربی را به انگلیسی تبدیل می‌کند."""
    return "".join(_DIGIT_MAP.get(ch, ch) for ch in text)


def normalize_text(text: str) -> str:
    """نرمال‌سازی کلی متن: ارقام، ي/ك عربی، فاصله‌ها."""
    text = normalize_digits(text)
    text = text.replace("ي", "ی").replace("ك", "ک")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def parse_amount(text: str) -> int | None:
    """
    مبلغ را از متن استخراج می‌کند.
    مثال‌ها:
        "۶۰۰ هزار" → 600000
        "600000" → 600000
        "۲ میلیون و ۵۰۰" → 2000500
        "پانصد هزار تومن" → 500000
        "سه میلیون" → 3000000
    """
    text = normalize_text(text)
    has_digit = bool(re.search(r"\d", text))

    if has_digit:
        # حالت ۱: عدد خام چسبیده به ضریب — مثل "۶۰۰ هزار" یا "2.5 میلیون"
        for word, mult in _MULTIPLIERS.items():
            if mult == 1:
                continue
            pattern = rf"([\d.,]+)\s*{word}"
            m = re.search(pattern, text)
            if m:
                num_str = m.group(1).replace(",", "")
                try:
                    base = float(num_str)
                    return int(base * mult)
                except ValueError:
                    pass

        # حالت ۲: فقط عدد خام
        m = re.search(r"[\d,]+", text)
        if m:
            try:
                return int(m.group(0).replace(",", ""))
            except ValueError:
                pass

    # حالت ۳: عدد حروفی (وقتی رقم انگلیسی نداریم یا حالت‌های بالا جواب نداد)
    result = _parse_word_number(text)
    if result is not None:
        return result

    return None


def _parse_word_number(text: str) -> int | None:
    """
    عدد حروفی فارسی را پارس می‌کند.
    'سه میلیون' → 3000000
    'دو میلیون و پانصد هزار' → 2500000
    """
    # «و» را به فاصله تبدیل می‌کنیم تا توکن‌ها جدا شوند
    tokens = re.sub(r"\bو\b", " ", text).split()

    total = 0      # مجموع نهایی
    segment = 0    # بخش در حال ساخت (قبل از رسیدن به ضریب بزرگ)
    found = False

    for token in tokens:
        if token in _WORD_NUMBERS:
            segment += _WORD_NUMBERS[token]
            found = True
        elif token in _MULTIPLIERS and _MULTIPLIERS[token] > 1:
            mult = _MULTIPLIERS[token]
            if segment == 0:
                segment = 1
            # کل بخش جاری در ضریب ضرب و به total اضافه می‌شود
            total += segment * mult
            segment = 0
            found = True
        elif token in _CURRENCY_WORDS:
            continue
        # توکن‌های نامرتبط (مثل اسم کالا) نادیده گرفته می‌شوند

    total += segment
    return total if found and total > 0 else None


def format_amount(amount: int, currency: str = "toman") -> str:
    """عدد را با جداکننده هزارگان و واحد پول نمایش می‌دهد."""
    formatted = f"{amount:,}"
    unit = "تومان" if currency == "toman" else "ریال"
    return f"{formatted} {unit}"
