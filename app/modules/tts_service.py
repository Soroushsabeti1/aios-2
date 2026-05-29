"""
سرویس TTS — Grok به عنوان default، با محاوره‌سازی.
"""
import io
import re
import httpx
from app.core.config import settings

VOICE_OPTIONS = {
    "alloy":   {"label": "آلوی — طبیعی و متعادل", "gender": "neutral"},
    "echo":    {"label": "اکو — واضح و رسمی",     "gender": "male"},
    "fable":   {"label": "فیبل — گرم و صمیمی",   "gender": "neutral"},
    "onyx":    {"label": "اونیکس — عمیق و مردانه", "gender": "male"},
    "nova":    {"label": "نووا — روشن و زنانه",   "gender": "female"},
    "shimmer": {"label": "شیمر — نرم و آرام",     "gender": "female"},
}
DEFAULT_VOICE = "nova"

# ═══════════════════════════════════════
# محاوره‌سازی فارسی
# ═══════════════════════════════════════

_COLLOQUIAL = [
    ("می‌روم", "میرم"), ("می‌رود", "میره"), ("می‌روند", "میرن"),
    ("می‌خواهم", "می‌خوام"), ("می‌خواهد", "می‌خواد"), ("می‌خواهند", "می‌خوان"),
    ("می‌گویم", "می‌گم"), ("می‌گوید", "می‌گه"), ("می‌گویند", "می‌گن"),
    ("می‌آیم", "میام"), ("می‌آید", "میاد"), ("می‌آیند", "میان"),
    ("می‌دهم", "میدم"), ("می‌دهد", "میده"), ("می‌دهند", "میدن"),
    ("می‌توانم", "می‌تونم"), ("می‌توانی", "می‌تونی"), ("می‌تواند", "می‌تونه"),
    ("می‌شوم", "میشم"), ("می‌شود", "میشه"), ("می‌شوند", "میشن"),
    ("می‌کنم", "می‌کنم"), ("می‌کند", "می‌کنه"), ("می‌کنند", "می‌کنن"),
    ("است ", "ه "), ("هستم", "هستم"), ("هستی", "هستی"),
    ("چطور است", "چطوره"), ("درست است", "درسته"),
    ("می‌باشد", "هست"), ("می‌باشم", "هستم"),
    ("خواهم", "خوام"), ("بنابراین", "پس"),
    ("البته", "البته"), ("اما", "ولی"),
]


def to_colloquial(text: str) -> str:
    """تبدیل متن رسمی به محاوره تهرانی."""
    for formal, informal in _COLLOQUIAL:
        text = text.replace(formal, informal)
    return text


def optimize_for_tts(text: str) -> str:
    """پاکسازی و آماده‌سازی متن برای TTS."""
    # حذف markdown
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'[_~`]', '', text)
    text = re.sub(r'https?://\S+', 'لینک', text)
    # حذف ایموجی‌های اضافه
    text = re.sub(r'[📊📋✅⚠️🔴🟢🟡💰📢🎉🚨📩🔗🔑⏳👤📎]', '', text)
    # فاصله‌های اضافه
    text = re.sub(r'\n+', ' ', text)
    text = re.sub(r'  +', ' ', text)
    # محاوره‌سازی
    text = to_colloquial(text)
    return text.strip()


# ═══════════════════════════════════════
# Grok TTS (default)
# ═══════════════════════════════════════

async def generate_voice(text: str, voice_key: str = None,
                          prefer_ai: bool = True) -> tuple[io.BytesIO | None, str]:
    """تولید صدا — Grok به عنوان default."""
    if not voice_key:
        voice_key = DEFAULT_VOICE

    optimized = optimize_for_tts(text)
    if not optimized:
        return None, ""

    # Grok TTS
    buf = await _grok_tts(optimized, voice_key)
    if buf:
        return buf, "voice.mp3"

    # fallback: Edge-TTS
    buf = await _edge_tts_fallback(optimized)
    if buf:
        return buf, "voice.mp3"

    return None, ""


async def _grok_tts(text: str, voice: str = "nova") -> io.BytesIO | None:
    """Grok Voice TTS از OpenRouter."""
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                "https://openrouter.ai/api/v1/audio/speech",
                headers={
                    "Authorization": f"Bearer {settings.openrouter_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "x-ai/grok-voice-tts-1.0",
                    "input": text,
                    "voice": voice,
                },
            )
            if resp.status_code == 200 and len(resp.content) > 100:
                return io.BytesIO(resp.content)
    except Exception:
        pass
    return None


async def _edge_tts_fallback(text: str) -> io.BytesIO | None:
    """Edge-TTS فقط به عنوان fallback."""
    try:
        import edge_tts
        communicate = edge_tts.Communicate(text, "fa-IR-DilaraNeural")
        buf = io.BytesIO()
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                buf.write(chunk["data"])
        buf.seek(0)
        if buf.getbuffer().nbytes > 0:
            return buf
    except Exception:
        pass
    return None


# ═══════════════════════════════════════
# مدیریت صدا در TenantSettings
# ═══════════════════════════════════════

async def set_voice(session, tenant_id: int, voice_key: str) -> str:
    """تغییر صدا."""
    if voice_key not in VOICE_OPTIONS:
        lines = ["❌ صدای نامعتبر.\n\nصداهای موجود:"]
        for k, v in VOICE_OPTIONS.items():
            lines.append(f"• `{k}` — {v['label']}")
        lines.append("\nبگو مثلاً: «صدا رو به nova تغییر بده»")
        return "\n".join(lines)

    from sqlalchemy import select
    from app.database.models.business import TenantSettings
    import json as _json

    ts = await session.scalar(
        select(TenantSettings).where(TenantSettings.tenant_id == tenant_id)
    )
    if not ts:
        ts = TenantSettings(tenant_id=tenant_id)
        session.add(ts)

    ts.voice_key = voice_key
    await session.commit()

    info = VOICE_OPTIONS[voice_key]
    return f"✅ صدا به «{info['label']}» تغییر کرد."


async def list_voices() -> str:
    """لیست صداهای موجود."""
    lines = ["🎙 صداهای موجود:\n"]
    for k, v in VOICE_OPTIONS.items():
        lines.append(f"• **{k}** — {v['label']}")
    lines.append("\nبرای تغییر بگو: «صدا رو به [نام] تغییر بده»")
    return "\n".join(lines)


async def get_voice_key(session, tenant_id: int) -> str:
    """دریافت صدای فعلی."""
    from sqlalchemy import select
    from app.database.models.business import TenantSettings
    import json as _json

    ts = await session.scalar(
        select(TenantSettings).where(TenantSettings.tenant_id == tenant_id)
    )
    if ts and ts.voice_key and ts.voice_key in VOICE_OPTIONS:
        return ts.voice_key
    return DEFAULT_VOICE
