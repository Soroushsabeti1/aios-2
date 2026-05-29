"""
صف پیام‌های خروجی — یکپارچه و بدون ناسازگاری.
queue_message هر دو فرمت رو قبول می‌کنه.
"""
from collections import defaultdict

_outbox: dict[int, list[dict]] = defaultdict(list)
_admin_queue: list[dict] = []


def queue_message(owner_user_id: int,
                  target_or_dict,
                  text: str = None):
    """
    دو فرمت:
      queue_message(uid, telegram_id, "متن")
      queue_message(uid, {"chat_id": tid, "text": "متن"})
    """
    if isinstance(target_or_dict, dict):
        _outbox[owner_user_id].append(target_or_dict)
    else:
        _outbox[owner_user_id].append({
            "type": "text",
            "chat_id": int(target_or_dict),
            "text": text or "",
        })


def queue_photo(owner_user_id: int, target_telegram_id: int,
                photo_bytes: bytes, mime: str, caption: str = ""):
    _outbox[owner_user_id].append({
        "type": "photo",
        "chat_id": int(target_telegram_id),
        "photo_bytes": photo_bytes,
        "mime": mime,
        "caption": caption,
    })


def queue_admin_notification(owner_user_id: int, request_id: int,
                              request_type: str, tenant,
                              receipt_bytes: bytes = None,
                              receipt_mime: str = None):
    _admin_queue.append({
        "owner_user_id": owner_user_id,
        "request_id": request_id,
        "request_type": request_type,
        "tenant_name": getattr(tenant, "name", "ناشناس") if tenant else "ناشناس",
        "tenant_id": getattr(tenant, "id", None) if tenant else None,
        "owner_telegram_id": getattr(tenant, "owner_telegram_id", owner_user_id) if tenant else owner_user_id,
        "receipt_bytes": receipt_bytes,
        "receipt_mime": receipt_mime,
    })


def pop_messages(owner_user_id: int) -> list[dict]:
    return _outbox.pop(owner_user_id, [])


def pop_admin_notifications() -> list[dict]:
    items = list(_admin_queue)
    _admin_queue.clear()
    return items
