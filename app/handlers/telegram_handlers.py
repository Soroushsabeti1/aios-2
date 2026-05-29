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
    """پردازش کلیک روی لینک دعوت."""
    user = update.effective_user

    async with AsyncSessionLocal() as session:
        ok, msg = await persons_service.consume_invite_link(
            session, token, user.id,
            telegram_username=user.username,
            full_name=user.full_name,
        )

        if msg == "PASSWORD_REQUIRED":
            context.user_data["pending_invite_token"] = token
            await update.message.reply_text(
                "🔑 این دعوت رمز داره.\nیوزرنیمت رو بفرست (کد ملی):"
            )
            context.user_data["credential_step"] = "username"
            return ConversationHandler.END

        # پیام ممکنه credential change بخواد
        if ok and msg.endswith("|CHANGE_CREDENTIALS"):
            real_msg = msg[:-len("|CHANGE_CREDENTIALS")]
            await update.message.reply_text(real_msg)
            context.user_data["credential_step"] = "new_username"
            return ConversationHandler.END

        await update.message.reply_text(msg)
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
        wants = any(w in text for w in ["آره","بگو","داستان","وقت","بله","ok","اوکی","yes","باشه"])
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
            msg, req_id = await request_trial(session, tenant.id, user.id)
            await update.message.reply_text("رفتم اطلاعاتت رو ثبت کنم، وقتی آماده شد خبرت می‌کنم 🙂")
            if req_id:
                queue_admin_notification(user.id, req_id, "trial", tenant)
                await _self._dispatch_admin_notifications(context)

        # ─── ۶. لحن — آخر پرسیده می‌شه ───
        context.user_data["onboarding_step"] = "asking_tone"
        await update.message.reply_text(
            "یه سوال آخر: دوست داری لحن صحبتمون چطور باشه؟\n"
            "صمیمی و راحت یا رسمی و حرفه‌ای؟"
        )
        return ASKING_BIZ_NAME

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



async def cancel_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("باشه، هر وقت خواستی /start بزن.")
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
        import logging
        logging.exception(e)
        reply = f"⚠️ یه مشکلی پیش اومد. دوباره امتحان کن.\n({type(e).__name__})"

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
            elif msg.get("type") == "document":
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
    if await _try_invite_password(update, context):
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

            # ─── مرحله ورود با لینک: یوزرنیم ───
            if cred_step == "username":
                context.user_data["pending_username"] = text
                context.user_data["credential_step"] = "password"
                await update.message.reply_text("🔑 گذرواژه‌ات رو بفرست (شماره تماس اولیه):")
                return

            # ─── مرحله ورود با لینک: پسورد ───
            elif cred_step == "password":
                token = context.user_data.get("pending_invite_token", "")
                username = context.user_data.get("pending_username", "")
                ok, msg = await persons_service.consume_invite_link(
                    session, token, user.id,
                    telegram_username=user.username,
                    full_name=user.full_name,
                    password_attempt=text,
                )
                context.user_data.pop("pending_invite_token", None)
                context.user_data.pop("pending_username", None)

                if msg in ("PASSWORD_REQUIRED", "WRONG_PASSWORD"):
                    context.user_data["credential_step"] = "username"
                    context.user_data["pending_invite_token"] = token
                    if msg == "WRONG_PASSWORD":
                        await update.message.reply_text("⚠️ گذرواژه اشتباهه. نام کاربری‌ات رو دوباره بفرست:")
                    else:
                        await update.message.reply_text("⚠️ نام کاربری یا گذرواژه اشتباهه. نام کاربری‌ات رو دوباره بفرست (کد ملی):")
                    return

                if ok and msg.endswith("|CHANGE_CREDENTIALS"):
                    real_msg = msg[:-len("|CHANGE_CREDENTIALS")]
                    await update.message.reply_text(real_msg)
                    context.user_data["credential_step"] = "new_username"
                else:
                    context.user_data.pop("credential_step", None)
                    await update.message.reply_text(msg)
                return

            # ─── تغییر credential: یوزرنیم جدید ───
            elif cred_step == "new_username":
                result = await persons_service.change_credentials(
                    session, user.id, new_username=text
                )
                if result.startswith("✅"):
                    context.user_data["credential_step"] = "new_password"
                    await update.message.reply_text(
                        f"{result}\nحالا گذرواژه جدیدت رو بفرست (حداقل ۸ کاراکتر، از حروف و عدد استفاده کن):"
                    )
                else:
                    await update.message.reply_text(result)
                return

            # ─── تغییر credential: پسورد جدید ───
            elif cred_step == "new_password":
                result = await persons_service.change_credentials(
                    session, user.id, new_password=text
                )
                context.user_data.pop("credential_step", None)
                await update.message.reply_text(
                    f"{result}\n\nمحتوای چتت کاملاً خصوصیه — حتی کارفرما نمی‌تونه ببینه."
                )
                return

    async with AsyncSessionLocal() as session:
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
            from app.modules import communication_service, persons_service

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
      /approve_<request_id>_<days>  [پیام اختیاری]
      /reject_<request_id>  [دلیل اختیاری]
    """
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
