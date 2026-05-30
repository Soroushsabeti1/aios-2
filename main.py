"""
نقطه‌ی ورود اصلی برنامه — نسخه ۵.
ربات تلگرام + دیتابیس + background jobs (سرچ، هشدار، گزارش هفتگی، یادآور، پیگیری، trial).
"""
import logging
from datetime import time, timezone
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler, ConversationHandler, filters,
)
from app.core.config import settings
from app.database.base import init_db
from app.handlers.telegram_handlers import (
    start_command, receive_biz_name, receive_biz_name_voice, cancel_start,
    reset_command, message_handler, file_handler, photo_handler, voice_handler,
    process_search_queue, weekly_report_job, critical_alerts_job, reminder_job,
    periodic_report_job, followup_job, trial_expiry_job,
    admin_command_handler,
    ASKING_BIZ_NAME,
)
from app.modules.automation_jobs import (
    scrum_master_job,
    workflow_executor_job,
    timed_goals_job,
    autonomy_reminder_job,
    birthday_job,
    contract_expiry_job,
    installment_overdue_job,
    end_of_day_job,
    weekly_incomplete_job,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


async def post_init(application: Application):
    logger.info("Initializing database...")
    await init_db()
    logger.info("Database ready.")

    try:
        from app.core.runtime import set_bot_username
        me = await application.bot.get_me()
        if me.username:
            set_bot_username(me.username)
            logger.info("Bot username: @%s", me.username)
    except Exception as e:
        logger.warning("نتونستم یوزرنیم ربات رو بگیرم: %s", e)


def main():
    if settings.telegram_bot_token == "PLACEHOLDER":
        logger.error("TELEGRAM_BOT_TOKEN تنظیم نشده! فایل .env را بررسی کن.")
        return

    app = (
        Application.builder()
        .token(settings.telegram_bot_token)
        .post_init(post_init)
        .build()
    )

    # ConversationHandler برای /start — با پشتیبانی از ویس
    start_conv = ConversationHandler(
        entry_points=[
            CommandHandler("start", start_command),
        ],
        states={
            ASKING_BIZ_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_biz_name),
                MessageHandler(filters.VOICE, receive_biz_name_voice),
                MessageHandler(filters.AUDIO, receive_biz_name_voice),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_start)],
        allow_reentry=True,
        per_user=True,
        per_chat=True,
    )

    app.add_handler(start_conv)
    app.add_handler(CommandHandler("reset", reset_command))

    # هندلر دستورات ادمین — /approve_ID_DAYS  یا  /reject_ID
    app.add_handler(MessageHandler(
        filters.TEXT & filters.COMMAND & filters.Regex(r"^/(approve|reject)_\d+"),
        admin_command_handler,
    ))

    # ویس و صوت
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, voice_handler))
    # عکس
    app.add_handler(MessageHandler(filters.PHOTO, photo_handler))
    # فایل (import اکسل)
    app.add_handler(MessageHandler(filters.Document.ALL, file_handler))
    # پیام متنی
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

    # ─── Background Jobs ───
    job_queue = app.job_queue

    # پردازش صف جستجو — هر ۳ دقیقه
    job_queue.run_repeating(process_search_queue, interval=180, first=30)

    # بررسی یادآورها — هر ۶۰ ثانیه
    job_queue.run_repeating(reminder_job, interval=60, first=20)

    # پیگیری‌های زمان‌بندی‌شده — هر ۶۰ ثانیه
    job_queue.run_repeating(followup_job, interval=60, first=25)

    # بررسی trial‌های منقضی — هر ساعت
    job_queue.run_repeating(trial_expiry_job, interval=3600, first=300)

    # گزارش دوره‌ای گفت‌وگوها — هر ساعت چک می‌شود
    job_queue.run_repeating(periodic_report_job, interval=3600, first=120)

    # هشدارهای بحرانی — هر روز ۹ صبح ایران (≈ 05:30 UTC)
    job_queue.run_daily(
        critical_alerts_job,
        time=time(hour=5, minute=30, tzinfo=timezone.utc),
    )

    # گزارش هفتگی — پنجشنبه ۸ شب ایران (≈ 16:30 UTC)
    job_queue.run_daily(
        weekly_report_job,
        time=time(hour=16, minute=30, tzinfo=timezone.utc),
        days=(4,),
    )

    # ─── جاب‌های فاز E ───

    # Scrum Master — هر ۴ ساعت
    job_queue.run_repeating(scrum_master_job, interval=4 * 3600, first=60)

    # اجرای فلوهای زمان‌بندی — هر ۱۵ دقیقه
    job_queue.run_repeating(workflow_executor_job, interval=15 * 60, first=90)
    job_queue.run_repeating(timed_goals_job, interval=5 * 60, first=120)
    job_queue.run_repeating(autonomy_reminder_job, interval=30 * 24 * 60 * 60, first=3600)

    # تبریک تولد — روزانه ۸ صبح ایران (≈ 04:30 UTC)
    job_queue.run_daily(
        birthday_job,
        time=time(hour=4, minute=30, tzinfo=timezone.utc),
    )

    # هشدار پایان قرارداد — روزانه ۹ صبح ایران (≈ 05:30 UTC)
    job_queue.run_daily(
        contract_expiry_job,
        time=time(hour=5, minute=30, tzinfo=timezone.utc),
    )

    # هشدار اقساط سررسید — روزانه ۱۰ صبح ایران (≈ 06:30 UTC)
    job_queue.run_daily(
        installment_overdue_job,
        time=time(hour=6, minute=30, tzinfo=timezone.utc),
    )

    # گزارش پایان روز — روزانه ۶ عصر ایران (≈ 14:30 UTC)
    job_queue.run_daily(
        end_of_day_job,
        time=time(hour=14, minute=30, tzinfo=timezone.utc),
    )

    # یادآور هفتگی اطلاعات ناقص — شنبه ۱۰ صبح (≈ 06:30 UTC)
    job_queue.run_daily(
        weekly_incomplete_job,
        time=time(hour=6, minute=30, tzinfo=timezone.utc),
        days=(5,),  # شنبه
    )

    logger.info("Bot starting with background jobs...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
