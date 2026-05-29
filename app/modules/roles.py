"""
سیستم نقش و دسترسی (Role-Based Access).

این ماژول تعریف می‌کند:
  - چه نقش‌هایی وجود دارد
  - هر نقش به چه ابزارهایی (toolها) دسترسی دارد
  - ربات با هر نقش چه لحنی دارد

فعال‌سازی تدریجی: هر پنج نقش تعریف شده‌اند، ولی فعلاً owner و employee
کامل فعال‌اند. collaborator/customer/partner پایه‌ای هستند و در
آپدیت‌های بعدی دسترسی و رفتار کاملشان ساخته می‌شود.
"""

# ─── نقش‌ها ───
ROLE_OWNER = "owner"
ROLE_EMPLOYEE = "employee"
ROLE_COLLABORATOR = "collaborator"
ROLE_CUSTOMER = "customer"
ROLE_PARTNER = "partner"

ALL_ROLES = [ROLE_OWNER, ROLE_EMPLOYEE, ROLE_COLLABORATOR, ROLE_CUSTOMER, ROLE_PARTNER]

# نام فارسی نقش‌ها
ROLE_LABELS = {
    ROLE_OWNER: "کارفرما",
    ROLE_EMPLOYEE: "کارمند",
    ROLE_COLLABORATOR: "همکار",
    ROLE_CUSTOMER: "مشتری",
    ROLE_PARTNER: "پارتنر",
}

# نقش‌هایی که می‌توان برایشان لینک دعوت ساخت (کارفرما خودش owner است)
INVITABLE_ROLES = [ROLE_EMPLOYEE, ROLE_COLLABORATOR, ROLE_CUSTOMER, ROLE_PARTNER]


# ─── دسترسی ابزارها بر اساس نقش ───
# هر نقش یک مجموعه از ابزارها دارد. owner به همه‌چیز دسترسی دارد.

# ابزارهایی که فقط کارفرما اجازه دارد (مدیریت، مالی کل، پرسنل)
_OWNER_ONLY_TOOLS = {
    "add_customer", "update_customer", "delete_customer", "list_customers",
    "add_employee", "list_employees", "update_employee", "delete_employee",
    "add_salary_payment", "list_salary_payments",
    "add_product", "list_products", "update_product", "delete_product",
    "create_invoice", "confirm_invoice", "cancel_invoice", "list_invoices",
    "get_invoice_detail", "export_invoice_excel", "blank_invoice_excel",
    "export_invoice_pdf",
    "add_expense", "delete_expense",
    "export_excel", "get_excel_template", "export_work_log", "get_work_log_template",
    "get_report", "sales_report", "financial_report", "debtors_report",
    "inventory_report", "export_report_pdf",
    "smart_search", "web_search_task", "get_search_result",
    "update_tenant_info", "get_tenant_info",
    "check_alerts",
    "save_entity_photo", "get_entity_photo",
    # مدیریت اشخاص و دعوت
    "add_person", "list_persons", "create_invite_link", "list_invite_links",
    "revoke_invite_link", "delete_person",
    # پیگیری
    "create_followup", "stop_followup", "list_followups",
    # ارسال عکس
    "send_photo_to_person",
    # سیستم ارتباطی
    "view_messages", "set_report_schedule", "disable_report_schedule",
    "send_broadcast", "broadcast_status", "send_direct_message",
    # اشتراک
    "get_subscription_status", "submit_payment_receipt", "request_trial",
    # فیش تصفیه حساب
    "generate_settlement",
    # اطلاعات کامل و جستجوی پیشرفته
    "get_employee_detail", "search_employees", "employee_statistics",
    "get_customer_detail", "search_customers", "customer_statistics", "top_customers",
    # صوتی
    "voice_reply",
    # خروجی دسته‌جمعی
    "batch_export",
    # بکاپ
    "backup_data",
    # برند
    "save_brand_config", "get_brand_config",
    # اقساط
    "add_installment", "list_installments", "pay_installment", "overdue_installments",
    # تاریخچه خرید
    "customer_purchase_history",
    # طراحی
    "generate_poster", "generate_slide_post", "generate_catalog",
    "crop_image", "save_design_template", "batch_design",
    # پروژه و تسک
    "create_project", "get_project_info", "add_project_document", "list_projects",
    "add_task", "move_task", "list_tasks", "project_report",
    # فلو
    "create_workflow", "list_workflows", "delete_workflow", "export_workflows_excel",
    # دسترسی
    "grant_permission", "list_permissions", "revoke_permission", "export_permissions_excel",
    # گزارش روزانه
    "end_of_day_report",
    # داشبورد مالی
    "monthly_profit_loss", "cashflow_report", "monthly_comparison",
    "top_selling_products", "financial_summary",
    # اطلاعیه
    "send_announcement", "create_poll", "send_checklist",
    # لینک‌های دعوت
    "create_employee_invite_link", "create_customer_invite_link",
    "create_collaborator_invite_link", "list_invite_links",
    "revoke_invite_link", "revoke_all_invite_links",
    # TTS
    "set_voice",
}

# ابزارهای کارمند — کار خودش + ارتباط با کارفرما
_EMPLOYEE_TOOLS = {
    "add_reminder", "list_reminders", "complete_reminder", "delete_reminder",
    "send_message_to_owner",   # پیام/گزارش به کارفرما
}

# ابزارهای همکار — مثل کارمند ولی محدودتر
_COLLABORATOR_TOOLS = {
    "add_reminder", "list_reminders", "complete_reminder", "delete_reminder",
    "send_message_to_owner",
}

# ابزارهای مشتری — فقط ارتباط (دیدن حساب/خرید در آپدیت بعدی)
_CUSTOMER_TOOLS = {
    "send_message_to_owner",   # پیام/درخواست به کسب‌وکار
}

# ابزارهای پارتنر — فقط ارتباط
_PARTNER_TOOLS = {
    "send_message_to_owner",
}

# یادآور برای همه‌ی نقش‌های متصل در دسترس است
_REMINDER_TOOLS = {
    "add_reminder", "list_reminders", "complete_reminder", "delete_reminder",
}


def get_allowed_tools(role: str) -> set:
    """مجموعه‌ی ابزارهای مجاز برای یک نقش را برمی‌گرداند."""
    if role == ROLE_OWNER:
        # کارفرما به همه‌چیز دسترسی دارد
        return _OWNER_ONLY_TOOLS | _REMINDER_TOOLS
    if role == ROLE_EMPLOYEE:
        return _EMPLOYEE_TOOLS | _REMINDER_TOOLS
    if role == ROLE_COLLABORATOR:
        return _COLLABORATOR_TOOLS | _REMINDER_TOOLS
    if role == ROLE_CUSTOMER:
        return _CUSTOMER_TOOLS
    if role == ROLE_PARTNER:
        return _PARTNER_TOOLS
    return set()


def is_tool_allowed(role: str, tool_name: str) -> bool:
    """آیا این نقش اجازه‌ی استفاده از این ابزار را دارد؟"""
    return tool_name in get_allowed_tools(role)


# ─── لحن ربات بر اساس نقش ───
# این متن به system prompt اضافه می‌شود تا ربات با هر نقش متناسب حرف بزند.

_TONE_OWNER = """تو با «کارفرما» (صاحب کسب‌وکار) صحبت می‌کنی.
لحن: محترمانه، حرفه‌ای، مثل یک دستیار اجرایی قابل‌اعتماد.
او به همه‌چیز دسترسی دارد. صریح و دقیق گزارش بده."""

_TONE_EMPLOYEE = """تو با یک «کارمند» این کسب‌وکار صحبت می‌کنی.
لحن: همکارانه، دوستانه ولی منظم و کاری.
کارمند فقط به کارهای خودش دسترسی دارد — اطلاعات مالی کل شرکت،
لیست مشتریان، حقوق دیگران و مدیریت پرسنل را نمی‌تواند ببیند.
اگر چیزی خارج از اجازه‌اش خواست، مودبانه بگو این بخش فقط برای کارفرماست."""

_TONE_COLLABORATOR = """تو با یک «همکار» (نیروی پروژه‌ای) صحبت می‌کنی.
لحن: حرفه‌ای و دوستانه.
دسترسی او محدود است — فقط کارهای مربوط به همکاری‌اش."""

_TONE_CUSTOMER = """تو با یک «مشتری» این کسب‌وکار صحبت می‌کنی.
لحن: گرم، مودب، صمیمی و وفادارساز — مثل یک فروشنده‌ی خوش‌برخورد.
مشتری فقط می‌تواند درباره‌ی حساب و خریدها و اقساط خودش بپرسد.
هرگز اطلاعات کسب‌وکار یا مشتریان دیگر را فاش نکن."""

_TONE_PARTNER = """تو با یک «پارتنر تجاری» صحبت می‌کنی.
لحن: رسمی، محترمانه و برابر — مثل گفت‌وگوی دو طرف تجاری.
فقط درباره‌ی موضوعات مشترک صحبت کن."""

_TONE_MAP = {
    ROLE_OWNER: _TONE_OWNER,
    ROLE_EMPLOYEE: _TONE_EMPLOYEE,
    ROLE_COLLABORATOR: _TONE_COLLABORATOR,
    ROLE_CUSTOMER: _TONE_CUSTOMER,
    ROLE_PARTNER: _TONE_PARTNER,
}


def get_role_tone(role: str) -> str:
    """متن راهنمای لحن برای یک نقش — به system prompt اضافه می‌شود."""
    return _TONE_MAP.get(role, _TONE_OWNER)


def get_denied_message(role: str) -> str:
    """پیام مودبانه وقتی یک نقش به ابزاری دسترسی ندارد."""
    if role == ROLE_EMPLOYEE:
        return "این بخش فقط در دسترس کارفرماست. اگر لازمش داری، به کارفرما بگو."
    if role == ROLE_CUSTOMER:
        return "این درخواست در دسترس نیست. فقط می‌تونی درباره‌ی حساب خودت بپرسی."
    return "متأسفم، این بخش برای نقش شما در دسترس نیست."
