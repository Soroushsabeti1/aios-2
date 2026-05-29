"""
نگهداری اطلاعات زمان‌اجرای ربات.

یوزرنیم ربات هنگام راه‌اندازی به‌صورت خودکار از تلگرام گرفته می‌شود
(در post_init) و اینجا ذخیره می‌شود تا برای ساخت لینک دعوت در دسترس باشد.
این‌طوری کارفرما لازم نیست یوزرنیم را دستی تنظیم کند.
"""
from app.core.config import settings

# مقدار اولیه از config (در صورت نیاز)
_bot_username: str = settings.bot_username


def set_bot_username(username: str):
    """یوزرنیم ربات را ثبت می‌کند (هنگام راه‌اندازی)."""
    global _bot_username
    if username:
        _bot_username = username.lstrip("@")


def get_bot_username() -> str:
    """یوزرنیم فعلی ربات را برمی‌گرداند."""
    return _bot_username
