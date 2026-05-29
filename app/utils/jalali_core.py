"""
الگوریتم تبدیل شمسی ↔ میلادی (مستقل، بدون نیاز به کتابخانه‌ی خارجی).

این پیاده‌سازی بر پایه‌ی الگوریتم استاندارد تبدیل تقویم جلالی است.
دلیل پیاده‌سازی مستقل: حذف وابستگی و امکان تست کامل.
"""
from datetime import date, timedelta

_G_DAYS_IN_MONTH = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
_J_DAYS_IN_MONTH = [31, 31, 31, 31, 31, 31, 30, 30, 30, 30, 30, 29]


def _is_jalali_leap(jy: int) -> bool:
    # الگوریتم ۳۳ساله‌ی تقریبی استاندارد
    return (((jy - 979) % 33) % 4) == 1 or _jalali_leap_precise(jy)


def _jalali_leap_precise(jy: int) -> bool:
    # روش دقیق‌تر بر اساس باقیمانده
    breaks = [-61, 9, 38, 199, 426, 686, 756, 818, 1111, 1181, 1210,
              1635, 2060, 2097, 2192, 2262, 2324, 2394, 2456, 3178]
    gy = jy + 621
    leap_j = -14
    jp = breaks[0]
    jump = 0
    for j in range(1, len(breaks)):
        jm = breaks[j]
        jump = jm - jp
        if jy < jm:
            break
        leap_j += (jump // 33) * 8 + (jump % 33) // 4
        jp = jm
    n = jy - jp
    leap_j += (n // 33) * 8 + ((n % 33) + 3) // 4
    if (jump % 33) == 4 and (jump - n) == 4:
        leap_j += 1
    leap_g = (gy // 4) - ((gy // 100 + 1) * 3 // 4) - 150
    march = 20 + leap_j - leap_g
    if (jump - n) < 6:
        n = n - jump + ((jump + 4) // 33) * 33
    leap = (((n + 1) % 33) - 1) % 4
    if leap == -1:
        leap = 4
    return leap == 0


def jalali_to_gregorian(jy: int, jm: int, jd: int) -> date:
    """شمسی → میلادی"""
    jy += 1595
    days = -355668 + (365 * jy) + ((jy // 33) * 8) + (((jy % 33) + 3) // 4) + jd
    if jm < 7:
        days += (jm - 1) * 31
    else:
        days += ((jm - 7) * 30) + 186
    gy = 400 * (days // 146097)
    days %= 146097
    if days > 36524:
        days -= 1
        gy += 100 * (days // 36524)
        days %= 36524
        if days >= 365:
            days += 1
    gy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        gy += (days - 1) // 365
        days = (days - 1) % 365
    gd = days + 1
    leap = (gy % 4 == 0 and gy % 100 != 0) or (gy % 400 == 0)
    months = [31, 29 if leap else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    gm = 0
    while gm < 12 and gd > months[gm]:
        gd -= months[gm]
        gm += 1
    return date(gy, gm + 1, gd)


def gregorian_to_jalali(g: date) -> tuple[int, int, int]:
    """میلادی → شمسی (jy, jm, jd)"""
    gy, gm, gd = g.year, g.month, g.day
    g_d_m = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    gy2 = gy - 1600
    gm2 = gm - 1
    gd2 = gd - 1
    g_day_no = 365 * gy2 + (gy2 + 3) // 4 - (gy2 + 99) // 100 + (gy2 + 399) // 400
    g_day_no += g_d_m[gm2] + gd2
    if gm2 > 1 and ((gy % 4 == 0 and gy % 100 != 0) or (gy % 400 == 0)):
        g_day_no += 1
    j_day_no = g_day_no - 79
    j_np = j_day_no // 12053
    j_day_no %= 12053
    jy = 979 + 33 * j_np + 4 * (j_day_no // 1461)
    j_day_no %= 1461
    if j_day_no >= 366:
        jy += (j_day_no - 1) // 365
        j_day_no = (j_day_no - 1) % 365
    if j_day_no < 186:
        jm = 1 + j_day_no // 31
        jd = 1 + j_day_no % 31
    else:
        jm = 7 + (j_day_no - 186) // 30
        jd = 1 + (j_day_no - 186) % 30
    return jy, jm, jd


def today_jalali() -> tuple[int, int, int]:
    return gregorian_to_jalali(date.today())
