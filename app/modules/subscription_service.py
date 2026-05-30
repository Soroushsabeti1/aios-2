"""
سرویس اشتراک و تست رایگان.

جریان تست رایگان:
  ۱. کارفرما جدید /start می‌زند → create_tenant (trial بدون فعال‌سازی)
  ۲. درخواست تأیید به ادمین می‌رود
  ۳. ادمین تأیید می‌کند → ۳ روز trial فعال
  ۴. بعد ۳ روز، job بهش پیام می‌دهد و مذاکره برای پرداخت شروع می‌شود
  ۵. کارفرما رسید می‌فرستد → ادمین تأیید → اشتراک فعال

وضعیت‌های Tenant:
  - subscription_status=TRIAL, trial_ends_at=None  → منتظر تأیید ادمین
  - subscription_status=TRIAL, trial_ends_at set   → تست فعال
  - subscription_status=ACTIVE, subscription_ends_at set → اشتراک فعال
  - subscription_status=EXPIRED → منقضی‌شده
"""
from datetime import datetime, timezone, timedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.models.tenant import (
    Tenant, SubscriptionRequest, SubscriptionStatus, utcnow
)
from app.core.config import settings

# شماره کارت ادمین برای پرداخت — از config خوانده می‌شود
PAYMENT_CARD = getattr(settings, "payment_card_number", "6037-XXXX-XXXX-XXXX")
PAYMENT_HOLDER = getattr(settings, "payment_card_holder", "نام صاحب حساب")


# ─────────────────────────────────────────────
# درخواست تست رایگان
# ─────────────────────────────────────────────

async def request_trial(session: AsyncSession,
                        tenant_id: int,
                        owner_telegram_id: int) -> tuple[str, int | None]:
    """
    ثبت درخواست تست رایگان — پیامی برای ادمین می‌فرستد.
    خروجی: (پیام_به_کارفرما, request_id)
    """
    # چک کن قبلاً درخواست داده یا نه
    existing = await session.scalar(
        select(SubscriptionRequest).where(
            SubscriptionRequest.tenant_id == tenant_id,
            SubscriptionRequest.request_type == "trial",
            SubscriptionRequest.status == "pending",
        )
    )
    if existing:
        return ("⏳ درخواست تست رایگانت قبلاً ثبت شده و منتظر تأیید ادمینه.\n"
                "معمولاً در کمتر از چند ساعت بررسی می‌شه. صبر کن!"), None

    req = SubscriptionRequest(
        tenant_id=tenant_id,
        owner_telegram_id=owner_telegram_id,
        request_type="trial",
        status="pending",
    )
    session.add(req)
    await session.commit()

    msg = ("✅ درخواست تست رایگان ۳ روزه ثبت شد!\n"
           "⏳ داره بررسی می‌شه — معمولاً خیلی سریع تأیید می‌شه.\n"
           "وقتی تأیید شد بهت خبر می‌دم و می‌تونی شروع کنی.")
    return msg, req.id


async def get_pending_requests(session: AsyncSession,
                                request_type: str = None) -> list:
    """لیست درخواست‌های در انتظار برای ادمین."""
    q = select(SubscriptionRequest).where(
        SubscriptionRequest.status == "pending"
    )
    if request_type:
        q = q.where(SubscriptionRequest.request_type == request_type)
    q = q.order_by(SubscriptionRequest.created_at.asc())
    return (await session.scalars(q)).all()


async def approve_request(session: AsyncSession,
                          request_id: int,
                          admin_telegram_id: int,
                          admin_message: str = None,
                          days: int = None) -> tuple[bool, str, Tenant | None, str]:
    """
    تأیید درخواست توسط ادمین.
    خروجی: (موفقیت, پیام_ادمین, tenant, پیام_برای_کارفرما)
    """
    req = await session.get(SubscriptionRequest, request_id)
    if not req:
        return False, "درخواست پیدا نشد.", None, ""
    if req.status != "pending":
        return False, f"این درخواست قبلاً {req.status} شده.", None, ""

    tenant = await session.get(Tenant, req.tenant_id)
    if not tenant:
        return False, "کارفرمای مرتبط پیدا نشد.", None, ""

    req.status = "approved"
    req.approved_by = admin_telegram_id
    req.approved_at = utcnow()
    req.admin_message = admin_message

    if req.request_type == "trial":
        # فعال‌سازی تست ۳ روزه
        tenant.subscription_status = SubscriptionStatus.TRIAL
        tenant.trial_ends_at = utcnow() + timedelta(days=settings.trial_days)
        owner_msg = (
            f"خبر خوووووب، ثبت شد! 🎉 {settings.trial_days} روز کنارتم و بعدش اگه دوست داشتی حقوق ماهانه‌ام رو پرداخت می‌کنی و ادامه می‌دیم باهم 😉\n\n"
            f"بریم شروع کنیم! اول اطلاعات کامل کسب‌وکارت رو وارد کن، بعد کارمنداتو اضافه کن تا لینک دعوتشون رو بفرستم. بعدش نوبت محصولات و مشتریاست.\n\n"
            f"یا اگه میخوای راهنماییت کنم که چیکارا می‌تونیم باهم بکنیم؟"
        )
        admin_reply = f"✅ تست رایگان «{tenant.name}» فعال شد ({settings.trial_days} روز)."
    else:
        # پرداخت — فعال‌سازی اشتراک
        active_days = days or req.approved_days or 30
        req.approved_days = active_days
        tenant.subscription_status = SubscriptionStatus.ACTIVE
        tenant.subscription_ends_at = utcnow() + timedelta(days=active_days)
        owner_msg = (
            f"🎊 {admin_message or 'اشتراکت با موفقیت فعال شد!'}\n\n"
            f"✅ اشتراک {active_days} روزه‌ات فعاله.\n"
            f"تا {_iran_date_str(tenant.subscription_ends_at)} ازت هستیم 💪\n\n"
            f"هر چیزی نیاز داشتی بنویس، همینجام!"
        )
        admin_reply = f"✅ اشتراک «{tenant.name}» فعال شد ({active_days} روز)."

    await session.commit()

    # پاک کردن onboarding_step از TenantSettings
    try:
        from app.database.models.business import TenantSettings
        from sqlalchemy import select as _sel
        ts = await session.scalar(_sel(TenantSettings).where(TenantSettings.tenant_id == tenant.id))
        if ts and ts.onboarding_step:
            ts.onboarding_step = None
            ts.onboarding_data = None
            await session.commit()
    except Exception:
        pass

    return True, admin_reply, tenant, owner_msg


async def reject_request(session: AsyncSession,
                         request_id: int,
                         admin_telegram_id: int,
                         reason: str = None) -> tuple[bool, str, int | None]:
    """رد درخواست توسط ادمین."""
    req = await session.get(SubscriptionRequest, request_id)
    if not req:
        return False, "درخواست پیدا نشد.", None

    req.status = "rejected"
    req.approved_by = admin_telegram_id
    req.approved_at = utcnow()
    await session.commit()

    owner_msg = (f"متأسفم، درخواست اشتراکت تأیید نشد."
                 + (f"\nدلیل: {reason}" if reason else "")
                 + "\nاگر سؤالی داری، با پشتیبانی تماس بگیر.")
    return True, "درخواست رد شد.", req.owner_telegram_id


# ─────────────────────────────────────────────
# پیام یادآوری پرداخت (بعد از اتمام تست)
# ─────────────────────────────────────────────

async def get_expiring_trials(session: AsyncSession) -> list[Tenant]:
    """تنانت‌هایی که trial‌شان تمام شده ولی notification نخورده‌اند."""
    now = utcnow()
    trials = (await session.scalars(
        select(Tenant).where(
            Tenant.subscription_status == SubscriptionStatus.TRIAL,
            Tenant.trial_ends_at <= now,
        )
    )).all()
    return trials


async def send_payment_reminder(tenant: Tenant) -> str:
    """متن پیام یادآوری پرداخت — مذاکره انسانی."""
    return (
        f"سلام {_first_name_from_name(tenant.name)} 👋\n\n"
        f"دوره‌ی تست رایگانت تموم شد.\n"
        f"امیدوارم این چند روز مفید بوده باشه و از سیستم خوشت اومده باشه 🙂\n\n"
        f"برای اینکه بتونی ادامه بدی و داده‌هات حفظ بشه، باید اشتراک بگیری.\n\n"
        f"💳 شماره کارت: {PAYMENT_CARD}\n"
        f"👤 به نام: {PAYMENT_HOLDER}\n\n"
        f"مبلغ اشتراک ماهیانه رو پرداخت کن، رسیدش رو عکس بگیر و همینجا بفرست.\n"
        f"بعد از تأیید، بلافاصله دوباره فعال می‌شی ✅\n\n"
        f"اگه سؤالی داری یا می‌خوای بیشتر بدونی، همینجا بنویس."
    )


async def submit_payment_receipt(session: AsyncSession,
                                  tenant_id: int,
                                  owner_telegram_id: int,
                                  receipt_file_id: str) -> tuple[str, int]:
    """
    ثبت رسید پرداخت از طرف کارفرما.
    خروجی: (پیام_برای_کارفرما, request_id)
    """
    req = SubscriptionRequest(
        tenant_id=tenant_id,
        owner_telegram_id=owner_telegram_id,
        request_type="payment",
        status="pending",
        receipt_file_id=receipt_file_id,
    )
    session.add(req)
    await session.commit()
    return (
        "✅ رسیدت دریافت شد!\n"
        "⏳ داره بررسی می‌شه — معمولاً ظرف چند ساعت تأیید می‌شه.\n"
        "وقتی تأیید شد بهت خبر می‌دم 🙂"
    ), req.id


# ─────────────────────────────────────────────
# کمک‌کننده‌ها
# ─────────────────────────────────────────────

def _iran_date_str(dt: datetime) -> str:
    """تبدیل datetime به تاریخ فارسی خوانا."""
    try:
        from app.utils.jalali import to_jalali_str
        return to_jalali_str(dt.date())
    except Exception:
        return str(dt.date())


def _first_name_from_name(biz_name: str) -> str:
    """اسم اول یا نام کسب‌وکار را برمی‌گرداند."""
    return biz_name.split()[0] if biz_name else "دوست"
