"""
مدل‌های هسته‌ای multi-tenant — نسخه ۲.
- Tenant: هر کسب‌وکار (کارفرما) با اطلاعات کامل + لوگو
- TenantUser: کاربران مجاز هر کارفرما
"""
import enum
from datetime import datetime, timezone
from sqlalchemy import String, BigInteger, DateTime, Enum, ForeignKey, Boolean, Text, LargeBinary, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database.base import Base


def utcnow():
    return datetime.now(timezone.utc)


class SubscriptionStatus(str, enum.Enum):
    TRIAL = "trial"
    ACTIVE = "active"
    EXPIRED = "expired"


class Tenant(Base):
    """یک کسب‌وکار مستقل داخل سیستم."""
    __tablename__ = "tenants"

    id: Mapped[int] = mapped_column(primary_key=True)
    display_id: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)  # BIZ-001
    name: Mapped[str] = mapped_column(String(200))
    owner_telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)

    # اطلاعات تماس فروشگاه
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    province: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # اطلاعات بانکی
    card_number: Mapped[str | None] = mapped_column(String(30), nullable=True)
    sheba: Mapped[str | None] = mapped_column(String(40), nullable=True)
    account_holder: Mapped[str | None] = mapped_column(String(200), nullable=True)  # نام صاحب حساب

    # لوگو (ذخیره binary در DB)
    logo: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    logo_mime: Mapped[str | None] = mapped_column(String(30), nullable=True)  # image/png, image/jpeg

    # مالیات پیش‌فرض
    default_tax_percent: Mapped[int] = mapped_column(Integer, default=9)

    # اشتراک
    subscription_status: Mapped[SubscriptionStatus] = mapped_column(
        Enum(SubscriptionStatus), default=SubscriptionStatus.TRIAL
    )
    trial_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    subscription_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    users: Mapped[list["TenantUser"]] = relationship(back_populates="tenant", cascade="all, delete-orphan")

    @property
    def is_active(self) -> bool:
        now = utcnow()
        if self.subscription_status == SubscriptionStatus.ACTIVE:
            return self.subscription_ends_at is None or self.subscription_ends_at > now
        if self.subscription_status == SubscriptionStatus.TRIAL:
            return self.trial_ends_at is not None and self.trial_ends_at > now
        return False


class TenantUser(Base):
    """کاربر مجاز یک کارفرما."""
    __tablename__ = "tenant_users"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, index=True)
    full_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    role: Mapped[str] = mapped_column(String(50), default="owner")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    tenant: Mapped["Tenant"] = relationship(back_populates="users")


class SubscriptionRequest(Base):
    """
    درخواست تست رایگان یا اشتراک — نیاز به تأیید ادمین دارد.
    نوع: trial (تست ۳ روزه) / payment (پرداخت — رسید ارسال شده)
    """
    __tablename__ = "subscription_requests"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    owner_telegram_id: Mapped[int] = mapped_column(BigInteger, index=True)
    request_type: Mapped[str] = mapped_column(String(20), default="trial")  # trial / payment
    status: Mapped[str] = mapped_column(String(20), default="pending")      # pending / approved / rejected
    # برای پرداخت: رسید تصویری
    receipt_file_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # ادمین تأیید‌کننده
    approved_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # مدت فعال‌سازی که ادمین وارد می‌کند (برای پرداخت)
    approved_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # پیام اختصاصی ادمین به کارفرما هنگام تأیید
    admin_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
