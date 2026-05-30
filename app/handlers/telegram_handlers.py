"""
هندلرهای تلگرام — نسخه ۵.
- دریافت فایل (import اکسل)
- دریافت عکس (لوگو یا تحلیل با AI)
- دریافت ویس (تبدیل به متن و پردازش)
- حافظه‌ی دائمی
- سیستم نقش: کارفرما / کارمند / همکار / مشتری / پارتنر
- لینک دعوت: پردازش /start inv_TOKEN
- background jobs: سرچ، هشدار، یادآور
"""
from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler
from app.database.base import AsyncSessionLocal
from app.modules.tenant_service import check_access, create_tenant, get_tenant_for_user, save_tenant_logo
from app.modules import persons_service, roles
from app.ai.orchestrator import handle_message, reset_conversation
from app.ai.pending_files import pop_files
from app.ai import pending_uploads
from app.utils.rate_limiter import check_rate_limit
from app.modules.reports.import_service import preview_import, do_import, rollback_last_import

ASKING_BIZ_NAME = 1


async def _resolve_user(session, telegram_id: int):
    """
    تشخیص اینکه این کاربر کیست و چه نقشی دارد.
    خروجی: (نوع, tenant_id, role)
      نوع: "owner" / "person" / "none"
    """
    # اول: آیا کارفرماست؟
    tenant = await get_tenant_for_user(session, telegram_id)
    if tenant:
        return "owner", tenant.id, roles.ROLE_OWNER

    # دوم: آیا یک شخص متصل است (کارمند/مشتری/...)؟
    person = await persons_service.get_person_by_telegram(session, telegram_id)
    if person:
        return "person", person.tenant_id, person.role

    return "none", None, None


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    دستور /start.
    سه حالت:
      ۱. /start inv_TOKEN  → پردازش لینک دعوت
      ۲. کاربر شناخته‌شده (کارفرما یا شخص متصل) → خوش‌آمد
      ۳. کاربر جدید → آنبوردینگ جدید
    """
    user = update.effective_user

    # آیا پارامتر start (لینک دعوت) دارد؟
    args = context.args or []
    if args and args[0].startswith("inv_"):
        token = args[0][4:]  # حذف پیشوند inv_
        return await _handle_invite(update, context, token)

    async with AsyncSessionLocal() as session:
        kind, tenant_id, role = await _resolve_user(session, user.id)

        if kind == "owner":
            tenant = await get_tenant_for_user(session, user.id)
            await update.message.reply_text(
                f"سلام {user.first_name} 👋\n"
                f"به «{tenant.name}» خوش برگشتی. چی کار کنم برات؟"
            )
            return ConversationHandler.END

        if kind == "person":
            role_fa = roles.ROLE_LABELS.get(role, role)
            await update.message.reply_text(
                f"سلام {user.first_name} 👋\n"
                f"خوش برگشتی. شما به‌عنوان {role_fa} وارد شدی."
            )
            return ConversationHandler.END

        # کاربر جدید — آنبوردینگ
        await update.message.reply_text(
            f"سلام {user.first_name}! 👋\n\n"
            f"من یه دستیار هوشمند کسب‌وکارم. "
            f"قبل از شروع یه داستان کوتاه دارم که فکر کنم دوست داری بشنوی. وقت داری؟"
        )
        context.user_data["onboarding_step"] = "story_ask"
        return ASKING_BIZ_NAME


async def _handle_invite(update: Update, context: ContextTypes.DEFAULT_TYPE,
                         token: str):
    """پردازش کلیک روی لینک دعوت — کامل و بدون باگ."""
    user = update.effective_user

    # پاک کردن همه state های قبلی
    for k in ["onboarding_step", "credential_step", "pending_invite_token",
              "pending_username", "credential_fails"]:
        context.user_data.pop(k, None)

    async with AsyncSessionLocal() as session:
        from app.database.models.business import InviteLink
        from sqlalchemy import select as _sel
        link = await session.scalar(_sel(InviteLink).where(InviteLink.token == token))

        if not link:
            await update.message.reply_text("⚠️ این لینک معتبر نیست.")
            return ConversationHandler.END
        if link.is_revoked:
            await update.message.reply_text("⚠️ این لینک لغو شده.")
            return ConversationHandler.END

        from datetime import datetime, timezone
        if link.expires_at:
            exp = link.expires_at
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
            if exp < datetime.now(timezone.utc):
                await update.message.reply_text("⚠️ این لینک منقضی شده. از کارفرما لینک جدید بخواه.")
                return ConversationHandler.END

        if link.max_uses and link.use_count >= link.max_uses:
            await update.message.reply_text("⚠️ ظرفیت این لینک پر شده.")
            return ConversationHandler.END

        # اگه رمز داره → credential flow
        if link.password:
            context.user_data["pending_invite_token"] = token
            context.user_data["credential_step"] = "username"
            context.user_data["credential_fails"] = 0
            await update.message.reply_text(
                "🔑 برای ورود، نام کاربری‌ات رو وارد کن (کد ملی ۱۰ رقمی):"
            )
            return ConversationHandler.END

        # بدون رمز → مستقیم وصل کن
        ok, msg = await persons_service.consume_invite_link(
            session, token, user.id,
            telegram_username=user.username,
            full_name=user.full_name,
        )
        if ok and msg.endswith("|CHANGE_CREDENTIALS"):
            real_msg = msg[:-len("|CHANGE_CREDENTIALS")]
            await update.message.reply_text(real_msg)
            context.user_data["credential_step"] = "new_username"
        else:
            await update.message.reply_text(msg)
            if ok:
                await update.message.reply_text("هر وقت کاری داشتی بگو 😊")
        return ConversationHandler.END


def _welcome_help(role: str) -> str:
    """پیام راهنمای خوش‌آمد بر اساس نقش — بعد از عضویت."""
    if role == roles.ROLE_CUSTOMER:
        return (
            "از این به بعد می‌تونی هر وقت خواستی همینجا باهامون در ارتباط باشی 🌟\n\n"
            "مثلاً می‌تونی:\n"
            "• سؤال یا درخواستت رو بفرستی\n"
            "• از محصولات و تخفیف‌ها بپرسی\n"
            "• اگه کارت فوریه، بگو «فوری» تا سریع رسیدگی بشه\n\n"
            "همین الان می‌تونی پیامت رو بنویسی 👇"
        )
    if role in (roles.ROLE_EMPLOYEE, roles.ROLE_COLLABORATOR):
        return (
            "از این به بعد دستیار کاری‌ت همینجاست 💼\n\n"
            "مثلاً می‌تونی:\n"
            "• یادآور بذاری: «فردا ساعت ۹ جلسه دارم»\n"
            "• با مدیریت در ارتباط باشی و گزارش بدی\n"
            "• اطلاع‌رسانی‌ها و درخواست‌های مدیریت رو دریافت کنی\n\n"
            "هر وقت چیزی لازم داشتی، همینجا بنویس 👇"
        )
    return (
        "خوش اومدی! از این به بعد می‌تونی همینجا با ما در ارتباط باشی.\n"
        "هر وقت چیزی لازم داشتی، بنویس 👇"
    )


async def _try_invite_password(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """
    اگر کاربر منتظر وارد کردن رمز دعوت است، این تابع رمز را پردازش می‌کند.
    خروجی: True اگر این پیام مربوط به رمز دعوت بود.
    """
    token = context.user_data.get("pending_invite_token")
    if not token:
        return False

    user = update.effective_user
    password = (update.message.text or "").strip()

    async with AsyncSessionLocal() as session:
        ok, msg = await persons_service.consume_invite_link(
            session, token, user.id,
            telegram_username=user.username,
            full_name=user.full_name,
            password_attempt=password,
        )

    if msg == "PASSWORD_REQUIRED":
        await update.message.reply_text("🔑 رمز اشتباه بود. دوباره امتحان کن:")
        return True

    # موفق یا خطای دیگر — توکن را پاک کن
    context.user_data.pop("pending_invite_token", None)
    await update.message.reply_text(msg)
    if ok:
        async with AsyncSessionLocal() as s2:
            p = await persons_service.get_person_by_telegram(s2, user.id)
            if p:
                await update.message.reply_text(_welcome_help(p.role))
    return True


async def receive_biz_name(update, context):
    """آنبوردینگ — طبق spec: لحن آخر پرسیده می‌شه."""
    import json as _json
    from app.database.base import AsyncSessionLocal
    from app.modules.tenant_service import create_tenant
    from app.ai.outbox import queue_admin_notification
    import app.handlers.telegram_handlers as _self

    user = update.effective_user
    text = (update.message.text or "").strip()
    step = context.user_data.get("onboarding_step", "story_ask")

    # ─── ۱. داستان ───
    if step == "story_ask":
        text_low = text.lower().strip()
        # اگه صریح نه گفت برو بعدی، وگرنه داستان بگو
        no_words = ["نه", "نخیر", "نه ممنون", "نه لازم", "بعدا", "بی‌خیال", "skip"]
        wants = not any(w in text_low for w in no_words)
        if wants:
            await update.message.reply_text(
                "سال ۲۰۲۴ متیو گالاگر با یه دوستش یه کلینیک سلامت از راه دور "
                "با هوش مصنوعی راه انداختن 🏥 محصول، وبسایت، تبلیغات، پشتیبانی "
                "همه با هوش مصنوعی بود. خودشون فقط تایید یا رد می‌کردن!\n\nخب؟"
            )
            context.user_data["onboarding_step"] = "story_part2"
        else:
            await update.message.reply_text("اوکی! کسب‌وکار داری یا فقط میخوای دستیار روزمره‌ات باشم؟")
            context.user_data["onboarding_step"] = "asking_biz_or_personal"
        return ASKING_BIZ_NAME

    if step == "story_part2":
        await update.message.reply_text(
            "دو نفر، بدون تیم! ماه اول ۳۰ مشتری، ماه دوم ۱,۲۹۳ مشتری 📈\n\n"
            "فکر می‌کنی درآمد یه ماه از سال دومشون چقدر بود؟ یه حدس بزن 😏"
        )
        context.user_data["onboarding_step"] = "story_guess"
        return ASKING_BIZ_NAME

    if step == "story_guess":
        await update.message.reply_text(
            "کل سال ۲۰۲۵ رو با ۴۰۰ میلیون دلار تموم کردن 💰 "
            "باورت میشه این کسب‌وکار دونفره بعد دو سال ۲ میلیارد دلار می‌ارزه؟ 🤯\n\n"
            "با یه هوش مصنوعی مثل من! میدونی فرق من با بقیه چیه؟"
        )
        context.user_data["onboarding_step"] = "story_diff"
        return ASKING_BIZ_NAME

    if step == "story_diff":
        await update.message.reply_text(
            "من اولین نسخه از هوش مصنوعی‌های خودمختار کنترل‌شده‌ام. "
            "یاد می‌گیرم و انجام می‌دم، مثل یه آدم واقعی!\n\n"
            "قراره کل کسب‌وکارت رو برات مدیریت کنم. "
            "توی کارهای تولید، فروش و مدیریت فقط تایید یا رد می‌دی "
            "و بقیه رو من انجام می‌دم.\n\nکاتالوگ زیر رو حتماً بخون 👇"
        )
        import os
        for p in ["/app/app/data/Moonax-v1.pdf", "app/data/Moonax-v1.pdf",
                  "/mnt/user-data/uploads/Moonax-v1.pdf"]:
            if os.path.exists(p):
                try:
                    with open(p, "rb") as f:
                        await context.bot.send_document(
                            chat_id=update.effective_chat.id,
                            document=f, filename="Moonax-v1.pdf"
                        )
                except Exception:
                    pass
                break
        await update.message.reply_text("هر وقت آماده بودی بگو شروع کنیم.")
        context.user_data["onboarding_step"] = "asking_biz_or_personal"
        return ASKING_BIZ_NAME

    # ─── ۲. کسب‌وکار یا شخصی ───
    if step == "asking_biz_or_personal":
        has_biz = any(w in text for w in ["کسب","کار","فروشگاه","شرکت","مغازه","دارم","آره","بله","yes"])
        context.user_data["mode"] = "business" if has_biz else "personal"
        if has_biz:
            await update.message.reply_text("اسم کسب‌وکارت چیه؟")
            context.user_data["onboarding_step"] = "asking_biz"
        else:
            await update.message.reply_text("میخوای اسم منو چی بزاری؟")
            context.user_data["onboarding_step"] = "asking_ai_name"
        return ASKING_BIZ_NAME

    # ─── ۳. اسم کسب‌وکار ───
    if step == "asking_biz":
        context.user_data["biz_name"] = text
        await update.message.reply_text("میخوای اسم منو چی بزاری؟")
        context.user_data["onboarding_step"] = "asking_ai_name"
        return ASKING_BIZ_NAME

    # ─── ۴. اسم دستیار ───
    if step == "asking_ai_name":
        context.user_data["ai_name"] = text
        mode = context.user_data.get("mode", "business")
        if mode == "business":
            await update.message.reply_text(
                "یه متن یا ویس بفرست و اطلاعات کسب‌وکارت رو بگو:\n"
                "نام، نوع فعالیت، شهر، آدرس، تلفن، شماره حساب/شبا، "
                "نام مالک، تعداد کارمندان، محصولات اصلی"
            )
        else:
            await update.message.reply_text(
                "یه متن یا ویس بفرست:\n"
                "اسم کامل، شغل، شهر، اهدافت، چه چیزی وقتت رو می‌گیره"
            )
        context.user_data["onboarding_step"] = "asking_info"
        return ASKING_BIZ_NAME

    # ─── ۵. دریافت اطلاعات ───
    if step == "asking_info":
        # چک کن آیا کاربر الان نمیخواد وارد کنه
        text_low = text.lower().strip()
        not_now_words = ["بعدا", "بعداً", "بعد", "الان نه", "نمیخوام", "نه", "بعدا وارد",
                         "فعلا نه", "فعلاً نه", "نه ممنون", "بی‌خیال", "بعدا میگم"]
        if any(w in text_low for w in not_now_words):
            # بدون اطلاعات هم ثبت کن
            biz_name = context.user_data.get("biz_name", user.first_name + " کسب‌وکار")
            async with AsyncSessionLocal() as session:
                tenant = await create_tenant(session, user.id, biz_name)
                from app.database.models.business import TenantSettings
                from sqlalchemy import select as _sel
                ts = await session.scalar(_sel(TenantSettings).where(TenantSettings.tenant_id == tenant.id))
                if not ts:
                    ts = TenantSettings(tenant_id=tenant.id)
                    session.add(ts)
                ts.user_real_name = user.first_name
                ts.ai_name = context.user_data.get("ai_name", "دستیار")
                ts.tone = "friendly"
                ts.mode = context.user_data.get("mode", "business")
                await session.commit()
                from app.modules.subscription_service import request_trial
                _, req_id = await request_trial(session, tenant.id, user.id)
                if req_id:
                    from app.ai.outbox import queue_admin_notification
                    queue_admin_notification(user.id, req_id, "trial", tenant)
                    import app.handlers.telegram_handlers as _self
                    await _self._dispatch_admin_notifications(context)
            await update.message.reply_text(
                "باشه! اشتراکت رو فعال می‌کنم. بعد از تأیید می‌تونی اطلاعات کسب‌وکارت رو کامل کنی."
            )
            for k in ["onboarding_step", "ai_name", "tone", "mode", "biz_name"]:
                context.user_data.pop(k, None)
            return ConversationHandler.END

        # اطلاعات کافی نیست - از AI بخواه تشخیص بده
        if len(text.strip()) < 20:
            await update.message.reply_text(
                "کمی بیشتر توضیح بده تا بهتر بتونم کمکت کنم.\n"
                "یا اگه الان نمیخوای بگو «بعداً وارد می‌کنم»."
            )
            return ASKING_BIZ_NAME

        biz_name = context.user_data.get("biz_name") or text[:50] or "کسب‌وکار"

        async with AsyncSessionLocal() as session:
            tenant = await create_tenant(session, user.id, biz_name)
            from app.database.models.business import TenantSettings
            from sqlalchemy import select as _sel
            ts = await session.scalar(_sel(TenantSettings).where(TenantSettings.tenant_id == tenant.id))
            if not ts:
                ts = TenantSettings(tenant_id=tenant.id)
                session.add(ts)
            ts.user_real_name = user.first_name
            ts.ai_name = context.user_data.get("ai_name", "دستیار")
            ts.tone = context.user_data.get("tone", "friendly")
            ts.use_emoji = True
            ts.mode = context.user_data.get("mode", "business")
            ts.business_description = text
            await session.commit()
            from app.modules.subscription_service import request_trial
            _, req_id = await request_trial(session, tenant.id, user.id)
            await update.message.reply_text(
                f"ممنون! اطلاعاتت رو دریافت کردم.\n"
                f"رفتم ثبتشون کنم — وقتی آماده شد خبرت می‌کنم 🙂"
            )
            if req_id:
                from app.ai.outbox import queue_admin_notification
                queue_admin_notification(user.id, req_id, "trial", tenant)
                import app.handlers.telegram_handlers as _self
                await _self._dispatch_admin_notifications(context)

        for k in ["onboarding_step", "ai_name", "tone", "mode", "biz_name"]:
            context.user_data.pop(k, None)
        return ConversationHandler.END

    # ─── ۷. لحن ───
    if step == "asking_tone":
        is_friendly = any(w in text for w in ["صمیمی","راحت","خودمونی","محاوره","دوستانه"])
        tone = "friendly" if is_friendly else "formal"
        context.user_data["tone"] = tone

        # آپدیت TenantSettings با لحن
        async with AsyncSessionLocal() as session:
            from app.modules.tenant_service import get_tenant_for_user
            from app.database.models.business import TenantSettings
            from sqlalchemy import select as _sel
            tenant = await get_tenant_for_user(session, user.id)
            if tenant:
                ts = await session.scalar(_sel(TenantSettings).where(TenantSettings.tenant_id == tenant.id))
                if ts:
                    ts.tone = tone
                    ts.use_emoji = (tone == "friendly")
                    await session.commit()

        tone_msg = "صمیمی" if is_friendly else "رسمی"
        await update.message.reply_text(
            f"✅ لحن {tone_msg} ثبت شد. منتظر تأیید اشتراکتم تا شروع کنیم!"
        )
        for k in ["onboarding_step","ai_name","tone","mode","biz_name"]:
            context.user_data.pop(k, None)
        return ConversationHandler.END

    await update.message.reply_text("برای شروع /start بزن.")
    return ConversationHandler.END



async def receive_biz_name_voice(update, context):
    """پردازش ویس در آنبوردینگ — تبدیل به متن و ادامه."""
    from app.ai.stt_service import transcribe_voice
    user = update.effective_user

    try:
        voice = update.message.voice or update.message.audio
        if not voice:
            await update.message.reply_text("ویس دریافت نشد. متن بنویس یا دوباره ویس بفرست.")
            return ASKING_BIZ_NAME

        file = await context.bot.get_file(voice.file_id)
        import io
        buf = io.BytesIO()
        await file.download_to_memory(buf)
        buf.seek(0)
        audio_bytes = buf.read()

        text = await transcribe_voice(audio_bytes, "audio/ogg")
        if not text:
            await update.message.reply_text("متوجه نشدم. دوباره بگو یا متن بنویس.")
            return ASKING_BIZ_NAME

        await update.message.reply_text(f"🎤 شنیدم: «{text}»")
        # ادامه با متن تبدیل‌شده
        update.message.text = text
        return await receive_biz_name(update, context)

    except Exception as e:
        await update.message.reply_text("مشکلی با ویس پیش اومد. متن بنویس.")
        return ASKING_BIZ_NAME
    await update.message.reply_text("باشه، هر وقت خواستی /start بزن.")
    return ConversationHandler.END


async def cancel_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """لغو آنبوردینگ."""
    context.user_data.clear()
    await update.message.reply_text("لغو شد. هر وقت خواستی /start بزن.")
    return ConversationHandler.END


async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """دستور /reset — پاک کردن حافظه از دیتابیس."""
    user = update.effective_user
    async with AsyncSessionLocal() as session:
        kind, tenant_id, role = await _resolve_user(session, user.id)
        if kind == "none":
            await update.message.reply_text("ابتدا /start بزن.")
            return
        await reset_conversation(session, tenant_id, user.id)
    await update.message.reply_text("حافظه‌ی مکالمه پاک شد. از نو شروع کنیم 🙂")


async def _process_and_reply(update, context, session, tenant_id, user,
                             text, role="owner", image_data=None, image_mime=None,
                             person_role=None, show_thinking=False):
    """منطق مشترک: پردازش پیام + ارسال جواب + فایل‌ها."""
    import re as _re

    # پیام موقت «دارم فکر می‌کنم» فقط برای کارهای سنگین
    thinking_msg = None
    if show_thinking:
        try:
            thinking_msg = await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="دارم فکر می‌کنم..."
            )
        except Exception:
            pass

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    try:
        reply = await handle_message(session, tenant_id, user.id, text,
                                     image_data=image_data, image_mime=image_mime,
                                     role=role, person_role=person_role)
    except Exception as e:
        import logging, traceback
        logging.exception(e)
        err_detail = traceback.format_exc()[-500:]
        reply = f"⚠️ یه مشکل فنی پیش اومد. تیم فنی خبر شد."
        # ارسال خطا به ادمین
        try:
            from app.core.config import settings
            admin_id = getattr(settings, 'admin_telegram_id', None)
            if admin_id:
                await context.bot.send_message(
                    chat_id=int(admin_id),
                    text=f"🚨 خطای سیستم:\nUser: {user.id}\nTenant: {tenant_id}\n\n<code>{err_detail}</code>",
                    parse_mode="HTML",
                )
        except Exception:
            pass

    # حذف پیام موقت
    if thinking_msg:
        try:
            await thinking_msg.delete()
        except Exception:
            pass

    # تبدیل **bold** به HTML
    reply_html = _re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', reply)

    try:
        await update.message.reply_text(reply_html, parse_mode="HTML")
    except Exception:
        await update.message.reply_text(reply)

    # ارسال فایل‌ها
    for buffer, filename in pop_files(user.id):
        buffer.seek(0)
        ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
        try:
            if ext in ('ogg', 'mp3', 'wav', 'm4a'):
                # ویس دایره‌ای
                await context.bot.send_voice(
                    chat_id=update.effective_chat.id,
                    voice=buffer,
                )
            else:
                await context.bot.send_document(
                    chat_id=update.effective_chat.id,
                    document=buffer,
                    filename=filename,
                )
        except Exception:
            pass

    # ارسال پیام‌های صف
    from app.ai.outbox import pop_messages
    for msg in pop_messages(user.id):
        try:
            if msg.get("type") == "photo":
                import io as _io
                await context.bot.send_photo(
                    chat_id=msg["chat_id"],
                    photo=_io.BytesIO(msg["photo_bytes"]),
                    caption=msg.get("caption") or "",
                )
            elif msg.get("type") == "resend_file":
                ftype = msg.get("file_type", "document")
                fid = msg.get("file_id")
                cap = msg.get("caption") or ""
                cid = msg["chat_id"]
                try:
                    if ftype == "photo":
                        await context.bot.send_photo(chat_id=cid, photo=fid, caption=cap)
                    elif ftype == "voice":
                        await context.bot.send_voice(chat_id=cid, voice=fid, caption=cap)
                    elif ftype == "video":
                        await context.bot.send_video(chat_id=cid, video=fid, caption=cap)
                    else:
                        await context.bot.send_document(chat_id=cid, document=fid, caption=cap)
                except Exception:
                    pass
                import io as _io
                buf = msg.get("document_buf")
                if buf:
                    if not hasattr(buf, 'read'):
                        buf = _io.BytesIO(buf)
                    buf.seek(0)
                    await context.bot.send_document(
                        chat_id=msg["chat_id"],
                        document=buf,
                        filename=msg.get("filename", "file"),
                        caption=msg.get("caption") or "",
                    )
            else:
                msg_text = msg.get("text", "")
                msg_html = _re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', msg_text)
                try:
                    await context.bot.send_message(
                        chat_id=msg["chat_id"], text=msg_html, parse_mode="HTML"
                    )
                except Exception:
                    await context.bot.send_message(
                        chat_id=msg["chat_id"], text=msg_text
                    )
        except Exception:
            pass

    await _dispatch_admin_notifications(context)


async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """هندلر اصلی — هر پیام متنی."""
    user = update.effective_user
    text = update.message.text

    allowed, rate_msg = check_rate_limit(user.id)
    if not allowed:
        await update.message.reply_text(rate_msg)
        return

    # آیا کاربر منتظر وارد کردن رمز لینک دعوت است؟
    if context.user_data.get("credential_step"):
        pass  # credential_step handler below takes care of it
    elif await _try_invite_password(update, context):
        return

    # آیا کاربر می‌پرسد «چی شنیدی از ویسم؟»
    if text and _is_asking_voice_transcript(text):
        last = context.user_data.get("last_voice_text")
        if last:
            await update.message.reply_text(f"شنیدم: «{last}»")
        else:
            await update.message.reply_text("هنوز ویسی نفرستادی که برات بخونم.")
        return

    # آیا کاربر در جریان credential هست؟
    cred_step = context.user_data.get("credential_step")
    if cred_step:
        async with AsyncSessionLocal() as session:

            # ─── normalize اعداد فارسی ───
            def normalize_digits(s: str) -> str:
                fa_digits = "۰۱۲۳۴۵۶۷۸۹"
                for i, d in enumerate(fa_digits):
                    s = s.replace(d, str(i))
                return s

            text_normalized = normalize_digits(text.strip()) if text else ""

            # ─── مرحله ۱: نام کاربری ───
            if cred_step == "username":
                if not text_normalized.isdigit() or len(text_normalized) != 10:
                    await update.message.reply_text(
                        "⚠️ نام کاربری باید کد ملی ۱۰ رقمی باشه.\n"
                        "دوباره وارد کن:"
                    )
                    return
                context.user_data["pending_username"] = text_normalized
                context.user_data["credential_step"] = "password"
                await update.message.reply_text(
                    "گذرواژه‌ات رو وارد کن (شماره تماس ثبت‌شده):"
                )
                return

            # ─── مرحله ۲: گذرواژه ───
            elif cred_step == "password":
                token = context.user_data.get("pending_invite_token", "")
                fail_count = context.user_data.get("credential_fails", 0)

                if fail_count >= 6:
                    context.user_data.pop("credential_step", None)
                    context.user_data.pop("pending_invite_token", None)
                    context.user_data.pop("credential_fails", None)
                    await update.message.reply_text(
                        "🔒 لینک قفل شد — ۶ بار اشتباه وارد کردی.\n"
                        "از کارفرما بخواه لینک جدید بفرسته."
                    )
                    return

                ok, msg = await persons_service.consume_invite_link(
                    session, token, user.id,
                    telegram_username=user.username,
                    full_name=user.full_name,
                    password_attempt=normalize_digits(text.strip()),
                )

                if msg == "WRONG_PASSWORD":
                    fail_count += 1
                    context.user_data["credential_fails"] = fail_count
                    remaining = 6 - fail_count
                    await update.message.reply_text(
                        f"⚠️ گذرواژه اشتباهه. ({fail_count} از ۶ تلاش)\n"
                        f"شماره تماس ثبت‌شده رو وارد کن ({remaining} تلاش باقیمونده):"
                    )
                    return

                if msg == "PASSWORD_REQUIRED":
                    context.user_data["credential_step"] = "username"
                    await update.message.reply_text(
                        "⚠️ نام کاربری تأیید نشد.\n"
                        "کد ملی‌ات رو دوباره وارد کن:"
                    )
                    return

                # موفق
                context.user_data.pop("pending_invite_token", None)
                context.user_data.pop("credential_fails", None)
                context.user_data.pop("onboarding_step", None)

                if ok and msg.endswith("|CHANGE_CREDENTIALS"):
                    real_msg = msg[:-len("|CHANGE_CREDENTIALS")]
                    await update.message.reply_text(real_msg)
                    context.user_data["credential_step"] = "new_username"
                elif ok:
                    context.user_data.pop("credential_step", None)
                    await update.message.reply_text(msg)
                    await update.message.reply_text("هر وقت کاری داشتی بگو 😊")
                    # اطلاع‌رسانی به کارفرما
                    try:
                        from app.modules.notification_service import notify_owner_member_joined
                        person = await persons_service.get_person_by_telegram(session, user.id)
                        if person:
                            await notify_owner_member_joined(
                                context.bot, session, person.tenant_id, person
                            )
                    except Exception:
                        pass
                else:
                    context.user_data.pop("credential_step", None)
                    await update.message.reply_text(msg)
                return

            # ─── مرحله ۳: نام کاربری جدید ───
            elif cred_step == "new_username":
                import re
                if not re.match(r'^[a-zA-Z0-9_]{5,30}$', text.strip()):
                    await update.message.reply_text(
                        "⚠️ نام کاربری باید:\n"
                        "• حداقل ۵ کاراکتر\n"
                        "• فقط حروف لاتین، عدد یا _\n\n"
                        "دوباره وارد کن:"
                    )
                    return
                result = await persons_service.change_credentials(
                    session, user.id, new_username=text.strip()
                )
                if result.startswith("✅"):
                    context.user_data["credential_step"] = "new_password"
                    await update.message.reply_text(
                        f"{result}\n\n"
                        "حالا گذرواژه جدیدت رو بفرست:\n"
                        "• حداقل ۸ کاراکتر\n"
                        "• ترکیبی از حروف و عدد:"
                    )
                else:
                    await update.message.reply_text(result)
                return

            # ─── مرحله ۴: گذرواژه جدید ───
            elif cred_step == "new_password":
                if len(text.strip()) < 8:
                    await update.message.reply_text(
                        "⚠️ گذرواژه باید حداقل ۸ کاراکتر باشه.\n"
                        "دوباره وارد کن:"
                    )
                    return
                result = await persons_service.change_credentials(
                    session, user.id, new_password=text.strip()
                )
                # پاک کردن همه state ها
                for k in ["credential_step", "onboarding_step", "pending_invite_token",
                          "credential_fails", "pending_username"]:
                    context.user_data.pop(k, None)

                await update.message.reply_text(
                    "✅ نام کاربری و گذرواژه‌ات ثبت شد!\n\n"
                    "🔒 محتوای چتت کاملاً خصوصیه — حتی کارفرما نمی‌تونه ببینه.\n\n"
                    "هر وقت کاری داشتی بگو 😊"
                )
                return

    async with AsyncSessionLocal() as session:
        kind, tenant_id, role = await _resolve_user(session, user.id)

        if kind == "none":
            # شاید تازه credential وارد کرده — یه بار دیگه refresh کن
            await session.refresh(session.identity_map.get(('persons', user.id)) or object())
            kind, tenant_id, role = await _resolve_user(session, user.id)

        if kind == "none":
            await update.message.reply_text("برای شروع، دستور /start رو بزن.")
            return

        # برای کارفرما، بررسی اعتبار اشتراک
        if kind == "owner":
            access_ok, reason, tenant = await check_access(session, user.id)
            if not access_ok:
                if reason == "pending_approval":
                    await update.message.reply_text(
                        "⏳ حساب کاربریت در انتظار تأیید ادمین هست.\n"
                        "معمولاً خیلی سریع بررسی می‌شه — کمی صبر کن! 🙂"
                    )
                elif reason == "expired":
                    from app.core.config import settings
                    await update.message.reply_text(
                        f"⏳ دوره‌ی اشتراکت تموم شده.\n\n"
                        f"برای تمدید، مبلغ رو به این شماره کارت پرداخت کن:\n"
                        f"💳 {settings.payment_card_number}\n"
                        f"👤 {settings.payment_card_holder}\n\n"
                        f"رسیدت رو عکس بگیر و همینجا بفرست تا تأیید بشه ✅"
                    )
                else:
                    await update.message.reply_text("برای شروع، دستور /start رو بزن.")
                return

            # بازگردانی import — فقط کارفرما
            if text and any(w in text for w in ["برگردون", "بازگردان", "undo", "rollback"]):
                result = await rollback_last_import(session, user.id)
                await update.message.reply_text(result)
                return

        # برای مشتری/کارمند/همکار/پارتنر:
        if kind == "person":
            from app.modules import communication_service

            # آیا این پیام، جوابِ یک پیام گروهی (broadcast) است؟
            is_reply = await communication_service.record_broadcast_reply(
                session, tenant_id, user.id, text
            )
            if is_reply:
                await update.message.reply_text(
                    "✅ جوابت ثبت شد و به مدیریت رسید. ممنون!"
                )
                return

            # پیام عادی — ذخیره‌ی گفت‌وگو
            person = await persons_service.get_person_by_telegram(session, user.id)
            if person:
                is_urgent = communication_service.detect_explicit_urgency(text)
                contact_msg = await communication_service.save_contact_message(
                    session, tenant_id, person, text, is_urgent=is_urgent
                )
                # اگر صراحتاً فوری بود، همین حالا به کارفرما خبر بده
                if is_urgent and not contact_msg.urgent_notified:
                    await communication_service.notify_owner_urgent(
                        context.bot, session, tenant_id, contact_msg
                    )

        # person_role برای system prompt اختصاصی
        _person_role = role if kind == "person" else None
        await _process_and_reply(update, context, session, tenant_id, user,
                                 text, role=role, person_role=_person_role)


import random as _random

# جمله‌های متنوع «در حال گوش دادن» — برای ویس کوتاه
_VOICE_LISTENING = [
    "🎤 دارم گوش می‌دم...",
    "🎧 یه لحظه، ویست رو می‌شنوم...",
    "🎤 در حال گوش دادن به پیامت...",
    "👂 دارم پیام صوتیت رو بررسی می‌کنم...",
    "🎧 یه لحظه صبر کن، ویست رو پردازش می‌کنم...",
    "🎤 پیامت رو دریافت کردم، دارم گوشش می‌دم...",
    "👂 یه لحظه، دارم حرفت رو می‌فهمم...",
    "🎧 ویست رسید، در حال پردازش...",
    "🎤 صبر کن، دارم به پیامت گوش می‌دم...",
    "👂 یه ثانیه، ویست رو می‌شنوم...",
]

# جمله برای ویس بلند (بیشتر از ۳۰ ثانیه)
_VOICE_LONG = "🎤 ویست طولانیه — چند لحظه صبر کن تا کامل گوشش بدم..."


def _is_asking_voice_transcript(text: str) -> bool:
    """آیا کاربر می‌پرسد متن ویسش چه بود؟"""
    t = text.strip()
    # باید هم به «ویس/صوت/شنیدن» اشاره کند هم حالت پرسشی داشته باشد
    has_voice = any(w in t for w in ["ویس", "صوت", "شنید", "گفتم"])
    has_ask = any(w in t for w in ["چی", "چه", "ببینم", "بگو", "نشون", "متن"])
    return has_voice and has_ask and len(t) < 60


async def voice_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """هندلر دریافت ویس — تبدیل به متن و پردازش."""
    from app.ai.stt_service import transcribe_voice

    user = update.effective_user

    allowed, rate_msg = check_rate_limit(user.id)
    if not allowed:
        await update.message.reply_text(rate_msg)
        return

    async with AsyncSessionLocal() as session:
        kind, tenant_id, role = await _resolve_user(session, user.id)
        if kind == "none":
            await update.message.reply_text("ابتدا /start بزن.")
            return

        voice = update.message.voice or update.message.audio
        if not voice:
            return

        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

        # پیام «در حال گوش دادن»:
        #  - ویس بلند (>۳۰ ثانیه): همیشه پیام بده
        #  - ویس کوتاه: فقط با احتمال ۳۰٪ (۳ از هر ۱۰ بار)، رندوم
        duration = getattr(voice, "duration", 0) or 0
        if duration > 30:
            await update.message.reply_text(_VOICE_LONG)
        elif _random.random() < 0.3:
            await update.message.reply_text(_random.choice(_VOICE_LISTENING))

        file = await voice.get_file()
        audio_bytes = await file.download_as_bytearray()

        text, err = await transcribe_voice(bytes(audio_bytes), src_ext="ogg")
        if err:
            await update.message.reply_text(f"⚠️ {err}")
            return

        # متن ویس را ذخیره کن تا اگر کاربر پرسید «چی شنیدی؟» بشود نشانش داد.
        # نمایش مستقیم متن غیرفعال است — مستقیم پردازش می‌شود.
        context.user_data["last_voice_text"] = text

        await _process_and_reply(update, context, session, tenant_id, user,
                                 text, role=role)


async def file_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """هندلر دریافت فایل — import اکسل."""
    user = update.effective_user
    document = update.message.document
    if not document:
        return

    fname = document.file_name or ""
    if not fname.endswith((".xlsx", ".xls")):
        await update.message.reply_text("⚠️ فقط فایل‌های اکسل (.xlsx) پشتیبانی می‌شه.")
        return

    allowed, rate_msg = check_rate_limit(user.id)
    if not allowed:
        await update.message.reply_text(rate_msg)
        return

    async with AsyncSessionLocal() as session:
        kind, tenant_id, role = await _resolve_user(session, user.id)
        if kind == "none":
            await update.message.reply_text("ابتدا /start بزن.")
            return
        if kind != "owner":
            await update.message.reply_text(
                "📥 وارد کردن فایل اکسل فقط در دسترس کارفرماست."
            )
            return

        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

        file = await document.get_file()
        file_bytes = await file.download_as_bytearray()

        preview_msg, data_type = await preview_import(bytes(file_bytes))
        await update.message.reply_text(preview_msg)
        if not data_type:
            return

        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
        report, result_buf, result_filename = await do_import(
            session, tenant_id, user.id, bytes(file_bytes)
        )
        await update.message.reply_text(report)

        if result_buf and result_filename:
            await context.bot.send_document(
                chat_id=update.effective_chat.id,
                document=result_buf,
                filename=result_filename,
            )


async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    هندلر دریافت عکس.
    - اگر کاربر کپشن «لوگو» داشته باشد → ذخیره به‌عنوان لوگوی فروشگاه
    - در غیر این صورت → عکس به AI داده می‌شود تا تحلیل/استفاده کند
      (رسید هزینه، عکس مشتری/کالا/کارمند، یا توصیف)
    """
    user = update.effective_user

    allowed, rate_msg = check_rate_limit(user.id)
    if not allowed:
        await update.message.reply_text(rate_msg)
        return

    async with AsyncSessionLocal() as session:
        kind, tenant_id, role = await _resolve_user(session, user.id)
        if kind == "none":
            await update.message.reply_text("ابتدا /start بزن.")
            return

        photo = update.message.photo[-1]
        file = await photo.get_file()
        photo_bytes = bytes(await file.download_as_bytearray())
        caption = (update.message.caption or "").strip()

        # حالت لوگو: کپشن صریحاً «لوگو» باشد — فقط کارفرما
        if caption and "لوگو" in caption:
            if kind != "owner":
                await update.message.reply_text(
                    "تنظیم لوگو فقط در دسترس کارفرماست."
                )
                return
            if len(photo_bytes) > 2_000_000:
                await update.message.reply_text(
                    "⚠️ حجم عکس زیاده. یه عکس کوچیک‌تر بفرست (زیر ۲ مگابایت)."
                )
                return
            result = await save_tenant_logo(session, tenant_id, photo_bytes, "image/jpeg")
            await update.message.reply_text(
                result + "\n\nاز این به بعد روی فاکتورها و گزارش‌های PDF نمایش داده می‌شه."
            )
            return

        # ذخیره فایل در حافظه
        try:
            from app.modules.memory_service import save_file_record
            tg_file = update.message.photo[-1] if update.message.photo else None
            file_id = tg_file.file_id if tg_file else None
            await save_file_record(
                session, tenant_id,
                sender_telegram_id=user.id,
                sender_role=role,
                file_type="photo",
                file_id=file_id,
                caption=caption,
            )
        except Exception:
            pass

        # حالت عادی: عکس را به AI بده + توی دیتابیس موقت ذخیره کن
        pending_uploads.set_upload(user.id, photo_bytes, "image/jpeg")

        # ذخیره موقت توی دیتابیس (برای tool calls بعدی)
        try:
            import base64
            from app.database.models.business import TenantSettings
            from sqlalchemy import select as _sel
            ts = await session.scalar(_sel(TenantSettings).where(TenantSettings.tenant_id == tenant_id))
            if ts:
                import json as _json
                pending_data = _json.dumps({
                    "photo_b64": base64.b64encode(photo_bytes).decode(),
                    "mime": "image/jpeg",
                    "caption": caption,
                }, ensure_ascii=False)
                # ذخیره در فیلد موقت
                if not ts.onboarding_data or not ts.onboarding_data.startswith('{"photo'):
                    ts.onboarding_data = pending_data
                    await session.commit()
        except Exception:
            pass

        prompt_text = caption or "این تصویر رو بررسی کن و بگو باهاش چی کار کنم."
        if not caption:
            prompt_text = "یه عکس فرستادم. باهاش چی کار کنم؟"

        await _process_and_reply(update, context, session, tenant_id, user,
                                 prompt_text, role=role, image_data=photo_bytes,
                                 image_mime="image/jpeg")

        # عکس رو بعد از پردازش نگه دار (برای tool calls بعدی)
        # pending_uploads.clear_upload(user.id)  # ← این رو کامنت کردیم


# ─────────────────────────────────────────────
# ارسال notification‌های ادمین
# ─────────────────────────────────────────────

async def _dispatch_admin_notifications(context):
    """notification‌های ادمین رو از صف بگیر و بفرست."""
    from app.ai.outbox import pop_admin_notifications
    from app.core.config import settings
    import io as _io

    for notif in pop_admin_notifications():
        for admin_id in settings.admin_id_list:
            try:
                req_type_fa = "تست رایگان" if notif["request_type"] == "trial" else "پرداخت اشتراک"
                text = (
                    f"🔔 درخواست جدید — {req_type_fa}\n"
                    f"🏢 کسب‌وکار: {notif['tenant_name']}\n"
                    f"👤 تلگرام: {notif['owner_telegram_id']}\n"
                    f"🆔 شناسه درخواست: {notif['request_id']}\n\n"
                    f"برای تأیید: /approve_{notif['request_id']}_30\n"
                    f"برای رد: /reject_{notif['request_id']}\n\n"
                    f"(عدد بعد از approve = تعداد روز اشتراک)"
                )
                await context.bot.send_message(chat_id=admin_id, text=text)
                if notif.get("receipt_bytes"):
                    await context.bot.send_photo(
                        chat_id=admin_id,
                        photo=_io.BytesIO(notif["receipt_bytes"]),
                        caption="📎 رسید پرداخت",
                    )
            except Exception:
                pass


async def admin_command_handler(update, context: ContextTypes.DEFAULT_TYPE):
    """
    هندلر دستورات ادمین:
      /approve_<id>_<days>   تأیید اشتراک
      /reject_<id>           رد اشتراک
      /tenants               لیست کارفرماها
      /suspend_<tenant_id>   تعلیق کارفرما
      /unsuspend_<tenant_id> رفع تعلیق
      /delete_tenant_<id>    حذف کارفرما
    """
    from app.core.config import settings
    from app.database.base import AsyncSessionLocal
    from app.modules.subscription_service import approve_request, reject_request
    from app.database.models.tenant import Tenant
    from sqlalchemy import select as _sel

    user = update.effective_user
    if user.id not in settings.admin_id_list:
        return

    text = update.message.text or ""
    parts = text.strip().split(maxsplit=1)
    cmd = parts[0].lstrip("/")
    extra = parts[1] if len(parts) > 1 else ""

    # ─── لیست کارفرماها ───
    if cmd == "tenants":
        async with AsyncSessionLocal() as session:
            tenants = (await session.scalars(
                _sel(Tenant).order_by(Tenant.id.desc()).limit(50)
            )).all()
            if not tenants:
                await update.message.reply_text("هیچ کارفرمایی نیست.")
                return
            lines = [f"📋 کارفرماها ({len(tenants)}):\n"]
            for t in tenants:
                status = "✅" if t.is_active else "🔴"
                sub = t.subscription_status or "—"
                lines.append(f"{status} [{t.id}] {t.name} — {sub} — {t.owner_telegram_id}")
            lines.append("\nدستورات:")
            lines.append("/suspend_<id> | /unsuspend_<id> | /delete_tenant_<id>")
            await update.message.reply_text("\n".join(lines))
        return

    # ─── تعلیق کارفرما ───
    if cmd.startswith("suspend_"):
        try:
            tid = int(cmd.split("_")[1])
        except Exception:
            await update.message.reply_text("فرمت: /suspend_<tenant_id>")
            return
        async with AsyncSessionLocal() as session:
            tenant = await session.get(Tenant, tid)
            if not tenant:
                await update.message.reply_text("کارفرما پیدا نشد.")
                return
            tenant.is_active = False
            tenant.subscription_status = "suspended"
            await session.commit()
            await update.message.reply_text(f"✅ کارفرما «{tenant.name}» تعلیق شد.")
            try:
                await context.bot.send_message(
                    chat_id=tenant.owner_telegram_id,
                    text="⚠️ دسترسی شما به سیستم موقتاً تعلیق شده. برای اطلاعات بیشتر با پشتیبانی تماس بگیرید."
                )
            except Exception:
                pass
        return

    # ─── رفع تعلیق ───
    if cmd.startswith("unsuspend_"):
        try:
            tid = int(cmd.split("_")[1])
        except Exception:
            await update.message.reply_text("فرمت: /unsuspend_<tenant_id>")
            return
        async with AsyncSessionLocal() as session:
            tenant = await session.get(Tenant, tid)
            if not tenant:
                await update.message.reply_text("کارفرما پیدا نشد.")
                return
            tenant.is_active = True
            tenant.subscription_status = "active"
            await session.commit()
            await update.message.reply_text(f"✅ کارفرما «{tenant.name}» فعال شد.")
            try:
                await context.bot.send_message(
                    chat_id=tenant.owner_telegram_id,
                    text="✅ دسترسی شما به سیستم مجدداً فعال شد."
                )
            except Exception:
                pass
        return

    # ─── حذف کارفرما ───
    if cmd.startswith("delete_tenant_"):
        try:
            tid = int(cmd.split("_")[2])
        except Exception:
            await update.message.reply_text("فرمت: /delete_tenant_<tenant_id>")
            return
        async with AsyncSessionLocal() as session:
            tenant = await session.get(Tenant, tid)
            if not tenant:
                await update.message.reply_text("کارفرما پیدا نشد.")
                return
            name = tenant.name
            tenant.is_active = False
            tenant.subscription_status = "deleted"
            await session.commit()
            await update.message.reply_text(f"🗑 کارفرما «{name}» حذف شد.")
        return

    # ─── تأیید اشتراک ───
    if cmd.startswith("approve_"):
        segments = cmd.split("_")
        try:
            req_id = int(segments[1])
            days = int(segments[2]) if len(segments) > 2 else 30
        except (ValueError, IndexError):
            await update.message.reply_text("فرمت: /approve_<id>_<days>")
            return

        async with AsyncSessionLocal() as session:
            ok, admin_msg, tenant, owner_msg = await approve_request(
                session, req_id, user.id,
                admin_message=extra or None,
                days=days,
            )
            await update.message.reply_text(admin_msg)
            if ok and tenant:
                try:
                    await context.bot.send_message(
                        chat_id=tenant.owner_telegram_id, text=owner_msg
                    )
                except Exception:
                    pass

    elif cmd.startswith("reject_"):
        try:
            req_id = int(cmd.split("_")[1])
        except (ValueError, IndexError):
            await update.message.reply_text("فرمت: /reject_<id>")
            return

        async with AsyncSessionLocal() as session:
            ok, admin_msg, owner_tid = await reject_request(
                session, req_id, user.id, reason=extra or None
            )
            await update.message.reply_text(admin_msg)
            if ok and owner_tid:
                try:
                    await context.bot.send_message(
                        chat_id=owner_tid,
                        text="متأسفم، درخواستت تأیید نشد." + (f"\nدلیل: {extra}" if extra else "")
                    )
                except Exception:
                    pass
    from app.core.config import settings
    from app.database.base import AsyncSessionLocal
    from app.modules.subscription_service import approve_request, reject_request

    user = update.effective_user
    if user.id not in settings.admin_id_list:
        return

    text = update.message.text or ""
    parts = text.strip().split(maxsplit=1)
    cmd = parts[0].lstrip("/")
    extra = parts[1] if len(parts) > 1 else ""

    if cmd.startswith("approve_"):
        # /approve_5_45  یا  /approve_5_30  پیام اختیاری
        segments = cmd.split("_")
        try:
            req_id = int(segments[1])
            days = int(segments[2]) if len(segments) > 2 else 30
        except (ValueError, IndexError):
            await update.message.reply_text("فرمت: /approve_<id>_<days>")
            return

        async with AsyncSessionLocal() as session:
            ok, admin_msg, tenant, owner_msg = await approve_request(
                session, req_id, user.id,
                admin_message=extra or None,
                days=days,
            )
            await update.message.reply_text(admin_msg)
            if ok and tenant:
                try:
                    await context.bot.send_message(
                        chat_id=tenant.owner_telegram_id, text=owner_msg
                    )
                except Exception:
                    pass

    elif cmd.startswith("reject_"):
        try:
            req_id = int(cmd.split("_")[1])
        except (ValueError, IndexError):
            await update.message.reply_text("فرمت: /reject_<id>")
            return

        async with AsyncSessionLocal() as session:
            ok, admin_msg, owner_tid = await reject_request(
                session, req_id, user.id, reason=extra or None
            )
            await update.message.reply_text(admin_msg)
            if ok and owner_tid:
                try:
                    await context.bot.send_message(
                        chat_id=owner_tid,
                        text="متأسفم، درخواستت تأیید نشد." + (f"\nدلیل: {extra}" if extra else "")
                    )
                except Exception:
                    pass


# ─────────────────────────────────────────────
# Background Jobs
# ─────────────────────────────────────────────

async def process_search_queue(context: ContextTypes.DEFAULT_TYPE):
    """پردازش صف جستجو."""
    from app.modules.reports.search_service import get_pending_tasks, execute_search, get_search_result
    import io as _io

    async with AsyncSessionLocal() as session:
        tasks = await get_pending_tasks(session)
        for task in tasks:
            task_id = task.id
            user_tid = task.user_telegram_id
            query = task.query
            try:
                await execute_search(session, task_id)
                msg, excel_data, fname = await get_search_result(session, task_id)
                await context.bot.send_message(chat_id=user_tid, text=msg or "جستجو تموم شد.")
                if excel_data:
                    await context.bot.send_document(
                        chat_id=user_tid,
                        document=_io.BytesIO(excel_data),
                        filename=fname or "نتایج.xlsx",
                    )
            except Exception:
                try:
                    await context.bot.send_message(
                        chat_id=user_tid,
                        text=f"⚠️ جستجوی «{query}» با خطا مواجه شد.",
                    )
                except Exception:
                    pass


async def reminder_job(context: ContextTypes.DEFAULT_TYPE):
    """بررسی یادآورها — هر دقیقه اجرا می‌شه."""
    from app.modules.reminders.service import get_due_reminders, format_reminder_alert

    async with AsyncSessionLocal() as session:
        due = await get_due_reminders(session)
        for reminder, alert_type in due:
            try:
                msg = format_reminder_alert(reminder, alert_type)
                await context.bot.send_message(
                    chat_id=reminder.user_telegram_id, text=msg
                )
                # علامت‌گذاری
                if alert_type == "pre":
                    reminder.pre_notified = True
                else:
                    reminder.due_notified = True
                await session.commit()
            except Exception:
                pass


async def weekly_report_job(context: ContextTypes.DEFAULT_TYPE):
    """گزارش هفتگی خودکار."""
    from sqlalchemy import select
    from app.database.models.tenant import Tenant
    from app.modules.reports.alerts_service import generate_weekly_report

    async with AsyncSessionLocal() as session:
        tenants = (await session.scalars(select(Tenant))).all()
        for tenant in tenants:
            if not tenant.is_active:
                continue
            try:
                report = await generate_weekly_report(session, tenant.id)
                await context.bot.send_message(
                    chat_id=tenant.owner_telegram_id,
                    text="📅 گزارش هفتگی خودکار:\n\n" + report,
                )
            except Exception:
                pass


async def critical_alerts_job(context: ContextTypes.DEFAULT_TYPE):
    """هشدارهای بحرانی روزانه."""
    from sqlalchemy import select
    from app.database.models.tenant import Tenant
    from app.modules.reports.alerts_service import check_critical_alerts

    async with AsyncSessionLocal() as session:
        tenants = (await session.scalars(select(Tenant))).all()
        for tenant in tenants:
            if not tenant.is_active:
                continue
            try:
                alerts = await check_critical_alerts(session, tenant.id)
                if alerts:
                    await context.bot.send_message(
                        chat_id=tenant.owner_telegram_id,
                        text="🚨 هشدارهای امروز:\n\n" + "\n".join(alerts),
                    )
            except Exception:
                pass


async def periodic_report_job(context: ContextTypes.DEFAULT_TYPE):
    """
    گزارش دوره‌ای — هر ساعت اجرا می‌شود و برای کارفرماهایی که
    زمان گزارششان رسیده، خلاصه‌ی گفت‌وگوها را می‌فرستد.
    """
    from datetime import datetime, timezone, timedelta
    from sqlalchemy import select
    from app.database.models.business import ReportSchedule
    from app.database.models.tenant import Tenant
    from app.modules import communication_service

    async with AsyncSessionLocal() as session:
        schedules = (await session.scalars(
            select(ReportSchedule).where(ReportSchedule.is_enabled == True)
        )).all()

        now = datetime.now(timezone.utc)
        for sched in schedules:
            # آیا زمان گزارش رسیده؟
            if sched.last_sent_at:
                last = sched.last_sent_at
                if last.tzinfo is None:
                    last = last.replace(tzinfo=timezone.utc)
                if now - last < timedelta(hours=sched.interval_hours):
                    continue

            tenant = await session.get(Tenant, sched.tenant_id)
            if not tenant or not tenant.is_active:
                continue

            # پیام‌های گزارش‌نشده
            messages = await communication_service.get_unreported_messages(
                session, sched.tenant_id
            )
            if messages:
                summary = await communication_service.get_contact_summary(
                    session, sched.tenant_id, hours=sched.interval_hours + 1
                )
                try:
                    await context.bot.send_message(
                        chat_id=tenant.owner_telegram_id,
                        text="📊 گزارش دوره‌ای گفت‌وگوها:\n\n" + summary,
                    )
                    await communication_service.mark_messages_reported(session, messages)
                except Exception:
                    pass

            sched.last_sent_at = now
            await session.commit()


async def followup_job(context: ContextTypes.DEFAULT_TYPE):
    """پیگیری‌های زمان‌بندی‌شده — هر دقیقه اجرا می‌شود."""
    from app.modules.persons_service import get_due_followups
    from app.database.models.business import PersonFollowup
    from datetime import timezone as _tz, timedelta as _td, datetime as _dt
    import io as _io

    async with AsyncSessionLocal() as session:
        due = await get_due_followups(session)
        for f in due:
            try:
                await context.bot.send_message(
                    chat_id=f.person_telegram_id,
                    text=f.message,
                )
                f.attempt_count += 1
                f.last_sent_at = _dt.now(_tz.utc)
                f.next_send_at = _dt.now(_tz.utc) + _td(minutes=f.interval_minutes)

                # اگه به سقف رسیدیم
                if f.max_attempts and f.attempt_count >= f.max_attempts:
                    f.is_active = False
                    try:
                        await context.bot.send_message(
                            chat_id=f.owner_telegram_id,
                            text=f"📋 پیگیری تموم شد — {f.attempt_count} پیام فرستادم.",
                        )
                    except Exception:
                        pass
                await session.commit()
            except Exception:
                pass


async def trial_expiry_job(context: ContextTypes.DEFAULT_TYPE):
    """بررسی trial‌های منقضی‌شده و ارسال پیام مذاکره پرداخت — هر ساعت."""
    from app.modules.subscription_service import get_expiring_trials, send_payment_reminder
    from app.database.models.tenant import SubscriptionStatus

    async with AsyncSessionLocal() as session:
        expired = await get_expiring_trials(session)
        for tenant in expired:
            try:
                msg = await send_payment_reminder(tenant)
                await context.bot.send_message(
                    chat_id=tenant.owner_telegram_id, text=msg
                )
                # وضعیت رو expired کن تا دیگه loop نزنه
                tenant.subscription_status = SubscriptionStatus.EXPIRED
                await session.commit()
            except Exception:
                pass
