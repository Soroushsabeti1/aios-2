"""
Rate limiter ساده — در حافظه.
جلوگیری از اسپم پیام توسط کاربر.
"""
import time
from collections import defaultdict

_user_timestamps: dict[int, list[float]] = defaultdict(list)

MAX_MESSAGES = 5       # حداکثر پیام
WINDOW_SECONDS = 10    # در بازه زمانی (ثانیه)
COOLDOWN_SECONDS = 15  # مدت انتظار بعد از محدودیت


def check_rate_limit(user_id: int) -> tuple[bool, str]:
    """
    بررسی محدودیت نرخ پیام.
    خروجی: (مجاز؟, پیام خطا)
    """
    now = time.time()
    timestamps = _user_timestamps[user_id]

    # پاکسازی timestamp‌های قدیمی
    _user_timestamps[user_id] = [t for t in timestamps if now - t < WINDOW_SECONDS]
    timestamps = _user_timestamps[user_id]

    if len(timestamps) >= MAX_MESSAGES:
        return False, f"⏳ یکم آروم‌تر! {COOLDOWN_SECONDS} ثانیه صبر کن بعد دوباره بفرست."

    _user_timestamps[user_id].append(now)
    return True, ""
