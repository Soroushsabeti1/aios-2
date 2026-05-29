"""
هماهنگ‌کننده‌ی مکالمه (Orchestrator) — نسخه ۳.

تغییر اصلی: تاریخچه‌ی مکالمه حالا در PostgreSQL ذخیره می‌شود (حافظه‌ی دائمی).
بعد از ری‌استارت، ربات همه‌چیز را به یاد می‌آورد.

- همه‌ی پیام‌ها در جدول ConversationMessage آرشیو می‌شوند
- موقع پاسخ‌دهی، فقط ۳۰ پیام آخر به AI داده می‌شود
"""
import json
import re
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from app.ai.engine import ai_engine
from app.ai.dispatcher import dispatch
from app.database.models.business import ConversationMessage

MAX_CONTEXT_MESSAGES = 50   # تعداد پیام آخر که به AI داده می‌شود
MAX_TOOL_ROUNDS = 5         # جلوگیری از حلقه‌ی بی‌نهایت

# الگوهای کد جعلی که گاهی مدل اشتباهاً تولید می‌کند
_FAKE_CODE_PATTERNS = [
    re.compile(r"<execute_tool>.*?</execute_tool>", re.DOTALL),
    re.compile(r"<execute_tool>.*", re.DOTALL),
    re.compile(r"```[a-z]*\n?await .*?```", re.DOTALL),
]


def _clean_reply(text: str) -> str:
    """کد جعلی احتمالی را از پاسخ مدل پاک می‌کند."""
    if not text:
        return text
    cleaned = text
    for pat in _FAKE_CODE_PATTERNS:
        cleaned = pat.sub("", cleaned)
    cleaned = cleaned.strip()
    # اگر بعد از پاک‌سازی چیزی نماند، پیام جایگزین
    if not cleaned:
        return "چشم، یه لحظه..."
    return cleaned


async def _load_history(session: AsyncSession, tenant_id: int,
                        user_id: int) -> list[dict]:
    """آخرین N پیام مکالمه را از دیتابیس می‌خواند و به فرمت AI تبدیل می‌کند."""
    rows = (await session.scalars(
        select(ConversationMessage).where(
            ConversationMessage.tenant_id == tenant_id,
            ConversationMessage.user_telegram_id == user_id,
        ).order_by(ConversationMessage.id.desc()).limit(MAX_CONTEXT_MESSAGES)
    )).all()
    # ترتیب صحیح (قدیم به جدید)
    rows = list(reversed(rows))

    history = []
    for row in rows:
        if row.raw_json:
            # پیام assistant با tool_calls یا پیام tool — کل دیکشنری ذخیره شده
            try:
                history.append(json.loads(row.raw_json))
                continue
            except json.JSONDecodeError:
                pass
        # پیام ساده‌ی متنی
        history.append({"role": row.role, "content": row.content or ""})

    # اصلاح پنجره: اگر ابتدای تاریخچه با پیام‌های tool یتیم شروع شود
    # (پیام assistant متناظرشان خارج از پنجره‌ی ۳۰تایی افتاده)، API خطا می‌دهد.
    # این پیام‌های یتیم را از ابتدا حذف می‌کنیم.
    while history and history[0].get("role") == "tool":
        history.pop(0)
    # همچنین اگر اولین پیام، assistantِ دارای tool_calls باشد ولی پیام‌های
    # tool متناظرش حذف شده‌اند، آن را هم پاک می‌کنیم.
    while history and history[0].get("role") == "assistant" and history[0].get("tool_calls"):
        history.pop(0)

    return history


async def _save_message(session: AsyncSession, tenant_id: int, user_id: int,
                        message: dict):
    """یک پیام را در آرشیو دیتابیس ذخیره می‌کند."""
    role = message.get("role", "user")
    content = message.get("content")
    if isinstance(content, list):
        # محتوای multimodal (متن + عکس) — فقط بخش متنی را برای آرشیو نگه می‌داریم
        text_parts = [p.get("text", "") for p in content if isinstance(p, dict) and p.get("type") == "text"]
        content = " ".join(text_parts) or "[محتوای تصویری]"

    # اگر پیام ساختار پیچیده دارد (tool_calls یا tool result)، کل آن را JSON ذخیره کن
    needs_raw = bool(message.get("tool_calls")) or role == "tool"
    raw_json = None
    if needs_raw:
        try:
            raw_json = json.dumps(message, ensure_ascii=False)
        except (TypeError, ValueError):
            raw_json = None

    session.add(ConversationMessage(
        tenant_id=tenant_id,
        user_telegram_id=user_id,
        role=role,
        content=content if isinstance(content, str) else None,
        raw_json=raw_json,
    ))
    await session.commit()


async def handle_message(session: AsyncSession, tenant_id: int,
                         user_id: int, text: str,
                         image_data: bytes = None,
                         image_mime: str = None,
                         role: str = "owner",
                         person_role: str = None) -> str:
    """
    یک پیام کاربر را پردازش می‌کند و جواب نهایی متنی برمی‌گرداند.
    """
    # تنظیمات tenant (لحن، اسم دستیار، ...)
    from sqlalchemy import select as _sel
    from app.database.models.business import TenantSettings as _TS
    from app.database.models.tenant import Tenant as _Tenant

    tenant_settings = {}
    try:
        ts = await session.scalar(_sel(_TS).where(_TS.tenant_id == tenant_id))
        tenant = await session.get(_Tenant, tenant_id)
        if ts:
            tenant_settings = {
                "tone": ts.tone or "friendly",
                "ai_name": ts.ai_name or "دستیار",
                "biz_name": tenant.name if tenant else "مجموعه",
            }
        elif tenant:
            tenant_settings = {
                "tone": "friendly",
                "ai_name": "دستیار",
                "biz_name": tenant.name,
            }
        # اگه پرسن هست اسمش رو بگیر
        if person_role:
            from app.modules.persons_service import get_person_by_telegram
            person = await get_person_by_telegram(session, user_id)
            if person:
                tenant_settings["person_name"] = person.full_name
    except Exception:
        pass

    # تاریخچه را از دیتابیس بخوان
    history = await _load_history(session, tenant_id, user_id)

    # ساخت پیام کاربر — اگر عکس دارد، multimodal
    if image_data:
        import base64
        b64 = base64.b64encode(image_data).decode("utf-8")
        mime = image_mime or "image/jpeg"
        user_message = {
            "role": "user",
            "content": [
                {"type": "text", "text": text or "این تصویر را تحلیل کن."},
                {"type": "image_url",
                 "image_url": {"url": f"data:{mime};base64,{b64}"}},
            ],
        }
    else:
        user_message = {"role": "user", "content": text}

    history.append(user_message)
    # پیام کاربر را در آرشیو ذخیره کن
    await _save_message(session, tenant_id, user_id, user_message)

    for _ in range(MAX_TOOL_ROUNDS):
        message = await ai_engine.chat(history, role=role, person_role=person_role,
                                        tenant_settings=tenant_settings)
        history.append(message)
        await _save_message(session, tenant_id, user_id, message)

        tool_calls = ai_engine.parse_tool_calls(message)

        if not tool_calls:
            return _clean_reply(message.get("content") or "...")

        for call in tool_calls:
            result = await dispatch(session, tenant_id, user_id,
                                    call["name"], call["arguments"], role=role)
            tool_message = {
                "role": "tool",
                "tool_call_id": call["id"],
                "content": result,
            }
            history.append(tool_message)
            await _save_message(session, tenant_id, user_id, tool_message)

    return "متأسفم، نتونستم این درخواست رو کامل کنم. می‌تونی واضح‌تر بگی؟"


async def reset_conversation(session: AsyncSession, tenant_id: int, user_id: int):
    """پاک کردن تاریخچه‌ی مکالمه‌ی یک کاربر از دیتابیس."""
    await session.execute(
        delete(ConversationMessage).where(
            ConversationMessage.tenant_id == tenant_id,
            ConversationMessage.user_telegram_id == user_id,
        )
    )
    await session.commit()
