"""
سرویس TTS — تبدیل متن به صدا.
جنس صدا از TenantSettings قابل تغییره.
"""
import io
import httpx
from app.core.config import settings


# ═══════════════════════════════════════
# صداهای موجود
# ═══════════════════════════════════════

VOICE_OPTIONS = {
    # فارسی
    "fa-female": "fa-IR-DilaraNeural",      # زن فارسی (پیش‌فرض)
    "fa-male": "fa-IR-FaridNeural",          # مرد فارسی
    # انگلیسی (برای تنوع)
    "en-female": "en-US-JennyNeural",
    "en-male": "en-US-GuyNeural",
}

DEFAULT_VOICE = "fa-female"


def detect_emotion(text: str) -> dict:
    _JOY = {"خوب", "عالی", "خوشحال", "فوق‌العاده", "تبریک", "سود", "رکورد"}
    _ANGER = {"کافیه", "اخطار", "تخلف", "فوری"}
    _SADNESS = {"ضرر", "زیان", "ناراحت", "کاهش"}
    _WORRY = {"هشدار", "بحرانی", "سررسید", "بدهی"}

    text_l = text.lower()
    scores = {
        "JOY": sum(1 for w in _JOY if w in text_l),
        "ANGER": sum(1 for w in _ANGER if w in text_l),
        "SADNESS": sum(1 for w in _SADNESS if w in text_l),
        "WORRY": sum(1 for w in _WORRY if w in text_l),
    }
    scores["JOY"] += text.count("!")
    top = max(scores, key=scores.get)
    speed = 1.1 if top in ("JOY", "ANGER") else 0.95 if top in ("SADNESS", "WORRY") else 1.0
    return {"emotion": top, "speed": speed}


def optimize_for_tts(text: str) -> str:
    """پاکسازی متن برای صدا."""
    import re
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'[_~`]', '', text)
    text = re.sub(r'https?://\S+', 'لینک', text)
    text = re.sub(r'[📊📋✅⚠️🔴🟢🟡💰📢🎉🚨📩]', '', text)
    text = re.sub(r'\n+', ' ', text)
    text = re.sub(r'  +', ' ', text)
    return text.strip()


async def _generate_edge_tts(text: str, voice_key: str = "fa-female") -> tuple[io.BytesIO | None, str]:
    """تولید صدا با Edge TTS."""
    try:
        import edge_tts

        voice_name = VOICE_OPTIONS.get(voice_key, VOICE_OPTIONS[DEFAULT_VOICE])
        optimized = optimize_for_tts(text)
        emotion = detect_emotion(text)
        rate = f"{int((emotion['speed'] - 1) * 100):+d}%"

        communicate = edge_tts.Communicate(optimized, voice_name, rate=rate)
        buf = io.BytesIO()
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                buf.write(chunk["data"])
        buf.seek(0)

        if buf.getbuffer().nbytes > 0:
            return buf, "voice.mp3"

    except ImportError:
        pass
    except Exception:
        pass
    return None, ""


async def _generate_openrouter_tts(text: str) -> tuple[io.BytesIO | None, str]:
    """تولید صدا از OpenRouter."""
    try:
        optimized = optimize_for_tts(text)
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                "https://openrouter.ai/api/v1/audio/speech",
                headers={
                    "Authorization": f"Bearer {settings.openrouter_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "x-ai/grok-voice-tts-1.0",
                    "input": optimized,
                    "voice": "alloy",
                },
            )
            if resp.status_code == 200:
                buf = io.BytesIO(resp.content)
                return buf, "voice.mp3"
    except Exception:
        pass
    return None, ""


async def generate_voice(text: str, voice_key: str = None,
                          prefer_ai: bool = False) -> tuple[io.BytesIO | None, str]:
    """
    تولید صدا — اگه متن کوتاه → OpenRouter, وگرنه Edge TTS.
    voice_key: fa-female / fa-male / en-female / en-male
    """
    if not voice_key:
        voice_key = DEFAULT_VOICE

    if prefer_ai or len(text) < 300:
        buf, fname = await _generate_openrouter_tts(text)
        if buf:
            return buf, fname

    return await _generate_edge_tts(text, voice_key)


async def set_voice(session, tenant_id: int, voice_key: str) -> str:
    """تغییر جنس صدا از چت."""
    if voice_key not in VOICE_OPTIONS:
        options = "، ".join(f"{k}" for k in VOICE_OPTIONS.keys())
        return f"⚠️ صدای معتبر: {options}"

    from sqlalchemy import select
    from app.database.models.business import TenantSettings
    ts = await session.scalar(
        select(TenantSettings).where(TenantSettings.tenant_id == tenant_id)
    )
    if not ts:
        ts = TenantSettings(tenant_id=tenant_id)
        session.add(ts)

    import json
    docs = {}
    if ts.business_docs_json:
        try:
            docs = json.loads(ts.business_docs_json)
        except Exception:
            pass
    docs["voice_key"] = voice_key
    ts.business_docs_json = json.dumps(docs, ensure_ascii=False)
    await session.commit()

    voice_label = {
        "fa-female": "زن فارسی",
        "fa-male": "مرد فارسی",
        "en-female": "زن انگلیسی",
        "en-male": "مرد انگلیسی",
    }.get(voice_key, voice_key)
    return f"✅ صدا به «{voice_label}» تغییر کرد."


async def get_voice_key(session, tenant_id: int) -> str:
    """دریافت جنس صدای فعلی."""
    from sqlalchemy import select
    from app.database.models.business import TenantSettings
    import json
    ts = await session.scalar(
        select(TenantSettings).where(TenantSettings.tenant_id == tenant_id)
    )
    if ts and ts.business_docs_json:
        try:
            docs = json.loads(ts.business_docs_json)
            return docs.get("voice_key", DEFAULT_VOICE)
        except Exception:
            pass
    return DEFAULT_VOICE
