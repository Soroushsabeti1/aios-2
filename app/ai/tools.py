"""
تعریف ابزارها (tools) — نسخه ۳.
کامل: مشتری، کارمند، کالا، هزینه، فاکتور، گزارش، سرچ، هشدار، فیلتر، کارفرما.
"""

TOOLS = [
    # ─── مشتریان ───
    {"type": "function", "function": {
        "name": "add_customer",
        "description": "ثبت مشتری جدید",
        "parameters": {"type": "object", "properties": {
            "name": {"type": "string", "description": "نام و نام خانوادگی"},
            "phone": {"type": "string"},
            "email": {"type": "string"},
            "national_id": {"type": "string", "description": "کد ملی"},
            "birth_date": {"type": "string", "description": "تاریخ تولد (هر شکلی)"},
            "city": {"type": "string"},
            "address": {"type": "string"},
            "credit_limit": {"type": "number", "description": "سقف بدهی"},
            "code": {"type": "string", "description": "کد مشتری"},
            "note": {"type": "string"},
        }, "required": ["name"]},
    }},
    {"type": "function", "function": {
        "name": "list_customers",
        "description": "نمایش لیست مشتریان",
        "parameters": {"type": "object", "properties": {
            "filter": {"type": "string", "enum": ["all", "debtors", "vip", "by_city"]},
            "city": {"type": "string"},
            "sort_by_debt": {"type": "boolean"},
            "limit": {"type": "integer"},
        }},
    }},
    {"type": "function", "function": {
        "name": "update_customer",
        "description": "ویرایش اطلاعات مشتری",
        "parameters": {"type": "object", "properties": {
            "name": {"type": "string", "description": "نام برای پیدا کردن"},
            "new_phone": {"type": "string"},
            "new_city": {"type": "string"},
            "new_address": {"type": "string"},
            "new_credit_limit": {"type": "number"},
        }, "required": ["name"]},
    }},
    {"type": "function", "function": {
        "name": "delete_customer",
        "description": "حذف مشتری",
        "parameters": {"type": "object", "properties": {
            "name": {"type": "string"}}, "required": ["name"]},
    }},

    # ─── فروش و فاکتور ───
    {"type": "function", "function": {
        "name": "create_invoice",
        "description": "ساخت پیش‌فاکتور (draft). بعد تأیید کارفرما ثبت نهایی می‌شه.",
        "parameters": {"type": "object", "properties": {
            "customer_name": {"type": "string"},
            "items": {"type": "array", "items": {"type": "object", "properties": {
                "product_name": {"type": "string"},
                "quantity": {"type": "integer"},
                "unit_price": {"type": "number"},
            }, "required": ["product_name", "quantity"]}},
            "discount": {"type": "number", "description": "مبلغ تخفیف"},
            "tax_percent": {"type": "number", "description": "درصد مالیات (پیش‌فرض: ۹٪)"},
            "paid": {"type": "number", "description": "مبلغ پرداختی"},
            "payment_method": {"type": "string", "description": "نقد/کارت/حواله"},
            "invoice_date": {"type": "string", "description": "تاریخ فاکتور"},
            "note": {"type": "string"},
        }, "required": ["customer_name", "items"]},
    }},
    {"type": "function", "function": {
        "name": "confirm_invoice",
        "description": "تأیید فاکتور → کسر از انبار + ثبت بدهی مشتری. کارفرما باید بگه «تأیید».",
        "parameters": {"type": "object", "properties": {
            "invoice_display_id": {"type": "string", "description": "شناسه فاکتور (INV-001). خالی = آخرین پیش‌فاکتور."},
        }},
    }},
    {"type": "function", "function": {
        "name": "cancel_invoice",
        "description": "کنسل کردن فاکتور. موجودی و بدهی برمی‌گرده.",
        "parameters": {"type": "object", "properties": {
            "invoice_display_id": {"type": "string"},
        }},
    }},
    {"type": "function", "function": {
        "name": "list_invoices",
        "description": "لیست فاکتورها. فیلتر بر اساس وضعیت یا مشتری.",
        "parameters": {"type": "object", "properties": {
            "status": {"type": "string", "enum": ["draft", "confirmed", "paid", "cancelled"]},
            "customer_name": {"type": "string"},
            "limit": {"type": "integer"},
        }},
    }},
    {"type": "function", "function": {
        "name": "get_invoice_detail",
        "description": "جزئیات یک فاکتور خاص.",
        "parameters": {"type": "object", "properties": {
            "invoice_display_id": {"type": "string", "description": "شناسه مثل INV-001"},
        }, "required": ["invoice_display_id"]},
    }},
    {"type": "function", "function": {
        "name": "export_invoice_excel",
        "description": "اکسل فاکتور حرفه‌ای با فرمول + لوگو + مهر. مثال: «اکسل فاکتور INV-001 رو بده»",
        "parameters": {"type": "object", "properties": {
            "invoice_display_id": {"type": "string"},
        }, "required": ["invoice_display_id"]},
    }},
    {"type": "function", "function": {
        "name": "blank_invoice_excel",
        "description": "اکسل فاکتور خالی با فرمول آماده — برای استفاده دستی کارفرما.",
        "parameters": {"type": "object", "properties": {}},
    }},
    {"type": "function", "function": {
        "name": "export_invoice_pdf",
        "description": "PDF فاکتور فارسی (راست‌چین + لوگو + مهر). مثال: «پی‌دی‌اف فاکتور INV-001»",
        "parameters": {"type": "object", "properties": {
            "invoice_display_id": {"type": "string"},
        }, "required": ["invoice_display_id"]},
    }},
    {"type": "function", "function": {
        "name": "export_report_pdf",
        "description": "PDF گزارش فارسی. مثال: «گزارش مالی این ماه رو پی‌دی‌اف کن»",
        "parameters": {"type": "object", "properties": {
            "report_type": {"type": "string", "enum": ["financial", "sales", "debtors", "inventory", "weekly"]},
            "period": {"type": "string", "enum": ["today", "week", "month"]},
        }, "required": ["report_type"]},
    }},

    # ─── هزینه‌ها ───
    {"type": "function", "function": {
        "name": "add_expense",
        "description": "ثبت هزینه",
        "parameters": {"type": "object", "properties": {
            "title": {"type": "string"},
            "amount": {"type": "number"},
            "category": {"type": "string"},
            "expense_type": {"type": "string", "enum": ["عملیاتی", "خرید", "بازاریابی", "متفرقه"]},
            "person": {"type": "string"},
            "payment_method": {"type": "string"},
            "expense_date": {"type": "string"},
            "note": {"type": "string"},
        }, "required": ["title", "amount"]},
    }},
    {"type": "function", "function": {
        "name": "delete_expense",
        "description": "حذف یک هزینه بر اساس عنوانش",
        "parameters": {"type": "object", "properties": {
            "title": {"type": "string", "description": "عنوان هزینه"},
        }, "required": ["title"]},
    }},

    # ─── کالا و انبار ───
    {"type": "function", "function": {
        "name": "add_product",
        "description": "ثبت کالای جدید",
        "parameters": {"type": "object", "properties": {
            "name": {"type": "string"},
            "category": {"type": "string"},
            "unit": {"type": "string"},
            "buy_price": {"type": "number"},
            "sell_price": {"type": "number"},
            "stock": {"type": "integer"},
            "min_stock": {"type": "integer"},
            "supplier": {"type": "string"},
            "barcode": {"type": "string"},
            "code": {"type": "string"},
        }, "required": ["name"]},
    }},
    {"type": "function", "function": {
        "name": "list_products",
        "description": "نمایش کالاها",
        "parameters": {"type": "object", "properties": {
            "filter": {"type": "string", "enum": ["all", "low_stock", "best_selling"]},
        }},
    }},
    {"type": "function", "function": {
        "name": "update_product",
        "description": "ویرایش یک کالا. مثال: «قیمت فروش مانیتور رو بکن ۷ میلیون»",
        "parameters": {"type": "object", "properties": {
            "name": {"type": "string", "description": "نام کالا برای پیدا کردن"},
            "new_name": {"type": "string"},
            "new_sell_price": {"type": "number"},
            "new_buy_price": {"type": "number"},
            "new_stock": {"type": "integer"},
            "new_min_stock": {"type": "integer"},
            "new_category": {"type": "string"},
        }, "required": ["name"]},
    }},
    {"type": "function", "function": {
        "name": "delete_product",
        "description": "حذف یک کالا",
        "parameters": {"type": "object", "properties": {
            "name": {"type": "string"},
        }, "required": ["name"]},
    }},

    # ─── کارمندان ───
    {"type": "function", "function": {
        "name": "add_employee",
        "description": "ثبت کارمند با تمام اطلاعات HR",
        "parameters": {"type": "object", "properties": {
            "name": {"type": "string"},
            "national_id": {"type": "string"},
            "phone": {"type": "string"},
            "birth_date": {"type": "string"},
            "marital_status": {"type": "string"},
            "children_count": {"type": "integer"},
            "city": {"type": "string"},
            "address": {"type": "string"},
            "role": {"type": "string"},
            "shift_type": {"type": "string"},
            "monthly_work_days": {"type": "integer"},
            "base_salary": {"type": "number"},
            "deductions": {"type": "number"},
            "bank_account": {"type": "string"},
            "leave_days": {"type": "integer"},
            "insurance_number": {"type": "string"},
            "insurance_amount": {"type": "number"},
            "insurance_start": {"type": "string"},
            "hire_date": {"type": "string"},
            "contract_end": {"type": "string", "description": "تاریخ پایان قرارداد"},
            "code": {"type": "string"},
        }, "required": ["name"]},
    }},
    {"type": "function", "function": {
        "name": "list_employees",
        "description": "نمایش کارمندان",
        "parameters": {"type": "object", "properties": {
            "filter": {"type": "string", "enum": ["all", "by_city"]},
            "city": {"type": "string"},
        }},
    }},
    {"type": "function", "function": {
        "name": "update_employee",
        "description": "ویرایش اطلاعات یک کارمند. مثال: «نقش امیرحسین رو بکن مدیر»، «حقوق رضا رو بکن ۱۵ میلیون»",
        "parameters": {"type": "object", "properties": {
            "name": {"type": "string", "description": "نام کارمند برای پیدا کردن"},
            "new_name": {"type": "string"},
            "new_role": {"type": "string"},
            "new_phone": {"type": "string"},
            "new_base_salary": {"type": "number"},
            "new_city": {"type": "string"},
            "new_national_id": {"type": "string"},
            "new_contract_end": {"type": "string"},
            "new_bank_account": {"type": "string"},
        }, "required": ["name"]},
    }},
    {"type": "function", "function": {
        "name": "delete_employee",
        "description": "حذف یک کارمند",
        "parameters": {"type": "object", "properties": {
            "name": {"type": "string"},
        }, "required": ["name"]},
    }},

    # ─── حقوق و گزارش کار ───
    {"type": "function", "function": {
        "name": "add_salary_payment",
        "description": "ثبت پرداخت حقوق",
        "parameters": {"type": "object", "properties": {
            "employee_name": {"type": "string"},
            "amount": {"type": "number"},
            "payment_date": {"type": "string"},
            "period": {"type": "string"},
            "payment_method": {"type": "string"},
            "note": {"type": "string"},
        }, "required": ["employee_name", "amount"]},
    }},
    {"type": "function", "function": {
        "name": "list_salary_payments",
        "description": "تاریخچه حقوق یک کارمند",
        "parameters": {"type": "object", "properties": {
            "employee_name": {"type": "string"},
        }, "required": ["employee_name"]},
    }},
    {"type": "function", "function": {
        "name": "export_work_log",
        "description": "اکسل گزارش کار",
        "parameters": {"type": "object", "properties": {
            "employee_name": {"type": "string"},
        }},
    }},
    {"type": "function", "function": {
        "name": "get_work_log_template",
        "description": "اکسل نمونه گزارش کار",
        "parameters": {"type": "object", "properties": {
            "employee_name": {"type": "string"},
        }},
    }},

    # ─── اکسل و گزارش‌ها ───
    {"type": "function", "function": {
        "name": "export_excel",
        "description": "اکسل اطلاعات. مثال: «اکسل مشتریا رو بده»",
        "parameters": {"type": "object", "properties": {
            "data_type": {"type": "string",
                          "enum": ["customers", "expenses", "products", "employees", "invoices", "tenant"],
                          "description": "tenant=اطلاعات کارفرما"},
        }, "required": ["data_type"]},
    }},
    {"type": "function", "function": {
        "name": "get_excel_template",
        "description": "اکسل نمونه (خالی) برای پر کردن",
        "parameters": {"type": "object", "properties": {
            "data_type": {"type": "string",
                          "enum": ["customers", "expenses", "products", "employees", "invoices"]},
        }, "required": ["data_type"]},
    }},
    {"type": "function", "function": {
        "name": "get_report",
        "description": "گزارش‌گیری سریع",
        "parameters": {"type": "object", "properties": {
            "report_type": {"type": "string",
                "enum": ["sales_today", "sales_month", "expenses_today", "expenses_month", "profit", "debts"]},
        }, "required": ["report_type"]},
    }},

    # ─── گزارش‌های پیشرفته ───
    {"type": "function", "function": {
        "name": "sales_report",
        "description": "گزارش فروش پیشرفته — دوره، پرفروش، مشتری برتر. مثال: «گزارش فروش این هفته»",
        "parameters": {"type": "object", "properties": {
            "period": {"type": "string", "enum": ["today", "week", "month", "all"]},
            "customer_name": {"type": "string"},
            "product_name": {"type": "string"},
        }},
    }},
    {"type": "function", "function": {
        "name": "financial_report",
        "description": "گزارش مالی — درآمد، هزینه، سود خالص. مثال: «سود این ماه چقدره؟»",
        "parameters": {"type": "object", "properties": {
            "period": {"type": "string", "enum": ["today", "week", "month"]},
        }},
    }},
    {"type": "function", "function": {
        "name": "debtors_report",
        "description": "لیست بدهکاران. مثال: «کیا بدهکارن؟»",
        "parameters": {"type": "object", "properties": {}},
    }},
    {"type": "function", "function": {
        "name": "inventory_report",
        "description": "گزارش انبار — ارزش کل، رو به اتمام. مثال: «وضعیت انبار»",
        "parameters": {"type": "object", "properties": {}},
    }},

    # ─── فیلتر و جستجوی ترکیبی ───
    {"type": "function", "function": {
        "name": "smart_search",
        "description": "جستجو و فیلتر پیشرفته. مثال: «مشتری‌های تهرانی بدهکار»، «کارمندایی که قراردادشون داره تموم می‌شه»",
        "parameters": {"type": "object", "properties": {
            "search_text": {"type": "string", "description": "متن جستجو"},
            "entity_type": {"type": "string", "enum": ["all", "customers", "employees", "products"]},
            "city": {"type": "string"},
            "min_amount": {"type": "number"},
            "max_amount": {"type": "number"},
            "near_birthday": {"type": "boolean", "description": "تولد طی ۳۰ روز آینده"},
            "near_contract_end": {"type": "boolean", "description": "قرارداد نزدیک اتمام"},
            "sort_by": {"type": "string", "enum": ["debt", "purchase", "name"]},
        }},
    }},

    # ─── سرچ اینترنتی ───
    {"type": "function", "function": {
        "name": "web_search_task",
        "description": "جستجوی اینترنتی (مثلاً شماره طلافروشی‌های تهران). باید اول سرعت بپرسی: فوری/متوسط/با حوصله.",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string", "description": "عبارت جستجو"},
            "priority": {"type": "string", "enum": ["instant", "medium", "nightly"],
                         "description": "فوری=2تا10دقیقه, متوسط=10تا40دقیقه, شبانه=بعد2شب"},
        }, "required": ["query", "priority"]},
    }},
    {"type": "function", "function": {
        "name": "get_search_result",
        "description": "نتیجه جستجوی اینترنتی قبلی",
        "parameters": {"type": "object", "properties": {
            "task_id": {"type": "integer"},
        }, "required": ["task_id"]},
    }},

    # ─── مدیریت کارفرما ───
    {"type": "function", "function": {
        "name": "update_tenant_info",
        "description": "آپدیت اطلاعات فروشگاه (نام، تلفن، آدرس، کارت، شبا). مثال: «شماره کارت فروشگاه 6037xxxx»",
        "parameters": {"type": "object", "properties": {
            "name": {"type": "string", "description": "نام فروشگاه"},
            "phone": {"type": "string"},
            "address": {"type": "string"},
            "city": {"type": "string"},
            "province": {"type": "string"},
            "card_number": {"type": "string", "description": "شماره کارت بانکی"},
            "sheba": {"type": "string", "description": "شماره شبا"},
            "account_holder": {"type": "string", "description": "نام صاحب حساب"},
            "default_tax_percent": {"type": "integer", "description": "درصد مالیات پیش‌فرض"},
        }},
    }},
    {"type": "function", "function": {
        "name": "get_tenant_info",
        "description": "نمایش اطلاعات فروشگاه. مثال: «اطلاعات فروشگاه»",
        "parameters": {"type": "object", "properties": {}},
    }},

    # ─── هشدارها ───
    {"type": "function", "function": {
        "name": "check_alerts",
        "description": "بررسی هشدارهای بحرانی (موجودی کم، بدهی بالا، قرارداد نزدیک اتمام)",
        "parameters": {"type": "object", "properties": {}},
    }},

    # ─── یادآور (ریمایندر) ───
    {"type": "function", "function": {
        "name": "add_reminder",
        "description": "ثبت یادآور با زمان مشخص. مثال: «فردا ساعت ۳ به فلانی زنگ بزنم» یا «یکشنبه قرار با تأمین‌کننده». اگر کاربر گفت چند دقیقه/ساعت قبلش خبر بده، notify_before_minutes رو پر کن.",
        "parameters": {"type": "object", "properties": {
            "title": {"type": "string", "description": "شرح کار"},
            "due_at": {"type": "string", "description": "زمان انجام کار به فرمت ISO وقت ایران، مثل 2026-05-26T15:00 . تاریخ شمسی کاربر رو خودت به میلادی تبدیل کن."},
            "notify_before_minutes": {"type": "integer", "description": "چند دقیقه قبل از موعد هشدار بده (مثلا ۳۰ برای نیم ساعت قبل). اگر کاربر نگفت، ۰ بذار."},
            "note": {"type": "string"},
        }, "required": ["title", "due_at"]},
    }},
    {"type": "function", "function": {
        "name": "list_reminders",
        "description": "لیست یادآورها. مثال: «کارهای امروزم»، «کارهای فردا»، «یادآورهام».",
        "parameters": {"type": "object", "properties": {
            "period": {"type": "string", "enum": ["today", "tomorrow", "week", "all"]},
        }},
    }},
    {"type": "function", "function": {
        "name": "complete_reminder",
        "description": "علامت زدن یادآور به‌عنوان انجام‌شده",
        "parameters": {"type": "object", "properties": {
            "reminder_display_id": {"type": "string", "description": "شناسه مثل REM-001"},
        }, "required": ["reminder_display_id"]},
    }},
    {"type": "function", "function": {
        "name": "delete_reminder",
        "description": "حذف یادآور",
        "parameters": {"type": "object", "properties": {
            "reminder_display_id": {"type": "string"},
        }, "required": ["reminder_display_id"]},
    }},

    # ─── عکس موجودیت‌ها ───
    {"type": "function", "function": {
        "name": "save_entity_photo",
        "description": "ذخیره عکسی که کاربر فرستاده برای یک مشتری/کالا/کارمند. وقتی کاربر عکس می‌فرستد و می‌گوید «این عکس فلان مشتری/کالا/کارمنده» این رو صدا بزن.",
        "parameters": {"type": "object", "properties": {
            "entity_type": {"type": "string", "enum": ["customer", "product", "employee"]},
            "entity_name": {"type": "string", "description": "نام مشتری/کالا/کارمند"},
        }, "required": ["entity_type", "entity_name"]},
    }},
    {"type": "function", "function": {
        "name": "get_entity_photo",
        "description": "ارسال عکس ذخیره‌شده‌ی یک مشتری/کالا/کارمند. مثال: «عکس کالای مانیتور رو نشونم بده»",
        "parameters": {"type": "object", "properties": {
            "entity_type": {"type": "string", "enum": ["customer", "product", "employee"]},
            "entity_name": {"type": "string"},
        }, "required": ["entity_type", "entity_name"]},
    }},

    # ─── اشخاص و نقش‌ها ───
    {"type": "function", "function": {
        "name": "add_person",
        "description": "ثبت یک شخص با نقش مشخص (کارمند/همکار/مشتری/پارتنر). بعد از ثبت باید لینک دعوت ساخت تا به تلگرام وصل بشه. مثال: «رضا رو به‌عنوان کارمند ثبت کن»",
        "parameters": {"type": "object", "properties": {
            "full_name": {"type": "string"},
            "role": {"type": "string", "enum": ["employee", "collaborator", "customer", "partner"],
                     "description": "employee=کارمند, collaborator=همکار, customer=مشتری, partner=پارتنر"},
            "phone": {"type": "string"},
            "note": {"type": "string"},
        }, "required": ["full_name", "role"]},
    }},
    {"type": "function", "function": {
        "name": "list_persons",
        "description": "لیست اشخاص ثبت‌شده و وضعیت اتصالشون. مثال: «کارمندام رو نشون بده»",
        "parameters": {"type": "object", "properties": {
            "role": {"type": "string", "enum": ["employee", "collaborator", "customer", "partner"]},
        }},
    }},

    {"type": "function", "function": {
        "name": "list_invite_links",
        "description": "نمایش لینک‌های دعوت فعال و وضعیتشون",
        "parameters": {"type": "object", "properties": {}},
    }},
    {"type": "function", "function": {
        "name": "revoke_invite_link",
        "description": "لغو یک لینک دعوت. مثال: «لینک LNK-3 رو لغو کن»",
        "parameters": {"type": "object", "properties": {
            "link_id": {"type": "string", "description": "شناسه لینک مثل LNK-3"},
        }, "required": ["link_id"]},
    }},

    # ─── سیستم ارتباطی ───
    {"type": "function", "function": {
        "name": "send_message_to_owner",
        "description": "ثبت و ارسال پیام/درخواست/گزارش کاربر (مشتری یا کارمند) برای کارفرما. هر وقت کاربر چیزی می‌خواد، شکایتی داره، سؤالی داره، یا گزارشی می‌ده، این رو صدا بزن. اگر کاربر گفت فوریه یا اورژانسیه، is_urgent رو true بذار.",
        "parameters": {"type": "object", "properties": {
            "message": {"type": "string", "description": "متن پیام/درخواست کاربر"},
            "is_urgent": {"type": "boolean", "description": "آیا فوری است؟"},
        }, "required": ["message"]},
    }},
    {"type": "function", "function": {
        "name": "view_messages",
        "description": "نمایش گفت‌وگوهای مشتری‌ها/کارمندها برای کارفرما. مثال: «مشتری‌ها چی گفتن؟»، «پیام‌های امروز کارمندا»",
        "parameters": {"type": "object", "properties": {
            "role_filter": {"type": "string", "enum": ["customer", "employee", "collaborator", "partner"]},
            "hours": {"type": "integer", "description": "فقط N ساعت اخیر"},
            "person_name": {"type": "string", "description": "فقط یک شخص خاص"},
        }},
    }},
    {"type": "function", "function": {
        "name": "set_report_schedule",
        "description": "تنظیم گزارش دوره‌ای خودکار گفت‌وگوها. مثال: «هر ۲ ساعت خلاصه بفرست» → interval_hours=2",
        "parameters": {"type": "object", "properties": {
            "interval_hours": {"type": "integer", "description": "فاصله به ساعت (۲ یعنی هر ۲ ساعت، ۴۸ یعنی هر ۲ روز)"},
        }, "required": ["interval_hours"]},
    }},
    {"type": "function", "function": {
        "name": "disable_report_schedule",
        "description": "خاموش کردن گزارش دوره‌ای",
        "parameters": {"type": "object", "properties": {}},
    }},
    {"type": "function", "function": {
        "name": "send_broadcast",
        "description": (
            "ارسال پیام/عکس/سوال به چند نفر همزمان با هدف مشخص. "
            "اگه عکسی آپلود شده همراه پیام ارسال میشه. "
            "مثال: این عکس رو برای همه کارمندا بفرست و بپرس خوبه؟ "
            "از همه بپرس فردا میان یا نه"
        ),
        "parameters": {"type": "object", "properties": {
            "message": {"type": "string"},
            "role_filter": {"type": "string",
                           "enum": ["employee", "customer", "collaborator", "partner"]},
            "person_names": {"type": "array", "items": {"type": "string"}},
            "expects_reply": {"type": "boolean"},
            "goal": {"type": "string", "description": "هدف نهایی مکالمه"},
            "next_step": {"type": "string", "description": "مرحله بعد اگه موافق بودن"},
        }, "required": ["message"]},
    }},
    {"type": "function", "function": {
        "name": "broadcast_status",
        "description": "وضعیت یک پیام گروهی و جواب‌هایی که اومده. مثال: «جواب‌های پیام گروهی چی شد؟»",
        "parameters": {"type": "object", "properties": {
            "broadcast_display_id": {"type": "string", "description": "شناسه مثل BRD-001 (خالی=آخرین)"},
        }},
    }},
    {"type": "function", "function": {
        "name": "send_direct_message",
        "description": "ارسال پیام به یک مشتری/کارمند خاص. مثال: «به علی محمدی بگو فاکتورش آماده‌ست»",
        "parameters": {"type": "object", "properties": {
            "person_name": {"type": "string"},
            "message": {"type": "string"},
        }, "required": ["person_name", "message"]},
    }},

    # ─── مدیریت پیشرفته پرسن‌ها ───
    {"type": "function", "function": {
        "name": "delete_person",
        "description": "حذف یک شخص از سیستم و قطع دسترسیش. مثال: «رضا رو از سیستم حذف کن»",
        "parameters": {"type": "object", "properties": {
            "display_id": {"type": "string", "description": "شناسه مثل PER-001 یا نام شخص"},
        }, "required": ["display_id"]},
    }},
    {"type": "function", "function": {
        "name": "create_followup",
        "description": "ایجاد پیگیری زمان‌بندی‌شده — هر N دقیقه/ساعت به یک پرسن پیام می‌فرستد تا فایل بفرستد یا کاری انجام دهد. مثال: «هر ۶۰ دقیقه به علی پیام بده که فایلش رو بفرسته»",
        "parameters": {"type": "object", "properties": {
            "person_display_id": {"type": "string", "description": "شناسه PER-001 یا نام شخص"},
            "message": {"type": "string", "description": "متن پیام پیگیری"},
            "interval_minutes": {"type": "integer", "description": "هر چند دقیقه پیام بفرستد"},
            "max_attempts": {"type": "integer", "description": "حداکثر چند بار (0 = نامحدود)"},
        }, "required": ["person_display_id", "message", "interval_minutes"]},
    }},
    {"type": "function", "function": {
        "name": "stop_followup",
        "description": "متوقف کردن پیگیری یک شخص. مثال: «پیگیری علی رو متوقف کن»",
        "parameters": {"type": "object", "properties": {
            "person_name": {"type": "string"},
        }, "required": ["person_name"]},
    }},
    {"type": "function", "function": {
        "name": "list_followups",
        "description": "لیست پیگیری‌های فعال",
        "parameters": {"type": "object", "properties": {}},
    }},
    {"type": "function", "function": {
        "name": "send_photo_to_person",
        "description": "ارسال عکسی که کارفرما فرستاده به یک پرسن مشخص. وقتی کارفرما عکسی می‌فرستد و می‌خواهد آن را برای یک نفر بفرستد.",
        "parameters": {"type": "object", "properties": {
            "person_name": {"type": "string", "description": "نام پرسن گیرنده"},
            "caption": {"type": "string", "description": "کپشن اختیاری برای عکس"},
        }, "required": ["person_name"]},
    }},

    # ─── اشتراک ───
    {"type": "function", "function": {
        "name": "request_trial",
        "description": "درخواست تست رایگان ۳ روزه — وقتی کارفرما جدید می‌خواهد شروع کند",
        "parameters": {"type": "object", "properties": {}},
    }},
    {"type": "function", "function": {
        "name": "get_subscription_status",
        "description": "وضعیت اشتراک کارفرما. مثال: «اشتراکم چه وضعیتی داره؟»",
        "parameters": {"type": "object", "properties": {}},
    }},
    {"type": "function", "function": {
        "name": "submit_payment_receipt",
        "description": "ثبت رسید پرداخت اشتراک — وقتی کارفرما عکس رسید را فرستاده",
        "parameters": {"type": "object", "properties": {}},
    }},

    # ─── فیش تصفیه حساب ───
    {"type": "function", "function": {
        "name": "generate_settlement",
        "description": (
            "صدور فیش تصفیه حساب PDF برای کارمند. "
            "حالت auto: از دیتابیس. amount: با مبلغ کل. manual: ورودی دستی. "
            "مثال: «فیش تصفیه مهدی طوافی برای آذر ۱۴۰۴» یا "
            "«فیش تصفیه برای علی با مبلغ ۵۰ میلیون»"
        ),
        "parameters": {"type": "object", "properties": {
            "employee_name": {"type": "string", "description": "نام کارمند"},
            "mode": {"type": "string", "enum": ["auto", "amount", "manual"],
                     "description": "auto=از دیتابیس، amount=با مبلغ کل، manual=دستی"},
            "year": {"type": "integer", "description": "سال شمسی (مثلاً ۱۴۰۴)"},
            "month_start": {"type": "integer", "description": "ماه شروع (۱ تا ۱۲)"},
            "day_start": {"type": "integer", "description": "روز شروع"},
            "month_end": {"type": "integer", "description": "ماه پایان"},
            "day_end": {"type": "integer", "description": "روز پایان"},
            "total_amount": {"type": "number", "description": "مبلغ کل (حالت amount)"},
            "work_hours": {"type": "number", "description": "ساعت کارکرد"},
            "work_days": {"type": "integer", "description": "تعداد روز کارکرد"},
            "overtime_hours": {"type": "number", "description": "ساعت اضافه‌کاری"},
            "night_hours": {"type": "number", "description": "ساعت شب‌کاری"},
            "holiday_days": {"type": "number", "description": "روز تعطیل‌کاری"},
            "friday_days": {"type": "number", "description": "روز جمعه‌کاری"},
            "leave_used": {"type": "number", "description": "مرخصی استفاده‌شده (روز)"},
            "unused_leave": {"type": "number", "description": "مرخصی استفاده‌نشده (روز)"},
            "shift_type": {"type": "string", "description": "نوبت‌کاری: صبح-عصر-شب/روز-شب/صبح-عصر"},
            "repair_wage": {"type": "number", "description": "مزد ترمیمی"},
            "loan_deduction": {"type": "number", "description": "مکسوره وام"},
            "marital_status": {"type": "string", "description": "متاهل/مجرد"},
            "children_status": {"type": "string", "description": "فاقد فرزند/یک فرزند/دو فرزند/سه فرزند"},
            "work_type": {"type": "string", "description": "تمام وقت/نیمه وقت"},
        }, "required": ["employee_name"]},
    }},

    # ─── اطلاعات کامل کارمند ───
    {"type": "function", "function": {
        "name": "get_employee_detail",
        "description": "اطلاعات کامل یک کارمند شامل شماره حساب، بیمه، آدرس، کد ملی و همه فیلدها",
        "parameters": {"type": "object", "properties": {
            "name": {"type": "string", "description": "نام کارمند (جزئی هم قبوله)"},
        }, "required": ["name"]},
    }},

    # ─── جستجو و مرتب‌سازی کارمندان ───
    {"type": "function", "function": {
        "name": "search_employees",
        "description": "جستجو و مرتب‌سازی کارمندان. مثال: بر اساس حقوق از بیشترین تا کمترین",
        "parameters": {"type": "object", "properties": {
            "sort_by": {"type": "string", "enum": ["name", "salary", "hire_date", "city"],
                        "description": "مرتب‌سازی بر اساس"},
            "order": {"type": "string", "enum": ["asc", "desc"], "description": "صعودی یا نزولی"},
            "filter_field": {"type": "string", "enum": ["city", "role", "marital_status", "work_mode", "contract_type", "shift_type"]},
            "filter_value": {"type": "string"},
            "limit": {"type": "integer", "description": "تعداد نتایج"},
        }},
    }},

    # ─── آمار کارمندان ───
    {"type": "function", "function": {
        "name": "employee_statistics",
        "description": "آمار کلی کارمندان: تعداد، میانگین حقوق، بیشترین/کمترین، تعداد متاهل و...",
        "parameters": {"type": "object", "properties": {}},
    }},

    # ─── اطلاعات کامل مشتری ───
    {"type": "function", "function": {
        "name": "get_customer_detail",
        "description": "اطلاعات کامل یک مشتری شامل تلفن، آدرس، مانده حساب و همه فیلدها",
        "parameters": {"type": "object", "properties": {
            "name": {"type": "string", "description": "نام مشتری (جزئی هم قبوله)"},
        }, "required": ["name"]},
    }},

    # ─── جستجو و مرتب‌سازی مشتریان ───
    {"type": "function", "function": {
        "name": "search_customers",
        "description": "جستجو و مرتب‌سازی مشتریان. مثال: بر اساس خرید از بیشترین، یا بدهکارها",
        "parameters": {"type": "object", "properties": {
            "sort_by": {"type": "string", "enum": ["name", "balance", "total_purchase", "city"]},
            "order": {"type": "string", "enum": ["asc", "desc"]},
            "filter_field": {"type": "string", "enum": ["city", "province", "name"]},
            "filter_value": {"type": "string"},
            "limit": {"type": "integer"},
        }},
    }},

    # ─── آمار مشتریان ───
    {"type": "function", "function": {
        "name": "customer_statistics",
        "description": "آمار کلی مشتریان: تعداد، بدهکاران، کل خرید و...",
        "parameters": {"type": "object", "properties": {}},
    }},

    # ─── رتبه‌بندی مشتریان ───
    {"type": "function", "function": {
        "name": "top_customers",
        "description": "رتبه‌بندی مشتریان: پرخریدترین یا بیشترین بدهکار",
        "parameters": {"type": "object", "properties": {
            "by": {"type": "string", "enum": ["purchase", "debt"], "description": "بر اساس خرید یا بدهی"},
            "limit": {"type": "integer", "description": "تعداد نتایج"},
        }},
    }},

    # ─── جواب صوتی (TTS) ───
    {"type": "function", "function": {
        "name": "voice_reply",
        "description": "جواب صوتی — وقتی کاربر میگه با صدا جواب بده، ویس بده، صوتی بگو",
        "parameters": {"type": "object", "properties": {
            "text": {"type": "string", "description": "متنی که باید به صدا تبدیل بشه"},
            "prefer_ai": {"type": "boolean", "description": "true=صدای AI طبیعی، false=TTS معمولی"},
        }, "required": ["text"]},
    }},

    # ─── خروجی دسته‌جمعی ───
    {"type": "function", "function": {
        "name": "batch_export",
        "description": (
            "خروجی دسته‌جمعی PDF/Excel/فیش. "
            "مثال: فیش تصفیه همه کارمندان آذر ماه، فاکتورهای این ماه. "
            "خروجی تکی یا zip"
        ),
        "parameters": {"type": "object", "properties": {
            "export_type": {"type": "string", "enum": ["settlement", "invoice_pdf", "invoice_excel", "employee_excel", "customer_excel"]},
            "output_format": {"type": "string", "enum": ["zip", "separate"], "description": "zip=یه فایل فشرده، separate=تک‌تک"},
            "year": {"type": "integer"},
            "month_start": {"type": "integer"},
            "month_end": {"type": "integer"},
            "employee_names": {"type": "array", "items": {"type": "string"}, "description": "لیست نام کارمندان (خالی=همه)"},
        }, "required": ["export_type"]},
    }},

    # ─── بکاپ ───
    {"type": "function", "function": {
        "name": "backup_data",
        "description": "بکاپ کامل اطلاعات — فایل zip حاوی JSON و Excel همه داده‌ها. مثال: بکاپ بگیر، اطلاعاتم رو بکاپ بده",
        "parameters": {"type": "object", "properties": {
            "full_system": {"type": "boolean", "description": "true=بکاپ کل سیستم (فقط ادمین)، false=بکاپ این کسب‌وکار"},
        }},
    }},

    # ─── برند ───
    {"type": "function", "function": {
        "name": "save_brand_config",
        "description": "ذخیره تنظیمات برند: رنگ، شعار، لحن. مثال: رنگ برندمون آبیه #2B5F9E",
        "parameters": {"type": "object", "properties": {
            "primary_color": {"type": "string", "description": "رنگ اصلی (هگز)"},
            "secondary_color": {"type": "string", "description": "رنگ ثانویه"},
            "slogan": {"type": "string", "description": "شعار برند"},
            "tone": {"type": "string", "enum": ["formal", "friendly", "neutral"]},
            "auto_send_approval": {"type": "boolean", "description": "قبل ارسال تأیید بگیره؟"},
        }},
    }},

    {"type": "function", "function": {
        "name": "get_brand_config",
        "description": "دریافت تنظیمات برند فعلی",
        "parameters": {"type": "object", "properties": {}},
    }},

    # ─── اقساط ───
    {"type": "function", "function": {
        "name": "add_installment",
        "description": "ثبت قسط جدید برای فاکتور. مثال: قسط اول فاکتور INV-0001 مبلغ ۵ میلیون سررسید ۱۴۰۴/۱۰/۱۵",
        "parameters": {"type": "object", "properties": {
            "invoice_display_id": {"type": "string"},
            "amount": {"type": "number", "description": "مبلغ قسط (ریال)"},
            "due_date": {"type": "string", "description": "تاریخ سررسید شمسی"},
            "installment_number": {"type": "integer"},
        }, "required": ["invoice_display_id", "amount", "due_date"]},
    }},
    {"type": "function", "function": {
        "name": "list_installments",
        "description": "لیست اقساط — همه یا یک فاکتور خاص",
        "parameters": {"type": "object", "properties": {
            "invoice_display_id": {"type": "string"},
        }},
    }},
    {"type": "function", "function": {
        "name": "pay_installment",
        "description": "پرداخت قسط. مثال: قسط ۲ فاکتور INV-0001 پرداخت شد",
        "parameters": {"type": "object", "properties": {
            "invoice_display_id": {"type": "string"},
            "installment_number": {"type": "integer"},
        }, "required": ["invoice_display_id", "installment_number"]},
    }},
    {"type": "function", "function": {
        "name": "overdue_installments",
        "description": "اقساط سررسید گذشته",
        "parameters": {"type": "object", "properties": {}},
    }},

    # ─── تاریخچه خرید مشتری ───
    {"type": "function", "function": {
        "name": "customer_purchase_history",
        "description": "تاریخچه خرید کامل یک مشتری با جزئیات فاکتورها و اقلام",
        "parameters": {"type": "object", "properties": {
            "name": {"type": "string", "description": "نام مشتری"},
            "limit": {"type": "integer"},
        }, "required": ["name"]},
    }},

    # ─── طراحی پوستر ───
    {"type": "function", "function": {
        "name": "generate_poster",
        "description": "طراحی پوستر تبلیغاتی با هوش مصنوعی. سایز: story/post/landscape/a4/a5. مثال: پوستر تبلیغاتی محصول ۱ برای استوری",
        "parameters": {"type": "object", "properties": {
            "title": {"type": "string", "description": "تیتر پوستر"},
            "subtitle": {"type": "string"},
            "size_preset": {"type": "string", "enum": ["story", "post", "landscape", "a4", "a5"]},
            "creativity": {"type": "integer", "description": "درصد خلاقیت (۰ تا ۱۰۰)"},
            "bg_prompt": {"type": "string", "description": "پرامپت سفارشی برای پس‌زمینه (انگلیسی)"},
            "product_id": {"type": "integer", "description": "آیدی محصول برای عکسش"},
        }, "required": ["title"]},
    }},

    # ─── پست اسلایدی ───
    {"type": "function", "function": {
        "name": "generate_slide_post",
        "description": "پست اسلایدی زنجیره‌ای — چند اسلاید مرتبط",
        "parameters": {"type": "object", "properties": {
            "slides": {"type": "array", "items": {"type": "object", "properties": {
                "title": {"type": "string"}, "subtitle": {"type": "string"},
            }}, "description": "لیست اسلایدها"},
            "size": {"type": "string", "enum": ["story", "post", "landscape"]},
            "creativity": {"type": "integer"},
        }, "required": ["slides"]},
    }},

    # ─── کاتالوگ ───
    {"type": "function", "function": {
        "name": "generate_catalog",
        "description": "کاتالوگ PDF چندصفحه‌ای از محصولات",
        "parameters": {"type": "object", "properties": {
            "title": {"type": "string"},
            "product_ids": {"type": "array", "items": {"type": "integer"}, "description": "آیدی محصولات (خالی=همه)"},
        }},
    }},

    # ─── برش عکس ───
    {"type": "function", "function": {
        "name": "crop_image",
        "description": "برش عکس به تکه‌های مساوی. مثال: این عکس رو ۵ تکه افقی کن",
        "parameters": {"type": "object", "properties": {
            "rows": {"type": "integer", "description": "تعداد سطر"},
            "cols": {"type": "integer", "description": "تعداد ستون"},
        }},
    }},

    # ─── تمپلیت طراحی ───
    {"type": "function", "function": {
        "name": "save_design_template",
        "description": "ذخیره تمپلیت طراحی برای استفاده مجدد و دسته‌جمعی",
        "parameters": {"type": "object", "properties": {
            "name": {"type": "string", "description": "نام تمپلیت"},
            "size_preset": {"type": "string", "enum": ["story", "post", "landscape", "a4"]},
            "bg_prompt": {"type": "string"},
            "creativity": {"type": "integer"},
            "fixed_elements": {"type": "string", "description": "المان‌هایی که ثابت بمونن"},
            "free_elements": {"type": "string", "description": "المان‌هایی که آزاد باشن"},
        }, "required": ["name"]},
    }},

    # ─── طراحی دسته‌جمعی از تمپلیت ───
    {"type": "function", "function": {
        "name": "batch_design",
        "description": "طراحی دسته‌جمعی از روی تمپلیت. مثال: با تمپلیت X برای ۱۰ محصول پرفروش پوستر بساز",
        "parameters": {"type": "object", "properties": {
            "template_name": {"type": "string"},
            "items": {"type": "array", "items": {"type": "object", "properties": {
                "title": {"type": "string"}, "subtitle": {"type": "string"},
                "product_id": {"type": "integer"},
            }}},
        }, "required": ["template_name", "items"]},
    }},

    # ─── لینک دعوت کارمند ───
    {"type": "function", "function": {
        "name": "create_employee_invite_link",
        "description": "ساخت لینک دعوت رمزدار برای کارمند. برای هر لینک کارمند فقط از این tool استفاده کن. کارمند باید قبلاً با کد ملی و شماره تماس ثبت شده باشه.",
        "parameters": {"type": "object", "properties": {
            "person_name": {"type": "string", "description": "نام کارمند"},
            "link_type": {"type": "string", "enum": ["self", "prefilled"],
                          "description": "self=کارمند اطلاعاتش رو خودش پر می‌کنه، prefilled=کارفرما پر کرده"},
            "expires_hours": {"type": "integer", "description": "ساعت انقضا (پیش‌فرض ۱۶۸=۷روز)"},
        }, "required": ["person_name", "link_type"]},
    }},

    # ─── لینک دعوت مشتری ───
    {"type": "function", "function": {
        "name": "create_customer_invite_link",
        "description": "ساخت لینک مشتری. دو نوع: آشنا (قبلاً باهاش کار کردیم) یا ناآشنا (جدیده)",
        "parameters": {"type": "object", "properties": {
            "acquaintance_type": {"type": "string", "enum": ["known", "new"]},
            "person_name": {"type": "string", "description": "نام مشتری (برای لینک آشنا)"},
            "person_phone": {"type": "string"},
            "max_uses": {"type": "integer", "description": "لیمیت تعداد (خالی=نامحدود)"},
            "expires_hours": {"type": "integer"},
        }, "required": ["acquaintance_type"]},
    }},

    # ─── لینک دعوت همکار ───
    {"type": "function", "function": {
        "name": "create_collaborator_invite_link",
        "description": "ساخت لینک همکار. دو نوع: آشنا یا ناآشنا",
        "parameters": {"type": "object", "properties": {
            "acquaintance_type": {"type": "string", "enum": ["known", "new"]},
            "person_name": {"type": "string"},
            "max_uses": {"type": "integer"},
            "expires_hours": {"type": "integer"},
        }, "required": ["acquaintance_type"]},
    }},

    # ─── لیست لینک‌ها ───
    {"type": "function", "function": {
        "name": "list_invite_links",
        "description": "لیست لینک‌های دعوت فعال",
        "parameters": {"type": "object", "properties": {}},
    }},

    # ─── لغو لینک ───
    {"type": "function", "function": {
        "name": "revoke_invite_link",
        "description": "لغو یک لینک دعوت. مثال: لینک LNK-3 رو حذف کن",
        "parameters": {"type": "object", "properties": {
            "link_id": {"type": "string", "description": "شناسه لینک مثل LNK-3"},
        }, "required": ["link_id"]},
    }},

    # ─── لغو همه لینک‌ها ───
    {"type": "function", "function": {
        "name": "revoke_all_invite_links",
        "description": "لغو همه لینک‌های دعوت",
        "parameters": {"type": "object", "properties": {}},
    }},
]

# اضافه کردن tools که از قلم افتاد
TOOLS += [
    {"type": "function", "function": {
        "name": "create_project",
        "description": "ساخت پروژه جدید",
        "parameters": {"type": "object", "properties": {
            "name": {"type": "string"}, "description": {"type": "string"},
        }, "required": ["name"]},
    }},
    {"type": "function", "function": {
        "name": "get_project_info",
        "description": "اطلاعات و مستندات پروژه",
        "parameters": {"type": "object", "properties": {
            "name": {"type": "string"},
        }, "required": ["name"]},
    }},
    {"type": "function", "function": {
        "name": "add_project_document",
        "description": "اضافه کردن مستند به پروژه",
        "parameters": {"type": "object", "properties": {
            "name": {"type": "string"}, "document_text": {"type": "string"},
        }, "required": ["name", "document_text"]},
    }},
    {"type": "function", "function": {
        "name": "list_projects",
        "description": "لیست پروژه‌ها",
        "parameters": {"type": "object", "properties": {}},
    }},
]

# فاز B — فلو، دسترسی، تسک، گزارش
TOOLS += [
    # ─── فلو ───
    {"type": "function", "function": {
        "name": "create_workflow",
        "description": (
            "ایجاد فلو کاری خودکار. "
            "مثال: اگه کارمند جواب نداد به رضا بگو تماس بگیره | "
            "هر بار که فاکتور تأیید شد برای گرافیست بفرست | "
            "وقتی طراحی آماده شد برام بفرست"
        ),
        "parameters": {"type": "object", "properties": {
            "name": {"type": "string"},
            "trigger_type": {"type": "string",
                            "enum": ["no_response", "deadline", "condition", "schedule", "event"],
                            "description": "event=وقتی رویداد خاصی اتفاق افتاد"},
            "event_type": {"type": "string",
                          "description": "نوع رویداد: invoice_confirmed / task_completed / payment_received",
                          "enum": ["invoice_confirmed", "task_completed", "payment_received", ""]},
            "trigger_description": {"type": "string"},
            "steps": {"type": "array", "items": {"type": "object",
                "properties": {
                    "action": {"type": "string",
                               "enum": ["send_message", "send_file", "notify_owner"],
                               "description": "send_file=ارسال فایل، send_message=ارسال پیام"},
                    "target_role": {"type": "string", "description": "نقش گیرنده: employee/customer/..."},
                    "message": {"type": "string"},
                    "file_type": {"type": "string",
                                  "description": "invoice=فاکتور، last_generated=آخرین فایل ساخته‌شده"},
                    "delay_minutes": {"type": "integer"},
                }}},
            "target_role": {"type": "string"},
            "max_retries": {"type": "integer", "default": 3},
        }, "required": ["name", "trigger_type", "steps"]},
    }},
    {"type": "function", "function": {
        "name": "list_workflows",
        "description": "لیست فلوهای کاری",
        "parameters": {"type": "object", "properties": {}},
    }},
    {"type": "function", "function": {
        "name": "delete_workflow",
        "description": "حذف فلو",
        "parameters": {"type": "object", "properties": {
            "flow_id": {"type": "integer"},
        }, "required": ["flow_id"]},
    }},
    {"type": "function", "function": {
        "name": "export_workflows_excel",
        "description": "خروجی اکسل فلوها",
        "parameters": {"type": "object", "properties": {}},
    }},

    # ─── دسترسی ───
    {"type": "function", "function": {
        "name": "grant_permission",
        "description": "دادن دسترسی. مثال: علی بتونه فاکتورهای بالای ۱۰ میلیون ببینه",
        "parameters": {"type": "object", "properties": {
            "name": {"type": "string"},
            "level": {"type": "integer", "minimum": 1, "maximum": 5},
            "grantee_type": {"type": "string", "enum": ["person", "role", "all"]},
            "resource_type": {"type": "string"},
            "grantee_role": {"type": "string"},
            "max_uses": {"type": "integer"},
            "expires_hours": {"type": "integer"},
            "condition": {"type": "string"},
        }, "required": ["name", "level", "grantee_type", "resource_type"]},
    }},
    {"type": "function", "function": {
        "name": "list_permissions",
        "description": "لیست دسترسی‌های تعریف‌شده",
        "parameters": {"type": "object", "properties": {}},
    }},
    {"type": "function", "function": {
        "name": "revoke_permission",
        "description": "لغو دسترسی",
        "parameters": {"type": "object", "properties": {
            "perm_id": {"type": "integer"},
        }, "required": ["perm_id"]},
    }},
    {"type": "function", "function": {
        "name": "export_permissions_excel",
        "description": "خروجی اکسل دسترسی‌ها (محرمانه)",
        "parameters": {"type": "object", "properties": {}},
    }},

    # ─── تسک ───
    {"type": "function", "function": {
        "name": "add_task",
        "description": "اضافه کردن تسک به پروژه",
        "parameters": {"type": "object", "properties": {
            "project_name": {"type": "string"},
            "title": {"type": "string"},
            "description": {"type": "string"},
            "task_type": {"type": "string",
                         "description": "نوع: گرافیک/فروش/جلسه/کدنویسی/تحقیق/تماس/گزارش"},
            "priority": {"type": "string", "enum": ["urgent", "high", "normal", "low"]},
            "estimated_hours": {"type": "number"},
            "deadline_str": {"type": "string"},
            "require_photo_report": {"type": "boolean"},
            "follow_up_hours": {"type": "integer"},
        }, "required": ["project_name", "title"]},
    }},
    {"type": "function", "function": {
        "name": "move_task",
        "description": "جابجایی تسک بین لیست‌ها",
        "parameters": {"type": "object", "properties": {
            "task_id": {"type": "integer"},
            "new_list": {"type": "string",
                        "enum": ["backlog", "this_week", "next", "doing", "review", "approved"]},
        }, "required": ["task_id", "new_list"]},
    }},
    {"type": "function", "function": {
        "name": "list_tasks",
        "description": "لیست تسک‌ها",
        "parameters": {"type": "object", "properties": {
            "project_name": {"type": "string"},
            "list_type": {"type": "string",
                         "enum": ["backlog", "this_week", "next", "doing", "review", "approved"]},
        }},
    }},
    {"type": "function", "function": {
        "name": "project_report",
        "description": "گزارش لحظه‌ای همه پروژه‌ها",
        "parameters": {"type": "object", "properties": {}},
    }},

    # ─── گزارش روزانه ───
    {"type": "function", "function": {
        "name": "end_of_day_report",
        "description": "گزارش پایان روز همه کارمندان با درصد بهره‌وری",
        "parameters": {"type": "object", "properties": {}},
    }},
]

# فاز C+D+F+G
TOOLS += [
    # ─── داشبورد مالی ───
    {"type": "function", "function": {
        "name": "monthly_profit_loss",
        "description": "سود و زیان ماهانه. مثال: گزارش مالی این ماه، سود/زیان آذر ماه",
        "parameters": {"type": "object", "properties": {
            "year": {"type": "integer"}, "month": {"type": "integer"},
        }},
    }},
    {"type": "function", "function": {
        "name": "cashflow_report",
        "description": "جریان نقدی چند ماه اخیر",
        "parameters": {"type": "object", "properties": {
            "months": {"type": "integer", "description": "تعداد ماه (پیش‌فرض ۳)"},
        }},
    }},
    {"type": "function", "function": {
        "name": "monthly_comparison",
        "description": "مقایسه این ماه با ماه قبل",
        "parameters": {"type": "object", "properties": {}},
    }},
    {"type": "function", "function": {
        "name": "top_selling_products",
        "description": "پرفروش‌ترین محصولات",
        "parameters": {"type": "object", "properties": {
            "limit": {"type": "integer"},
        }},
    }},
    {"type": "function", "function": {
        "name": "financial_summary",
        "description": "خلاصه مالی کامل — سود/زیان + مقایسه",
        "parameters": {"type": "object", "properties": {}},
    }},

    # ─── اطلاعیه مدیریت ───
    {"type": "function", "function": {
        "name": "send_announcement",
        "description": "ارسال اطلاعیه مدیریت به کارمندان، مشتریان یا همه. مثال: به همه کارمندان بگو فردا جلسه داریم",
        "parameters": {"type": "object", "properties": {
            "message": {"type": "string"},
            "target_role": {"type": "string",
                           "enum": ["employee", "customer", "collaborator", "partner"],
                           "description": "خالی=همه"},
            "is_official": {"type": "boolean", "description": "True=هدر رسمی داشته باشه"},
        }, "required": ["message"]},
    }},
    {"type": "function", "function": {
        "name": "create_poll",
        "description": "نظرسنجی. مثال: از کارمندان بپرس جلسه کِی باشه",
        "parameters": {"type": "object", "properties": {
            "question": {"type": "string"},
            "options": {"type": "array", "items": {"type": "string"}},
            "target_role": {"type": "string"},
            "is_anonymous": {"type": "boolean"},
        }, "required": ["question", "options"]},
    }},
    {"type": "function", "function": {
        "name": "send_checklist",
        "description": "ارسال چک‌لیست به کارمندان",
        "parameters": {"type": "object", "properties": {
            "title": {"type": "string"},
            "items": {"type": "array", "items": {"type": "string"}},
            "target_role": {"type": "string"},
        }, "required": ["title", "items"]},
    }},
]

# تغییر جنس صدا
TOOLS += [
    {"type": "function", "function": {
        "name": "set_voice",
        "description": "تغییر صدای ربات یا نمایش صداهای موجود. مثال: «صداهای موجود رو نشون بده» یا «صدا رو به nova تغییر بده»",
        "parameters": {"type": "object", "properties": {
            "voice_key": {"type": "string",
                         "enum": ["alloy", "echo", "fable", "onyx", "nova", "shimmer", "list"],
                         "description": "نام صدا یا list برای نمایش همه صداها"},
        }, "required": ["voice_key"]},
    }},
]

TOOLS += [
    {"type": "function", "function": {
        "name": "send_file_to_person",
        "description": (
            "ارسال هر نوع فایل (PDF، اکسل، عکس، فاکتور، گزارش، ...) به یک شخص. "
            "مثال: فاکتور رو برای گرافیست بفرست | این PDF رو به علی بفرست | "
            "خروجی طراحی رو برام بفرست | آخرین فایل رو به سارا بفرست"
        ),
        "parameters": {"type": "object", "properties": {
            "person_name": {"type": "string", "description": "نام گیرنده"},
            "file_type": {"type": "string",
                         "enum": ["invoice", "pdf", "excel", "last_generated", "uploaded", "any"],
                         "description": "نوع فایل — any=هر فایلی که موجوده"},
            "caption": {"type": "string", "description": "پیام همراه فایل"},
        }, "required": ["person_name"]},
    }},
]

# قطع اتصال، حذف اکانت
TOOLS += [
    {"type": "function", "function": {
        "name": "disconnect_person",
        "description": "قطع اتصال کارمند از ربات — کارمند می‌مونه ولی دسترسی نداره. برای اتصال مجدد لینک جدید لازمه.",
        "parameters": {"type": "object", "properties": {
            "name": {"type": "string", "description": "نام کارمند"},
        }, "required": ["name"]},
    }},
    {"type": "function", "function": {
        "name": "request_account_deletion",
        "description": "حذف کامل اکانت کارفرما — بکاپ می‌گیره و حذف می‌کنه",
        "parameters": {"type": "object", "properties": {
            "confirmed": {"type": "boolean", "description": "کارفرما تأیید کرده؟"},
        }, "required": ["confirmed"]},
    }},
]

TOOLS += [
    {"type": "function", "function": {
        "name": "request_disconnect",
        "description": "کارمند می‌خواد از سیستم قطع بشه — نیاز به تأیید کارفرما داره",
        "parameters": {"type": "object", "properties": {
            "reason": {"type": "string", "description": "دلیل قطع اتصال (اختیاری)"},
        }},
    }},
]

TOOLS += [
    {"type": "function", "function": {
        "name": "search_memory",
        "description": "جستجو در تاریخچه مکالمات. مثال: «رضایی چی گفت؟» «هفته پیش چی صحبت کردیم؟»",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string", "description": "کلمه کلیدی جستجو"},
            "person_name": {"type": "string", "description": "نام شخص (اختیاری)"},
        }, "required": ["query"]},
    }},
    {"type": "function", "function": {
        "name": "get_thread_summary",
        "description": "خلاصه وضعیت یه موضوع از همه نقش‌ها. مثال: «رضایی چی شد؟» «وضعیت پروژه X؟»",
        "parameters": {"type": "object", "properties": {
            "topic": {"type": "string", "description": "موضوع مورد نظر"},
        }, "required": ["topic"]},
    }},
    {"type": "function", "function": {
        "name": "search_files",
        "description": "جستجوی فایل‌های ارسال‌شده. مثال: «PDF که علی فرستاد» «آخرین عکس»",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string"},
            "sender_name": {"type": "string"},
            "file_type": {"type": "string", "enum": ["photo", "document", "voice", "video", "any"]},
        }},
    }},
    {"type": "function", "function": {
        "name": "resend_file",
        "description": "ارسال مجدد فایل قبلی. مثال: «همون PDF که فرستادم رو دوباره برای رضا بفرست»",
        "parameters": {"type": "object", "properties": {
            "file_record_id": {"type": "integer", "description": "شناسه فایل از search_files"},
            "receiver_name": {"type": "string", "description": "نام گیرنده"},
            "caption": {"type": "string"},
        }, "required": ["file_record_id", "receiver_name"]},
    }},
]

TOOLS += [
    {"type": "function", "function": {
        "name": "schedule_meetings",
        "description": (
            "ست کردن جلسه با چند نفر — همزمان همه رو می‌پرسه و نتیجه رو گزارش میده. "
            "مثال: «با هر کارمند فردا جلسه خصوصی ست کن، من ۱۲ تا ۱۶ آزادم»"
        ),
        "parameters": {"type": "object", "properties": {
            "owner_free_slots": {"type": "string",
                                  "description": "ساعات آزاد کارفرما — مثل «۱۲ تا ۱۶»"},
            "role_filter": {"type": "string",
                           "enum": ["employee", "customer", "collaborator"],
                           "description": "با کدوم نقش جلسه؟"},
            "meeting_date": {"type": "string", "description": "تاریخ جلسه — مثل «فردا»"},
            "meeting_topic": {"type": "string", "description": "موضوع جلسه"},
        }, "required": ["owner_free_slots", "role_filter"]},
    }},
]

TOOLS += [
    {"type": "function", "function": {
        "name": "create_approval_goal",
        "description": "گرفتن تأیید از شخص + اقدام بعدی بر اساس جواب. مثال: از علی بپرس موافقه، اگه آره بود به من خبر بده",
        "parameters": {"type": "object", "properties": {
            "target_name": {"type": "string"},
            "question": {"type": "string"},
            "description": {"type": "string"},
            "action_if_positive": {"type": "string",
                                   "enum": ["notify_owner", "ask_followup", "escalate"],
                                   "description": "اگه موافق بود چیکار کنم"},
            "message_if_positive": {"type": "string"},
            "action_if_negative": {"type": "string",
                                   "enum": ["notify_owner", "ask_followup", "escalate"]},
            "message_if_negative": {"type": "string"},
        }, "required": ["target_name", "question", "description"]},
    }},
    {"type": "function", "function": {
        "name": "create_collection_goal",
        "description": "جمع‌آوری اطلاعات از چند نفر. مثال: از همه کارمندا شماره حساب بگیر",
        "parameters": {"type": "object", "properties": {
            "question": {"type": "string", "description": "سوال — {name} جایگزین اسم میشه"},
            "role_filter": {"type": "string", "enum": ["employee", "customer", "collaborator"]},
            "description": {"type": "string"},
        }, "required": ["question", "role_filter", "description"]},
    }},
    {"type": "function", "function": {
        "name": "request_permission_for_person",
        "description": "درخواست دسترسی برای یه کارمند — اولین بار به کارفرما پیشنهاد میشه",
        "parameters": {"type": "object", "properties": {
            "person_name": {"type": "string"},
            "resource_type": {"type": "string",
                              "enum": ["invoice", "employee", "report", "file", "customer", "product"]},
            "action": {"type": "string", "enum": ["read", "write", "delete"]},
            "suggested_approval_type": {"type": "string",
                                         "enum": ["once", "always", "until_date"],
                                         "description": "نوع تأیید پیشنهادی"},
        }, "required": ["person_name", "resource_type", "action"]},
    }},
    {"type": "function", "function": {
        "name": "approve_permission_request",
        "description": "تأیید درخواست دسترسی توسط کارفرما",
        "parameters": {"type": "object", "properties": {
            "request_id": {"type": "integer"},
            "approval_type": {"type": "string",
                              "enum": ["once", "always", "until_date", "count"]},
            "expires_days": {"type": "integer", "description": "اگه زمان‌دار باشه، چند روز"},
            "count": {"type": "integer", "description": "اگه تعدادی باشه، چند بار"},
        }, "required": ["request_id", "approval_type"]},
    }},
]

# ─── Employee Relay کامل ───
TOOLS += [
    {"type": "function", "function": {
        "name": "relay_message_to_employee",
        "description": "ارسال پیام از کارمند A به کارمند B از طریق AI. مثال: به رضا بگو قیمت محصول X چنده",
        "parameters": {"type": "object", "properties": {
            "from_name": {"type": "string"},
            "to_name": {"type": "string"},
            "message": {"type": "string"},
            "expect_reply": {"type": "boolean", "default": True},
        }, "required": ["to_name", "message"]},
    }},
    {"type": "function", "function": {
        "name": "transfer_file_to_employee",
        "description": "ارسال فایل از یه کارمند به کارمند دیگه با چک دسترسی",
        "parameters": {"type": "object", "properties": {
            "to_name": {"type": "string"},
            "caption": {"type": "string"},
            "file_type": {"type": "string", "enum": ["photo", "document", "any"]},
        }, "required": ["to_name"]},
    }},
    {"type": "function", "function": {
        "name": "apply_penalty_flow",
        "description": "اعمال جریمه کارمند بر اساس تخلف. مثال: ۳ بار ددلاین رد کرد",
        "parameters": {"type": "object", "properties": {
            "employee_name": {"type": "string"},
            "violation_type": {"type": "string",
                               "enum": ["deadline_miss", "absence", "late", "quality"],
                               "description": "نوع تخلف"},
            "violation_count": {"type": "integer"},
            "penalty_percent": {"type": "number", "description": "درصد جریمه از حقوق"},
            "fire_after_count": {"type": "integer", "description": "بعد از چند بار اخراج"},
        }, "required": ["employee_name", "violation_type"]},
    }},
    {"type": "function", "function": {
        "name": "get_productivity_report",
        "description": "گزارش بهره‌وری کارمند یا تیم. مثال: بهره‌وری این هفته چقدر بوده؟",
        "parameters": {"type": "object", "properties": {
            "employee_name": {"type": "string", "description": "خالی = همه تیم"},
            "period": {"type": "string", "enum": ["today", "week", "month"], "default": "week"},
        }},
    }},
    {"type": "function", "function": {
        "name": "check_and_apply_autonomy",
        "description": "چک کردن و ذخیره قوانین خودمختاری. وقتی کارفرما تأیید داد که دفعه بعد خودم انجام بدم",
        "parameters": {"type": "object", "properties": {
            "action_type": {"type": "string", "description": "نوع اقدامی که تأیید شده"},
            "condition": {"type": "string", "description": "شرط اجرا"},
            "approved": {"type": "boolean"},
        }, "required": ["action_type", "approved"]},
    }},
    {"type": "function", "function": {
        "name": "set_task_scoped_permission",
        "description": "دسترسی محدود به یه تسک — وقتی تسک تموم شد دسترسی خودکار قطع میشه",
        "parameters": {"type": "object", "properties": {
            "person_name": {"type": "string"},
            "task_id": {"type": "string"},
            "resource_type": {"type": "string"},
            "action": {"type": "string", "enum": ["read", "write"]},
        }, "required": ["person_name", "task_id", "resource_type"]},
    }},
]
