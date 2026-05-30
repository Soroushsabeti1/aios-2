"""
مدل‌های موجودیت‌های کسب‌وکار — نسخه ۳.
آیدی پیشونددار، فیلدهای کامل، جداول جدید: SalaryPayment, WorkLog, SearchTask.
"""
from datetime import datetime, timezone, date
from sqlalchemy import String, BigInteger, DateTime, Date, ForeignKey, Numeric, Integer, Text, Boolean, Float, LargeBinary
from sqlalchemy.orm import Mapped, mapped_column
from app.database.base import Base


def utcnow():
    return datetime.now(timezone.utc)


class Customer(Base):
    __tablename__ = "customers"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    display_id: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    name: Mapped[str] = mapped_column(String(200), index=True)
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    email: Mapped[str | None] = mapped_column(String(120), nullable=True)
    national_id: Mapped[str | None] = mapped_column(String(20), nullable=True)
    birth_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    province: Mapped[str | None] = mapped_column(String(100), nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    postal_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    telegram_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    bale_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    rubika_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    balance: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    credit_limit: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    total_purchase: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    photo: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    photo_mime: Mapped[str | None] = mapped_column(String(30), nullable=True)
    import_batch: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Product(Base):
    __tablename__ = "products"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    display_id: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    barcode: Mapped[str | None] = mapped_column(String(50), nullable=True)
    name: Mapped[str] = mapped_column(String(200), index=True)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    unit: Mapped[str | None] = mapped_column(String(30), nullable=True)
    buy_price: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    sell_price: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    discount: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    stock: Mapped[int] = mapped_column(Integer, default=0)
    min_stock: Mapped[int] = mapped_column(Integer, default=0)
    supplier: Mapped[str | None] = mapped_column(String(200), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    photo: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    photo_mime: Mapped[str | None] = mapped_column(String(30), nullable=True)
    import_batch: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Invoice(Base):
    __tablename__ = "invoices"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    display_id: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"), nullable=True)
    customer_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    total: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    discount: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    tax: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    final_amount: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    paid: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    remaining_debt: Mapped[float] = mapped_column(Numeric(18, 2), default=0)  # مانده بدهی
    # وضعیت: draft → confirmed → paid/installment/cancelled
    status: Mapped[str] = mapped_column(String(30), default="draft")
    payment_method: Mapped[str | None] = mapped_column(String(50), nullable=True)
    invoice_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    import_batch: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class InvoiceItem(Base):
    __tablename__ = "invoice_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id", ondelete="CASCADE"))
    row_number: Mapped[int] = mapped_column(Integer, default=1)  # شماره ردیف
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"), nullable=True)
    product_name: Mapped[str] = mapped_column(String(200))
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    unit_price: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    row_discount: Mapped[float] = mapped_column(Numeric(5, 2), default=0)  # تخفیف ردیف (درصد)
    total_price: Mapped[float] = mapped_column(Numeric(18, 2), default=0)


class Installment(Base):
    """اقساط فاکتور — فقط برای فاکتورهای اقساطی."""
    __tablename__ = "installments"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id", ondelete="CASCADE"), index=True)
    installment_number: Mapped[int] = mapped_column(Integer)  # شماره قسط
    amount: Mapped[float] = mapped_column(Numeric(18, 2))
    due_date: Mapped[date] = mapped_column(Date)  # تاریخ سررسید
    payment_date: Mapped[date | None] = mapped_column(Date, nullable=True)  # تاریخ پرداخت
    # وضعیت: پرداخت شده / پرداخت نشده / تاریخ نرسیده / کنسل شده
    status: Mapped[str] = mapped_column(String(30), default="پرداخت نشده")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Expense(Base):
    __tablename__ = "expenses"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    amount: Mapped[float] = mapped_column(Numeric(18, 2))
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    expense_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    person: Mapped[str | None] = mapped_column(String(200), nullable=True)
    payment_method: Mapped[str | None] = mapped_column(String(50), nullable=True)
    ref_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    expense_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    import_batch: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Employee(Base):
    __tablename__ = "employees"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    display_id: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    name: Mapped[str] = mapped_column(String(200), index=True)
    national_id: Mapped[str | None] = mapped_column(String(20), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    birth_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    marital_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    children_count: Mapped[int] = mapped_column(Integer, default=0)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    province: Mapped[str | None] = mapped_column(String(100), nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    role: Mapped[str | None] = mapped_column(String(100), nullable=True)
    shift_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    work_mode: Mapped[str | None] = mapped_column(String(30), nullable=True)  # تمام وقت / پاره وقت / آزمایشی
    contract_type: Mapped[str | None] = mapped_column(String(30), nullable=True)  # کار / پیمانکاری / اجاره
    monthly_work_days: Mapped[int] = mapped_column(Integer, default=26)
    base_salary: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    deductions: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    bank_account: Mapped[str | None] = mapped_column(String(50), nullable=True)
    leave_days: Mapped[int] = mapped_column(Integer, default=0)
    annual_leave: Mapped[float] = mapped_column(Float, default=0)  # مرخصی استحقاقی (روز)
    insurance_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    insurance_amount: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    insurance_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    hire_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    contract_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    postal_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    bale_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    telegram_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    rubika_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    photo: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    photo_mime: Mapped[str | None] = mapped_column(String(30), nullable=True)
    import_batch: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SalaryPayment(Base):
    __tablename__ = "salary_payments"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"), index=True)
    amount: Mapped[float] = mapped_column(Numeric(18, 2))
    payment_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    period: Mapped[str | None] = mapped_column(String(20), nullable=True)
    payment_method: Mapped[str | None] = mapped_column(String(50), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class WorkLog(Base):
    __tablename__ = "work_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"), index=True)
    work_date: Mapped[date] = mapped_column(Date, index=True)
    work_hours: Mapped[float] = mapped_column(Float, default=0)
    overtime_hours: Mapped[float] = mapped_column(Float, default=0)
    is_holiday_work: Mapped[bool] = mapped_column(Boolean, default=False)
    night_hours: Mapped[float] = mapped_column(Float, default=0)
    unused_leave: Mapped[float] = mapped_column(Float, default=0)
    friday_work: Mapped[float] = mapped_column(Float, default=0)
    repair_wage: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    import_batch: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SearchTask(Base):
    """وظایف جستجوی اینترنتی — صف‌بندی شده."""
    __tablename__ = "search_tasks"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    user_telegram_id: Mapped[int] = mapped_column(BigInteger)
    query: Mapped[str] = mapped_column(Text)
    priority: Mapped[str] = mapped_column(String(20), default="instant")  # instant/medium/nightly
    status: Mapped[str] = mapped_column(String(20), default="pending")    # pending/running/done/failed
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    result_count: Mapped[int] = mapped_column(Integer, default=0)
    results_json: Mapped[str | None] = mapped_column(Text, nullable=True)    # نتایج JSON
    excel_data: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)  # فایل اکسل
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ConversationMessage(Base):
    """تاریخچه‌ی دائمی مکالمه — برای حافظه‌ی پایدار بعد از ری‌استارت."""
    __tablename__ = "conversation_messages"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    user_telegram_id: Mapped[int] = mapped_column(BigInteger, index=True)
    role: Mapped[str] = mapped_column(String(20))  # user / assistant / tool
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    context_thread_id: Mapped[int | None] = mapped_column(ForeignKey("shared_contexts.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class SharedContext(Base):
    """نخ ارتباطی — موضوع مشترک بین چند نقش."""
    __tablename__ = "shared_contexts"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    topic: Mapped[str] = mapped_column(String(200))  # «رضایی»، «فاکتور ۱۲»، «پروژه X»
    topic_type: Mapped[str | None] = mapped_column(String(50), nullable=True)  # customer/invoice/project/general
    topic_ref_id: Mapped[int | None] = mapped_column(Integer, nullable=True)  # id موجودیت مرتبط
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)  # خلاصه هوشمند
    is_resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class FileRecord(Base):
    """ثبت همه فایل‌های رد و بدل شده."""
    __tablename__ = "file_records"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    sender_telegram_id: Mapped[int] = mapped_column(BigInteger, index=True)
    sender_role: Mapped[str] = mapped_column(String(20))
    receiver_telegram_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    receiver_role: Mapped[str | None] = mapped_column(String(20), nullable=True)
    file_type: Mapped[str] = mapped_column(String(20))  # photo/document/voice/video
    file_id: Mapped[str | None] = mapped_column(String(200), nullable=True)  # telegram file_id
    file_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    caption: Mapped[str | None] = mapped_column(Text, nullable=True)
    context_thread_id: Mapped[int | None] = mapped_column(ForeignKey("shared_contexts.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class Reminder(Base):
    """یادآور — کار زمان‌دار با هشدار قبل از موعد."""
    __tablename__ = "reminders"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    user_telegram_id: Mapped[int] = mapped_column(BigInteger, index=True)
    display_id: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)  # REM-001
    title: Mapped[str] = mapped_column(String(300))
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)  # زمان انجام کار
    # هشدار چند دقیقه قبل از موعد (مثلاً 30 یعنی نیم ساعت زودتر خبر بده)
    notify_before_minutes: Mapped[int] = mapped_column(Integer, default=0)
    # وضعیت هشدارها
    pre_notified: Mapped[bool] = mapped_column(Boolean, default=False)   # هشدار قبل از موعد فرستاده شد؟
    due_notified: Mapped[bool] = mapped_column(Boolean, default=False)   # هشدار سر موعد فرستاده شد؟
    is_done: Mapped[bool] = mapped_column(Boolean, default=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Person(Base):
    """
    هر شخصی که با ربات تعامل دارد — با نقش مشخص.

    نقش‌ها:
      owner       : کارفرما (صاحب کسب‌وکار، دسترسی کامل)
      employee    : کارمند رسمی
      collaborator: همکار (نیروی غیررسمی/پروژه‌ای)
      customer    : مشتری
      partner     : پارتنرشیپ (طرف تجاری)

    حالت اتصال:
      - رکورد می‌تواند بدون telegram_id ساخته شود (ثبت‌شده ولی متصل‌نشده)
      - با کلیک روی لینک دعوت، telegram_id وصل می‌شود (متصل)

    ملاک یکتای شناسایی: telegram_id (عددی). یوزرنیم فقط اطلاعات کمکی است.
    """
    __tablename__ = "persons"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    display_id: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    role: Mapped[str] = mapped_column(String(20), index=True)  # owner/employee/collaborator/customer/partner
    full_name: Mapped[str] = mapped_column(String(200), index=True)
    # آیدی عددی تلگرام — ملاک یکتا. تا وصل نشده None است.
    telegram_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    telegram_username: Mapped[str | None] = mapped_column(String(100), nullable=True)  # اطلاعات کمکی
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    # اتصال اختیاری به رکورد موجودیت متناظر (مثلاً اگر این Person یک کارمند ثبت‌شده باشد)
    linked_employee_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), nullable=True)
    linked_customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    connected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    @property
    def is_connected(self) -> bool:
        """آیا این شخص آیدی تلگرامش وصل شده؟"""
        return self.telegram_id is not None


class InviteLink(Base):
    """
    لینک دعوت — برای متصل کردن کارمند/مشتری/همکار/پارتنر به سیستم.

    ویژگی‌های امنیتی (کارفرما هنگام ساخت انتخاب می‌کند):
      - lock_to_person_id : قفل به یک شخص خاص (فقط او می‌تواند استفاده کند)
      - expires_at        : زمان انقضا (None = بدون انقضا)
      - password          : رمز (None = بدون رمز)
      - max_uses          : حداکثر تعداد استفاده (None = نامحدود)
    """
    __tablename__ = "invite_links"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    # توکن یکتای لینک (در URL استفاده می‌شود)
    token: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    # نقشی که این لینک اعطا می‌کند
    role: Mapped[str] = mapped_column(String(20))  # employee/collaborator/customer/partner
    # نام نمایشی لینک (برای مدیریت توسط کارفرما)
    label: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # قفل به یک شخص خاص (اختیاری)
    lock_to_person_id: Mapped[int | None] = mapped_column(ForeignKey("persons.id"), nullable=True)
    # انقضا (اختیاری)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # رمز (اختیاری)
    password: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # حداکثر استفاده (None = نامحدود)
    max_uses: Mapped[int | None] = mapped_column(Integer, nullable=True)
    use_count: Mapped[int] = mapped_column(Integer, default=0)
    is_revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ContactMessage(Base):
    """
    پیام‌های دریافتی از مشتری/کارمند — ذخیره‌ی همه‌ی گفت‌وگوها.
    کارفرما می‌تواند این‌ها را ببیند یا گزارش دوره‌ای بگیرد.
    """
    __tablename__ = "contact_messages"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    person_id: Mapped[int | None] = mapped_column(ForeignKey("persons.id"), nullable=True)
    sender_name: Mapped[str] = mapped_column(String(200))
    sender_role: Mapped[str] = mapped_column(String(20))  # customer/employee/...
    sender_telegram_id: Mapped[int] = mapped_column(BigInteger, index=True)
    # متن پیام کاربر و خلاصه‌ی پاسخ ربات
    message_text: Mapped[str] = mapped_column(Text)
    bot_reply: Mapped[str | None] = mapped_column(Text, nullable=True)
    # فوریت
    is_urgent: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    urgent_notified: Mapped[bool] = mapped_column(Boolean, default=False)
    # آیا در گزارش دوره‌ای لحاظ شده؟
    reported: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class Broadcast(Base):
    """
    مأموریت پیام گروهی — کارفرما به چند نفر پیام/سؤال می‌فرستد
    و ربات جواب‌ها را جمع‌آوری می‌کند.
    """
    __tablename__ = "broadcasts"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    display_id: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)  # BRD-001
    # متن پیامی که کارفرما می‌خواهد فرستاده شود
    message_text: Mapped[str] = mapped_column(Text)
    # آیا این یک «سؤال» است که منتظر جواب می‌مانیم؟
    expects_reply: Mapped[bool] = mapped_column(Boolean, default=False)
    # وضعیت: active (در حال جمع‌آوری) / done
    status: Mapped[str] = mapped_column(String(20), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class BroadcastTarget(Base):
    """
    هر گیرنده‌ی یک پیام گروهی + جوابش.
    این تضمین می‌کند جواب هر نفر جدا و بدون قاطی‌شدن ذخیره شود.
    """
    __tablename__ = "broadcast_targets"
    id: Mapped[int] = mapped_column(primary_key=True)
    broadcast_id: Mapped[int] = mapped_column(ForeignKey("broadcasts.id", ondelete="CASCADE"), index=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("persons.id"))
    person_name: Mapped[str] = mapped_column(String(200))
    person_telegram_id: Mapped[int] = mapped_column(BigInteger)
    # وضعیت تحویل
    delivered: Mapped[bool] = mapped_column(Boolean, default=False)
    # جواب طرف (اگر منتظر جواب بودیم)
    reply_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    replied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ReportSchedule(Base):
    """
    تنظیمات گزارش دوره‌ای — کارفرما تعیین می‌کند هر چند وقت
    خلاصه‌ی گفت‌وگوهای مشتری/کارمند برایش فرستاده شود.
    """
    __tablename__ = "report_schedules"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"),
                                           unique=True, index=True)
    # فاصله‌ی گزارش به ساعت (مثلاً 2 = هر ۲ ساعت، 48 = هر ۲ روز)
    interval_hours: Mapped[int] = mapped_column(Integer, default=24)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    last_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PersonFollowup(Base):
    """
    پیگیری زمان‌بندی‌شده — کارفرما می‌خواهد هر N دقیقه به یک پرسن پیام برسد
    تا فایل ارسال کند یا کاری انجام دهد.
    """
    __tablename__ = "person_followups"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("persons.id", ondelete="CASCADE"), index=True)
    person_name: Mapped[str] = mapped_column(String(200), default="")
    person_telegram_id: Mapped[int] = mapped_column(BigInteger)
    owner_telegram_id: Mapped[int] = mapped_column(BigInteger)
    message: Mapped[str] = mapped_column(Text)
    interval_minutes: Mapped[int] = mapped_column(Integer, default=60)
    max_attempts: Mapped[int] = mapped_column(Integer, default=0)   # 0 = نامحدود
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    next_send_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    last_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# ═══════════════════════════════════════════════════════
# فاز ۲-۳: برند، عکس، طراحی، پروژه
# ═══════════════════════════════════════════════════════

class BrandConfig(Base):
    """تنظیمات برند هر tenant — لوگو، رنگ، فونت، شعار."""
    __tablename__ = "brand_configs"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), unique=True, index=True)
    logo: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    logo_mime: Mapped[str | None] = mapped_column(String(30), nullable=True)
    primary_color: Mapped[str | None] = mapped_column(String(20), nullable=True)
    secondary_color: Mapped[str | None] = mapped_column(String(20), nullable=True)
    slogan: Mapped[str | None] = mapped_column(Text, nullable=True)
    fonts_json: Mapped[str | None] = mapped_column(Text, nullable=True)  # {"title": "BTitr.ttf", "body": "BYekan.ttf"}
    tone: Mapped[str | None] = mapped_column(String(30), nullable=True)  # formal/friendly/neutral
    auto_send_approval: Mapped[bool] = mapped_column(Boolean, default=True)  # تأیید قبل ارسال
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class EntityPhoto(Base):
    """چند عکس برای هر موجودیت (محصول/مشتری/کارمند/پروژه)."""
    __tablename__ = "entity_photos"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    entity_type: Mapped[str] = mapped_column(String(30))  # employee/customer/product/project
    entity_id: Mapped[int] = mapped_column(Integer)
    photo: Mapped[bytes] = mapped_column(LargeBinary)
    photo_mime: Mapped[str] = mapped_column(String(30), default="image/jpeg")
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    caption: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DesignTemplate(Base):
    """تمپلیت طراحی ذخیره‌شده."""
    __tablename__ = "design_templates"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    size_preset: Mapped[str | None] = mapped_column(String(30), nullable=True)  # story/post/a4/custom
    width: Mapped[int] = mapped_column(Integer, default=1080)
    height: Mapped[int] = mapped_column(Integer, default=1080)
    layout_json: Mapped[str | None] = mapped_column(Text, nullable=True)  # جای متن/لوگو/عکس
    background_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    fixed_elements: Mapped[str | None] = mapped_column(Text, nullable=True)  # چی ثابت بمونه
    free_elements: Mapped[str | None] = mapped_column(Text, nullable=True)  # چی آزاد باشه
    creativity_percent: Mapped[int] = mapped_column(Integer, default=20)
    sample_image: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DesignHistory(Base):
    """تاریخچه طراحی — برای اصلاح و بایگانی."""
    __tablename__ = "design_history"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    template_id: Mapped[int | None] = mapped_column(ForeignKey("design_templates.id"), nullable=True)
    task_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    entity_type: Mapped[str | None] = mapped_column(String(30), nullable=True)  # product/project/general
    entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    prompt_used: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_image: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    output_mime: Mapped[str | None] = mapped_column(String(30), nullable=True)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(30), default="done")  # processing/done/failed
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Project(Base):
    """پروژه‌ها — حافظه و مستندات."""
    __tablename__ = "projects"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    display_id: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    documents_json: Mapped[str | None] = mapped_column(Text, nullable=True)  # مستندات جمع‌شده از چت
    brand_override_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="active")  # active/completed/archived
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# ═══════════════════════════════════════════════════════
# دسترسی‌ها، فلوها، پروژه‌ها، تسک‌ها
# ═══════════════════════════════════════════════════════

class AccessPermission(Base):
    """سطوح دسترسی — ۵ سطح."""
    __tablename__ = "access_permissions"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    level: Mapped[int] = mapped_column(Integer, default=1)  # 1-5
    grantee_type: Mapped[str] = mapped_column(String(30))  # person/role/all
    grantee_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    grantee_role: Mapped[str | None] = mapped_column(String(30), nullable=True)
    resource_type: Mapped[str] = mapped_column(String(50))  # invoice/employee/customer/file/...
    resource_filter: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON فیلتر
    resource_exclude: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON استثنا
    max_uses: Mapped[int | None] = mapped_column(Integer, nullable=True)  # None=نامحدود
    use_count: Mapped[int] = mapped_column(Integer, default=0)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    condition: Mapped[str | None] = mapped_column(Text, nullable=True)  # شرط اجرا
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class WorkFlow(Base):
    """فلوهای کاری خودکار."""
    __tablename__ = "work_flows"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    trigger_type: Mapped[str] = mapped_column(String(50))  # no_response/deadline/condition/schedule
    trigger_condition: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    target_type: Mapped[str | None] = mapped_column(String(30), nullable=True)  # person/role/all
    target_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    target_role: Mapped[str | None] = mapped_column(String(30), nullable=True)
    steps_json: Mapped[str] = mapped_column(Text)  # JSON مراحل اجرا
    max_retries: Mapped[int] = mapped_column(Integer, default=3)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TenantSettings(Base):
    """تنظیمات کسب‌وکار — لحن، مود، اطلاعات تکمیلی."""
    __tablename__ = "tenant_settings"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), unique=True)
    user_real_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    ai_name: Mapped[str | None] = mapped_column(String(100), nullable=True)  # اسم دستیار
    tone: Mapped[str] = mapped_column(String(20), default="formal")  # formal/friendly
    use_emoji: Mapped[bool] = mapped_column(Boolean, default=False)
    mode: Mapped[str] = mapped_column(String(20), default="business")  # business/personal
    business_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    business_docs_json: Mapped[str | None] = mapped_column(Text, nullable=True)  # اسناد تکمیلی
    onboarding_step: Mapped[str | None] = mapped_column(String(50), nullable=True)
    onboarding_data: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    autonomy_rules: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON قوانین خودمختاری
    voice_key: Mapped[str | None] = mapped_column(String(20), nullable=True, default="nova")
    work_start_hour: Mapped[int] = mapped_column(Integer, default=9)
    work_end_hour: Mapped[int] = mapped_column(Integer, default=18)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PersonCredential(Base):
    """یوزرنیم و پسورد کارمندان."""
    __tablename__ = "person_credentials"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("persons.id", ondelete="CASCADE"), unique=True)
    username: Mapped[str] = mapped_column(String(100), index=True)
    password_hash: Mapped[str] = mapped_column(String(200))
    must_change: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ProjectTask(Base):
    """کارت ماموریت در پروژه — ترلوی چتی."""
    __tablename__ = "project_tasks"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    task_type: Mapped[str | None] = mapped_column(String(50), nullable=True)  # گرافیک/فروش/جلسه/...
    list_type: Mapped[str] = mapped_column(String(50), default="backlog")  # backlog/this_week/next/doing/review/approved
    priority: Mapped[str] = mapped_column(String(20), default="normal")  # urgent/high/normal/low
    assignee_id: Mapped[int | None] = mapped_column(ForeignKey("persons.id"), nullable=True)
    estimated_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    actual_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    start_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    end_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    checklist_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    deliverable_to_id: Mapped[int | None] = mapped_column(ForeignKey("persons.id"), nullable=True)
    deliverable_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    quality_score: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 1-5
    require_photo_report: Mapped[bool] = mapped_column(Boolean, default=False)
    follow_up_hours: Mapped[int] = mapped_column(Integer, default=4)
    dependencies_json: Mapped[str | None] = mapped_column(Text, nullable=True)  # وابستگی‌ها
    tags_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    history_json: Mapped[str | None] = mapped_column(Text, nullable=True)  # سابقه تغییرات
    deadline_violation: Mapped[bool] = mapped_column(Boolean, default=False)
    violation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DailyReport(Base):
    """گزارش روزانه کارمند."""
    __tablename__ = "daily_reports"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("persons.id"), index=True)
    report_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    check_in: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    check_out: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    break_minutes: Mapped[int] = mapped_column(Integer, default=0)
    overtime_hours: Mapped[float] = mapped_column(Float, default=0)
    night_hours: Mapped[float] = mapped_column(Float, default=0)
    holiday_work: Mapped[bool] = mapped_column(Boolean, default=False)
    friday_work: Mapped[bool] = mapped_column(Boolean, default=False)
    tasks_json: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON تسک‌های انجام‌شده
    productivity: Mapped[float | None] = mapped_column(Float, nullable=True)  # درصد بهره‌وری
    positives: Mapped[str | None] = mapped_column(Text, nullable=True)
    negatives: Mapped[str | None] = mapped_column(Text, nullable=True)
    no_response_count: Mapped[int] = mapped_column(Integer, default=0)
    late_response_count: Mapped[int] = mapped_column(Integer, default=0)
    is_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    submitted_by: Mapped[str] = mapped_column(String(20), default="employee")  # employee/ai
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
