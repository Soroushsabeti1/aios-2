"""
نگهداری موقت آخرین فایل آپلودی کاربر (عکس) برای دسترسی toolها.

وقتی کاربر عکسی می‌فرستد، علاوه بر اینکه به AI داده می‌شود، اینجا هم
موقتاً نگه داشته می‌شود تا اگر AI خواست عکس را برای یک موجودیت ذخیره
کند (toolِ save_entity_photo)، به داده‌ی خام عکس دسترسی داشته باشد.
"""

# {user_id: (photo_bytes, mime)}
_current_upload: dict[int, tuple[bytes, str]] = {}


def set_upload(user_id: int, photo_bytes: bytes, mime: str = "image/jpeg"):
    """عکس فعلی کاربر را ثبت می‌کند."""
    _current_upload[user_id] = (photo_bytes, mime)


def get_upload(user_id: int) -> tuple[bytes, str] | None:
    """عکس فعلی کاربر را برمی‌گرداند (بدون پاک کردن)."""
    return _current_upload.get(user_id)


def clear_upload(user_id: int):
    """عکس فعلی کاربر را پاک می‌کند."""
    _current_upload.pop(user_id, None)
