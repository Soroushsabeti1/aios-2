"""
سرویس تبدیل گفتار به متن (Speech-to-Text) — نسخه ۴.

این نسخه دقیقاً مطابق نمونه‌کد رسمی OpenRouter نوشته شده:
  POST https://openrouter.ai/api/v1/audio/transcriptions
  body: {"model": "...", "input_audio": {"data": base64, "format": "wav"}}

نکات کلیدی که نسخه‌های قبلی اشتباه داشتند:
  - مدل درست: mistralai/voxtral-mini-transcribe (نه whisper-1)
  - فرمت صوت: wav (نه mp3) — نمونه‌کد رسمی wav می‌خواهد
  - فیلد input_audio به‌صورت json در body (نه multipart/files)

تلگرام ویس را با فرمت ogg/opus می‌فرستد، پس با ffmpeg به wav تبدیل می‌شود.
"""
import io
import os
import shutil
import base64
import asyncio
import logging
import tempfile
import subprocess
import httpx
from app.core.config import settings

logger = logging.getLogger(__name__)

# مدل تبدیل گفتار — مطابق OpenRouter
STT_MODEL = "openai/gpt-4o-mini-transcribe"

# endpoint رسمی تبدیل صوت OpenRouter
STT_URL = f"{settings.openrouter_base_url}/audio/transcriptions"

# سقف منطقی حجم فایل صوتی
MAX_AUDIO_BYTES = 20 * 1024 * 1024


def _ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def _convert_to_wav(audio_bytes: bytes, src_ext: str = "ogg") -> bytes | None:
    """
    تبدیل فایل صوتی به wav با ffmpeg.
    خروجی wav با ۱۶ کیلوهرتز و mono — استاندارد تبدیل گفتار.
    """
    if not _ffmpeg_available():
        logger.warning("STT: ffmpeg در دسترس نیست.")
        return None
    try:
        with tempfile.NamedTemporaryFile(suffix=f".{src_ext}", delete=False) as src:
            src.write(audio_bytes)
            src_path = src.name
        dst_path = src_path.rsplit(".", 1)[0] + ".wav"

        result = subprocess.run(
            ["ffmpeg", "-y", "-i", src_path, "-ar", "16000", "-ac", "1", dst_path],
            capture_output=True, timeout=120,
        )
        if result.returncode != 0:
            logger.error("STT: ffmpeg خطا داد: %s",
                         result.stderr.decode("utf-8", "ignore")[:300])
            return None

        with open(dst_path, "rb") as f:
            wav_bytes = f.read()

        for p in (src_path, dst_path):
            try:
                os.remove(p)
            except OSError:
                pass
        return wav_bytes
    except Exception as e:
        logger.error("STT: خطای تبدیل ffmpeg: %s", e)
        return None


async def _send_transcription(audio_bytes: bytes, audio_format: str) -> str:
    """
    فایل صوتی را به endpoint تبدیل صوت OpenRouter می‌فرستد.
    دقیقاً مطابق نمونه‌کد رسمی: input_audio به‌صورت json در body.
    در صورت خطا استثنا پرتاب می‌کند.
    """
    b64_audio = base64.b64encode(audio_bytes).decode("utf-8")

    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/ai-business-os",
        "X-OpenRouter-Title": "AI Business OS",
    }
    body = {
        "model": STT_MODEL,
        "input_audio": {
            "data": b64_audio,
            "format": audio_format,
        },
    }

    async with httpx.AsyncClient(timeout=180.0) as client:
        resp = await client.post(STT_URL, headers=headers, json=body)
        if resp.status_code != 200:
            logger.error("STT: پاسخ %s از %s — بدنه: %s",
                         resp.status_code, STT_URL, resp.text[:400])
            resp.raise_for_status()
        result = resp.json()

    # پاسخ طبق مستندات: {"text": "..."}
    text = result.get("text")
    if text is None:
        # بعضی پاسخ‌ها ممکن است ساختار choices داشته باشند
        choices = result.get("choices")
        if choices:
            text = choices[0].get("message", {}).get("content")
    return (text or "").strip()


async def transcribe_voice(audio_bytes: bytes,
                           src_ext: str = "ogg") -> tuple[str | None, str | None]:
    """
    ویس کاربر را به متن تبدیل می‌کند.
    خروجی: (متن, خطا) — اگر موفق: (متن, None)، اگر خطا: (None, پیام).
    """
    logger.info("STT: شروع تبدیل ویس (%d بایت، فرمت %s)", len(audio_bytes), src_ext)

    if len(audio_bytes) > MAX_AUDIO_BYTES:
        return None, "این ویس خیلی بلنده. لطفاً کوتاه‌تر بفرست."

    # تبدیل به wav (فرمتی که نمونه‌کد رسمی می‌خواهد)
    wav_bytes = await asyncio.to_thread(_convert_to_wav, audio_bytes, src_ext)

    if wav_bytes is not None:
        audio_to_send = wav_bytes
        audio_format = "wav"
        logger.info("STT: تبدیل به wav موفق (%d بایت)", len(wav_bytes))
    else:
        # ffmpeg نبود — فایل خام را با فرمت اصلی امتحان کن
        audio_to_send = audio_bytes
        audio_format = src_ext
        logger.info("STT: بدون ffmpeg — تلاش با فرمت خام %s", src_ext)

    try:
        text = await _send_transcription(audio_to_send, audio_format)
        if not text:
            return None, "صدایی تشخیص داده نشد. لطفاً واضح‌تر و بلندتر صحبت کن."
        logger.info("STT: موفق — %d کاراکتر متن", len(text))
        return text, None
    except httpx.HTTPStatusError as e:
        code = e.response.status_code
        if code == 400:
            return None, "فرمت این ویس پشتیبانی نشد. اگر مشکل ادامه داشت به پشتیبانی اطلاع بده."
        if code == 404:
            return None, "سرویس تبدیل صدا در دسترس نیست (endpoint پیدا نشد)."
        if code == 500:
            return None, "سرویس تبدیل صدا موقتاً پاسخ نمی‌دهد. کمی بعد دوباره امتحان کن."
        return None, f"خطا در سرویس تبدیل صدا (کد {code})."
    except Exception as e:
        logger.error("STT: خطای ناشناخته: %s", e)
        return None, "خطا در تبدیل صدا به متن. دوباره امتحان کن."
