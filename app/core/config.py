"""
تنظیمات مرکزی پروژه.
همه‌ی مقادیر حساس از متغیرهای محیطی (.env) خوانده می‌شوند.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # تلگرام
    telegram_bot_token: str = "PLACEHOLDER"
    # یوزرنیم ربات (بدون @) — برای ساخت لینک دعوت لازم است
    bot_username: str = "your_bot"

    # OpenRouter / AI
    openrouter_api_key: str = "PLACEHOLDER"
    openrouter_model: str = "google/gemini-2.5-pro"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"

    # دیتابیس
    database_url: str = "postgresql+asyncpg://user:password@localhost:5432/ai_business_os"

    # عمومی
    super_admin_ids: str = ""
    currency: str = "toman"
    trial_days: int = 3

    # شماره کارت برای دریافت اشتراک
    payment_card_number: str = "XXXX-XXXX-XXXX-XXXX"
    payment_card_holder: str = "صاحب حساب"

    @property
    def admin_id_list(self) -> list[int]:
        if not self.super_admin_ids:
            return []
        return [int(x.strip()) for x in self.super_admin_ids.split(",") if x.strip()]

    @property
    def db_url_normalized(self) -> str:
        # Railway گاهی postgresql:// می‌دهد؛ به نسخه async تبدیل می‌کنیم
        url = self.database_url
        if url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return url


settings = Settings()
