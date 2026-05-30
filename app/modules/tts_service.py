"""
TTS — Grok default با احساس، اکسان، مکث، لحن.
"""
import io, re, httpx
from app.core.config import settings

VOICE_OPTIONS = {
    "alloy":   {"label": "آلوی — طبیعی", "gender": "neutral"},
    "echo":    {"label": "اکو — رسمی",   "gender": "male"},
    "fable":   {"label": "فیبل — صمیمی", "gender": "neutral"},
    "onyx":    {"label": "اونیکس — مردانه", "gender": "male"},
    "nova":    {"label": "نووا — زنانه", "gender": "female"},
    "shimmer": {"label": "شیمر — آرام",  "gender": "female"},
}
DEFAULT_VOICE = "nova"

# احساس → voice + پارامترهای لحن
EMOTION_MAP = {
    "joy":       {"voice": "nova",    "prefix": "با شادی: "},
    "worry":     {"voice": "shimmer", "prefix": "با نگرانی: "},
    "authority": {"voice": "onyx",    "prefix": "با اقتدار: "},
    "formal":    {"voice": "echo",    "prefix": ""},
    "friendly":  {"voice": "fable",   "prefix": ""},
    "neutral":   {"voice": "alloy",   "prefix": ""},
}

# لحن بر اساس نقش
ROLE_VOICE = {
    "customer":     "nova",
    "employee":     "alloy",
    "owner":        "onyx",
    "collaborator": "fable",
}

# محاوره‌سازی فارسی
_COLLOQUIAL = [
    ("می‌روم","میرم"),("می‌رود","میره"),("می‌روند","میرن"),
    ("می‌خواهم","می‌خوام"),("می‌خواهد","می‌خواد"),("می‌خواهند","می‌خوان"),
    ("می‌گویم","می‌گم"),("می‌گوید","می‌گه"),("می‌گویند","می‌گن"),
    ("می‌آیم","میام"),("می‌آید","میاد"),("می‌آیند","میان"),
    ("می‌دهم","میدم"),("می‌دهد","میده"),("می‌دهند","میدن"),
    ("می‌توانم","می‌تونم"),("می‌تواند","می‌تونه"),("می‌توانند","می‌تونن"),
    ("می‌شوم","میشم"),("می‌شود","میشه"),("می‌شوند","میشن"),
    ("می‌کند","می‌کنه"),("می‌کنند","می‌کنن"),
    ("است ","ه "),("می‌باشد","هست"),("می‌باشم","هستم"),
    ("بنابراین","پس"),("اما","ولی"),("البته","البته"),
    ("می‌خواهی","می‌خوای"),("می‌توانی","می‌تونی"),
]

# اعداد به حروف
_NUM_MAP = {
    "0":"صفر","1":"یک","2":"دو","3":"سه","4":"چهار","5":"پنج",
    "6":"شش","7":"هفت","8":"هشت","9":"نه","10":"ده",
    "11":"یازده","12":"دوازده","13":"سیزده","14":"چهارده","15":"پانزده",
    "16":"شانزده","17":"هفده","18":"هجده","19":"نوزده","20":"بیست",
}

def numbers_to_words(text: str) -> str:
    """اعداد ساده رو به حروف تبدیل کن."""
    def replace_num(m):
        n = m.group(0)
        if n in _NUM_MAP:
            return _NUM_MAP[n]
        # اعداد بزرگ‌تر رو نگه بدار
        return n
    return re.sub(r'\b\d+\b', replace_num, text)

def to_colloquial(text: str) -> str:
    for formal, informal in _COLLOQUIAL:
        text = text.replace(formal, informal)
    return text

def add_pauses(text: str) -> str:
    """اضافه کردن مکث با ویرگول."""
    text = re.sub(r'([.!?؟])\s+', r'\1 ... ', text)
    text = re.sub(r'([،,])\s+', r'\1 .. ', text)
    return text

def optimize_for_tts(text: str, emotion: str = "neutral",
                      role: str = None) -> str:
    """آماده‌سازی کامل متن برای TTS."""
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'[_~`]', '', text)
    text = re.sub(r'https?://\S+', 'لینک', text)
    text = re.sub(r'[📊📋✅⚠️🔴🟢🟡💰📢🎉🚨📩🔗🔑⏳👤📎]', '', text)
    text = re.sub(r'\n+', ' ', text)
    text = re.sub(r'  +', ' ', text)
    text = numbers_to_words(text)
    text = to_colloquial(text)
    text = add_pauses(text)
    return text.strip()


async def generate_voice(text: str, voice_key: str = None,
                          emotion: str = "neutral",
                          role: str = None) -> tuple[io.BytesIO | None, str]:
    """تولید صدا با احساس و لحن."""
    if not voice_key:
        voice_key = ROLE_VOICE.get(role, DEFAULT_VOICE)

    em = EMOTION_MAP.get(emotion, EMOTION_MAP["neutral"])
    optimized = optimize_for_tts(text, emotion, role)
    if not optimized:
        return None, ""

    buf = await _grok_tts(optimized, voice_key)
    if buf:
        return buf, "voice.mp3"

    buf = await _edge_tts_fallback(optimized)
    if buf:
        return buf, "voice.mp3"

    return None, ""


async def _grok_tts(text: str, voice: str = "nova") -> io.BytesIO | None:
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


async def set_voice(session, tenant_id: int, voice_key: str) -> str:
    if voice_key not in VOICE_OPTIONS:
        lines = ["صداهای موجود:"]
        for k, v in VOICE_OPTIONS.items():
            lines.append(f"• {k} — {v['label']}")
        return "\n".join(lines)
    from sqlalchemy import select
    from app.database.models.business import TenantSettings
    ts = await session.scalar(select(TenantSettings).where(TenantSettings.tenant_id == tenant_id))
    if not ts:
        ts = TenantSettings(tenant_id=tenant_id)
        session.add(ts)
    ts.voice_key = voice_key
    await session.commit()
    return f"✅ صدا به «{VOICE_OPTIONS[voice_key]['label']}» تغییر کرد."


async def list_voices() -> str:
    lines = ["🎙 صداهای موجود:\n"]
    for k, v in VOICE_OPTIONS.items():
        lines.append(f"• **{k}** — {v['label']}")
    lines.append("\nبرای تغییر: «صدا رو به [نام] تغییر بده»")
    return "\n".join(lines)


async def get_voice_key(session, tenant_id: int) -> str:
    from sqlalchemy import select
    from app.database.models.business import TenantSettings
    ts = await session.scalar(select(TenantSettings).where(TenantSettings.tenant_id == tenant_id))
    if ts and ts.voice_key and ts.voice_key in VOICE_OPTIONS:
        return ts.voice_key
    return DEFAULT_VOICE
