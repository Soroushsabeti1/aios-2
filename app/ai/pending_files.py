"""
مدیریت فایل‌های در انتظار ارسال به کاربر.
وقتی یک tool فایلی تولید می‌کند (مثلاً اکسل)، اینجا ذخیره می‌شود
و بعد از پاسخ متنی به کاربر ارسال می‌شود.
"""
import io
from collections import defaultdict

_pending: dict[int, list[tuple[io.BytesIO, str]]] = defaultdict(list)


def add_file(user_id: int, buffer: io.BytesIO, filename: str):
    """یک فایل به صف ارسال اضافه می‌کند."""
    _pending[user_id].append((buffer, filename))


def pop_files(user_id: int) -> list[tuple[io.BytesIO, str]]:
    """همه فایل‌های در انتظار را برمی‌گرداند و صف را خالی می‌کند."""
    return _pending.pop(user_id, [])


def peek_files(user_id: int) -> list[tuple[io.BytesIO, str]]:
    """فایل‌ها را بدون پاک کردن برمی‌گرداند."""
    return _pending.get(user_id, [])
