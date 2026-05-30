"""
Dispatcher ابزارها — نسخه ۳.
همه ماژول‌ها: مشتری، کارمند، کالا، هزینه، فاکتور، گزارش، سرچ، هشدار، کارفرما.
"""
import json
from sqlalchemy.ext.asyncio import AsyncSession
from app.modules.customers import service as customers
from app.modules.expenses import service as expenses
from app.modules.employees import service as employees
from app.modules.inventory import service as inventory
from app.modules.sales import service as sales
from app.modules.reports import excel_service
from app.modules.reports import advanced_reports
from app.modules.reports import search_service
from app.modules.reports import alerts_service
from app.modules.reports import invoice_excel
from app.modules import tenant_service
from app.modules import media_service
from app.modules import persons_service
from app.modules import communication_service
from app.modules.reminders import service as reminders
from app.ai import pending_files
from app.ai import pending_uploads
from app.ai import outbox


async def dispatch(session: AsyncSession, tenant_id: int, user_id: int,
                   tool_name: str, args: dict, role: str = "owner") -> str:
    import logging as _log
    logger = _log.getLogger("moonax.tools")

    # کارفرما به همه چیز دسترسی داره
    if role != "owner":
        from app.modules import roles
        if not roles.is_tool_allowed(role, tool_name):
            logger.info(f"[TOOL✗ ACCESS] {tool_name} | role={role}")
            return roles.get_denied_message(role)

    logger.info(f"[TOOL→] {tool_name} | {json.dumps(args, ensure_ascii=False)[:300]}")

    try:
        # ─── اکسل خروجی ───
        if tool_name == "export_excel":
            data_type = args.get("data_type")
            exporter = excel_service.EXPORTERS.get(data_type)
            if not exporter:
                return f"⚠️ نوع «{data_type}» پشتیبانی نمی‌شود."
            buffer, filename = await exporter(session, tenant_id)
            pending_files.add_file(user_id, buffer, filename)
            labels = {"customers": "مشتریان", "expenses": "هزینه‌ها",
                      "products": "کالاها", "employees": "کارمندان",
                      "invoices": "فاکتورها", "tenant": "اطلاعات فروشگاه"}
            return f"📊 فایل اکسل {labels.get(data_type, data_type)} آماده شد و الان می‌فرستم."

        if tool_name == "get_excel_template":
            data_type = args.get("data_type")
            if data_type not in excel_service.SCHEMAS:
                return f"⚠️ نوع «{data_type}» پشتیبانی نمی‌شود."
            buffer, filename = await excel_service.make_template(data_type)
            pending_files.add_file(user_id, buffer, filename)
            labels = {"customers": "مشتریان", "expenses": "هزینه‌ها",
                      "products": "کالاها", "employees": "کارمندان",
                      "invoices": "فاکتورها"}
            return (f"📋 فایل اکسل نمونه‌ی {labels.get(data_type, data_type)} رو می‌فرستم.\n"
                    f"پُرش کن و برام بفرست تا وارد سیستم کنم.")

        if tool_name == "export_work_log":
            emp_name = args.get("employee_name")
            buf, fname, err = await excel_service.export_work_logs(session, tenant_id, emp_name)
            if err:
                return f"⚠️ {err}"
            pending_files.add_file(user_id, buf, fname)
            return "📊 فایل گزارش کار آماده شد و الان می‌فرستم."

        if tool_name == "get_work_log_template":
            emp_name = args.get("employee_name")
            buf, fname = await excel_service.make_work_log_template(emp_name)
            pending_files.add_file(user_id, buf, fname)
            return "📋 فایل نمونه گزارش کار رو می‌فرستم. پُرش کن و برام بفرست."

        # ─── مشتریان ───
        if tool_name == "add_customer":
            return await customers.add_customer(session, tenant_id, **args)
        if tool_name == "list_customers":
            return await customers.list_customers(session, tenant_id, **args)
        if tool_name == "update_customer":
            return await customers.update_customer(session, tenant_id, **args)
        if tool_name == "delete_customer":
            return await customers.delete_customer(session, tenant_id, **args)
        if tool_name == "get_customer_detail":
            return await customers.get_customer_detail(session, tenant_id, **args)
        if tool_name == "search_customers":
            return await customers.search_customers(session, tenant_id, **args)
        if tool_name == "customer_statistics":
            return await customers.customer_statistics(session, tenant_id)
        if tool_name == "top_customers":
            return await customers.top_customers(session, tenant_id, **args)

        # ─── هزینه‌ها ───
        if tool_name == "add_expense":
            return await expenses.add_expense(session, tenant_id, **args)
        if tool_name == "delete_expense":
            return await expenses.delete_expense(session, tenant_id, **args)

        # ─── کالا و انبار ───
        if tool_name == "add_product":
            result = await inventory.add_product(session, tenant_id, **args)
            await _trigger_flows(session, tenant_id, "product_added",
                                  {"product_name": args.get("name", ""),
                                   "product_id": args.get("name", "")},
                                  user_id)
            return result
        if tool_name == "list_products":
            return await inventory.list_products(session, tenant_id, **args)
        if tool_name == "update_product":
            return await inventory.update_product(session, tenant_id, **args)
        if tool_name == "delete_product":
            return await inventory.delete_product(session, tenant_id, **args)

        # ─── کارمندان ───
        if tool_name == "add_employee":
            return await employees.add_employee(session, tenant_id, **args)
        if tool_name == "list_employees":
            return await employees.list_employees(session, tenant_id, **args)
        if tool_name == "update_employee":
            return await employees.update_employee(session, tenant_id, **args)
        if tool_name == "delete_employee":
            return await employees.delete_employee(session, tenant_id, **args)
        if tool_name == "get_employee_detail":
            return await employees.get_employee_detail(session, tenant_id, **args)
        if tool_name == "search_employees":
            return await employees.search_employees(session, tenant_id, **args)
        if tool_name == "employee_statistics":
            return await employees.employee_statistics(session, tenant_id)
        if tool_name == "add_salary_payment":
            return await employees.add_salary_payment(session, tenant_id, **args)
        if tool_name == "list_salary_payments":
            return await employees.list_salary_payments(session, tenant_id, **args)

        # ─── فاکتور / فروش ───
        if tool_name == "create_invoice":
            return await sales.create_invoice(session, tenant_id, **args)
        if tool_name == "confirm_invoice":
            result = await sales.confirm_invoice(session, tenant_id, **args)
            # trigger فلوهای invoice_confirmed
            await _trigger_flows(session, tenant_id, "invoice_confirmed",
                                  {"invoice_id": args.get("invoice_id"),
                                   "display_id": args.get("display_id", "")},
                                  user_id)
            return result
        if tool_name == "cancel_invoice":
            return await sales.cancel_invoice(session, tenant_id, **args)
        if tool_name == "list_invoices":
            return await sales.list_invoices(session, tenant_id, **args)
        if tool_name == "get_invoice_detail":
            return await sales.get_invoice_detail(session, tenant_id, **args)

        # ─── اکسل فاکتور ───
        if tool_name == "export_invoice_excel":
            did = args.get("invoice_display_id")
            buf, fname, err = await invoice_excel.make_invoice_excel(session, tenant_id, did)
            if err:
                return f"⚠️ {err}"
            pending_files.add_file(user_id, buf, fname)
            return f"📊 اکسل فاکتور {did} آماده شد و الان می‌فرستم."

        if tool_name == "blank_invoice_excel":
            buf, fname = await invoice_excel.make_blank_invoice_excel(session, tenant_id)
            pending_files.add_file(user_id, buf, fname)
            return "📋 فاکتور خالی با فرمول آماده شد و الان می‌فرستم."

        # ─── PDF فارسی ───
        if tool_name == "export_invoice_pdf":
            from app.modules.reports import pdf_service
            did = args.get("invoice_display_id")
            buf, fname, err = await pdf_service.make_invoice_pdf(session, tenant_id, did)
            if err:
                return f"⚠️ {err}"
            pending_files.add_file(user_id, buf, fname)
            return f"📄 PDF فاکتور {did} آماده شد و الان می‌فرستم."

        if tool_name == "export_report_pdf":
            from app.modules.reports import pdf_service
            rtype = args.get("report_type", "financial")
            period = args.get("period", "month")
            buf, fname = await pdf_service.make_data_report_pdf(
                session, tenant_id, rtype, period
            )
            pending_files.add_file(user_id, buf, fname)
            return f"📄 PDF گزارش آماده شد و الان می‌فرستم."

        # ─── گزارش‌های پیشرفته ───
        if tool_name == "sales_report":
            return await advanced_reports.sales_report(session, tenant_id, **args)
        if tool_name == "financial_report":
            return await advanced_reports.financial_report(session, tenant_id, **args)
        if tool_name == "debtors_report":
            return await advanced_reports.debtors_report(session, tenant_id)
        if tool_name == "inventory_report":
            return await advanced_reports.inventory_report(session, tenant_id)
        if tool_name == "smart_search":
            return await advanced_reports.smart_search(session, tenant_id, **args)

        # ─── سرچ اینترنتی ───
        if tool_name == "web_search_task":
            query = args.get("query", "")
            priority = args.get("priority", "instant")
            label, task_id = await search_service.create_search_task(
                session, tenant_id, user_id, query, priority
            )
            # فوری → همین الان اجرا کن
            if priority == "instant":
                await search_service.execute_search(session, task_id)
                msg, excel_data, fname = await search_service.get_search_result(session, task_id)
                if excel_data:
                    import io
                    buf = io.BytesIO(excel_data)
                    pending_files.add_file(user_id, buf, fname)
                    return msg + "\n📎 فایل اکسل نتایج رو الان می‌فرستم."
                return msg or "نتیجه‌ای پیدا نشد."
            else:
                return (f"✅ جستجوی «{query}» ثبت شد!\n"
                        f"{label}\n"
                        f"شناسه وظیفه: {task_id}\n"
                        f"وقتی تموم شد بهت خبر می‌دم.")

        if tool_name == "get_search_result":
            task_id = args.get("task_id")
            msg, excel_data, fname = await search_service.get_search_result(session, task_id)
            if excel_data:
                import io
                buf = io.BytesIO(excel_data)
                pending_files.add_file(user_id, buf, fname)
                return msg + "\n📎 فایل اکسل نتایج رو الان می‌فرستم."
            return msg or "نتیجه‌ای نیست."

        # ─── مدیریت کارفرما ───
        if tool_name == "update_tenant_info":
            return await tenant_service.update_tenant_info(session, tenant_id, **args)
        if tool_name == "get_tenant_info":
            return await tenant_service.get_tenant_info(session, tenant_id)

        # ─── هشدارها ───
        if tool_name == "check_alerts":
            alerts = await alerts_service.check_critical_alerts(session, tenant_id)
            if alerts:
                return "🚨 هشدارها:\n" + "\n".join(alerts)
            return "✅ همه چیز عادیه! هشداری نیست."

        # ─── گزارش قدیمی ───
        if tool_name == "get_report":
            report_type = args.get("report_type")
            if report_type == "expenses_today":
                return await expenses.get_expenses_today(session, tenant_id)
            if report_type in ("sales_today", "sales_month"):
                period = "today" if report_type == "sales_today" else "month"
                return await advanced_reports.sales_report(session, tenant_id, period=period)
            if report_type == "profit":
                return await advanced_reports.financial_report(session, tenant_id, period="month")
            if report_type == "debts":
                return await advanced_reports.debtors_report(session, tenant_id)
            if report_type == "expenses_month":
                return await advanced_reports.financial_report(session, tenant_id, period="month")
            return f"📊 گزارش «{report_type}» در دسترس نیست."

        # ─── یادآور (ریمایندر) ───
        if tool_name == "add_reminder":
            return await reminders.add_reminder(session, tenant_id, user_id, **args)
        if tool_name == "list_reminders":
            return await reminders.list_reminders(session, tenant_id, user_id, **args)
        if tool_name == "complete_reminder":
            return await reminders.complete_reminder(session, tenant_id, user_id, **args)
        if tool_name == "delete_reminder":
            return await reminders.delete_reminder(session, tenant_id, user_id, **args)

        # ─── عکس موجودیت‌ها ───
        if tool_name == "save_entity_photo":
            upload = pending_uploads.get_upload(user_id)
            if not upload:
                return "⚠️ عکسی برای ذخیره پیدا نکردم. اول عکس رو بفرست."
            photo_bytes, mime = upload
            return await media_service.save_entity_photo(
                session, tenant_id,
                args.get("entity_type"), args.get("entity_name"),
                photo_bytes, mime,
            )
        if tool_name == "get_entity_photo":
            photo_bytes, mime, err = await media_service.get_entity_photo(
                session, tenant_id,
                args.get("entity_type"), args.get("entity_name"),
            )
            if err:
                return f"⚠️ {err}"
            import io
            ext = "jpg" if "jpeg" in (mime or "") else "png"
            fname = f"{args.get('entity_name', 'photo')}.{ext}"
            pending_files.add_file(user_id, io.BytesIO(photo_bytes), fname)
            return f"📷 عکس {args.get('entity_name')} رو می‌فرستم."

        # ─── اشخاص و لینک دعوت ───
        if tool_name == "add_person":
            return await persons_service.add_person(session, tenant_id, **args)
        if tool_name == "list_persons":
            return await persons_service.list_persons(session, tenant_id, **args)

        # ─── لینک‌های دعوت جدید ───
        if tool_name == "create_employee_invite_link":
            from app.core.runtime import get_bot_username
            from app.database.models.business import Employee
            from sqlalchemy import select as _sel2

            person_name = args.get("person_name", "")
            link_type = args.get("link_type", "")

            # اگه link_type مشخص نشده، بر اساس اطلاعات کارمند تشخیص بده
            if not link_type:
                emp = await session.scalar(
                    _sel2(Employee).where(
                        Employee.tenant_id == tenant_id,
                        Employee.name.ilike(f"%{person_name}%"),
                    ).limit(1)
                )
                if emp:
                    # چک فیلدهای اصلی
                    missing = []
                    for field in ["position", "department", "address"]:
                        if not getattr(emp, field, None):
                            missing.append(field)
                    if missing:
                        # اطلاعات ناقصه — بپرس
                        missing_fa = {"position": "سمت", "department": "بخش", "address": "آدرس"}
                        missing_names = [missing_fa.get(f, f) for f in missing]
                        return (
                            f"اطلاعات {emp.name} کامل نیست ({', '.join(missing_names)} خالیه).\n"
                            f"ترجیح میدی خودت الان کامل کنی، یا کارمند موقع ورود پر کنه؟"
                        )
                    else:
                        link_type = "prefilled"
                else:
                    link_type = "self"

            result = await persons_service.create_employee_invite_link(
                session, tenant_id,
                bot_username=get_bot_username(),
                person_name=person_name,
                link_type=link_type,
                expires_hours=args.get("expires_hours", 24 * 7),
            )
            # ارسال دو پیام جدا
            if "||SPLIT_MSG||" in result:
                parts = result.split("||SPLIT_MSG||", 1)
                outbox.queue_message(user_id, {
                    "chat_id": user_id,
                    "text": parts[1],
                })
                return parts[0]
            return result
        if tool_name == "create_customer_invite_link":
            from app.core.runtime import get_bot_username
            return await persons_service.create_customer_invite_link(
                session, tenant_id,
                bot_username=get_bot_username(),
                acquaintance_type=args.get("acquaintance_type", "new"),
                person_name=args.get("person_name"),
                person_phone=args.get("person_phone"),
                max_uses=args.get("max_uses"),
                expires_hours=args.get("expires_hours"),
            )
        if tool_name == "create_collaborator_invite_link":
            from app.core.runtime import get_bot_username
            return await persons_service.create_collaborator_invite_link(
                session, tenant_id,
                bot_username=get_bot_username(),
                acquaintance_type=args.get("acquaintance_type", "new"),
                person_name=args.get("person_name"),
                max_uses=args.get("max_uses"),
                expires_hours=args.get("expires_hours"),
            )
        # backward compat
        # backward compat — اگه مدل از tool قدیمی استفاده کرد
        if tool_name == "create_invite_link":
            from app.core.runtime import get_bot_username
            role = args.get("role", "")
            # اگه role مشخص نشده، از مدل بخواه مشخص کنه
            if not role:
                return "⚠️ نوع لینک مشخص نیست. از tool صحیح استفاده کن: create_employee_invite_link یا create_customer_invite_link"
            if role == "employee":
                return await persons_service.create_employee_invite_link(
                    session, tenant_id, bot_username=get_bot_username(),
                    person_name=args.get("person_name", ""),
                    link_type=args.get("link_type", "self"),
                )
            elif role in ("collaborator", "partner"):
                return await persons_service.create_collaborator_invite_link(
                    session, tenant_id, bot_username=get_bot_username(),
                    acquaintance_type=args.get("acquaintance_type", "new"),
                )
            else:
                return await persons_service.create_customer_invite_link(
                    session, tenant_id, bot_username=get_bot_username(),
                    acquaintance_type=args.get("acquaintance_type", "new"),
                )
        if tool_name == "list_invite_links":
            return await persons_service.list_invite_links(session, tenant_id)
        if tool_name == "revoke_invite_link":
            return await persons_service.revoke_invite_link(session, tenant_id, **args)
        if tool_name == "revoke_all_invite_links":
            return await persons_service.revoke_all_invite_links(session, tenant_id)

        # ─── سیستم ارتباطی ───
        if tool_name == "send_message_to_owner":
            person = await persons_service.get_person_by_telegram(session, user_id)
            if not person:
                return "⚠️ پروفایلت پیدا نشد."
            message_text = args.get("message", "")
            is_urgent = bool(args.get("is_urgent", False))

            from app.database.models.tenant import Tenant
            tenant = await session.get(Tenant, tenant_id)
            if not tenant:
                return "⚠️ مشکلی پیش اومد."

            role_fa = roles.ROLE_LABELS.get(person.role, person.role)
            prefix = f"📩 {role_fa} «{person.full_name}» می‌گه"
            if is_urgent:
                prefix = f"🚨 فوری — {prefix}"
            full_msg = f"{prefix}:\n\n{message_text}"

            # ذخیره در تاریخچه کارفرما با context کامل
            from app.ai.orchestrator import _save_message
            await _save_message(session, tenant_id, tenant.owner_telegram_id, {
                "role": "user",
                "content": f"[پیام از {person.full_name}]: {message_text}",
            })

            outbox.queue_message(user_id, {
                "chat_id": tenant.owner_telegram_id,
                "text": full_msg,
            })

            if is_urgent:
                return "✅ پیام فوری به کارفرما فرستاده شد."
            return "✅ پیامت به کارفرما فرستاده شد."

        if tool_name == "view_messages":
            return await communication_service.get_contact_summary(
                session, tenant_id, **args
            )

        if tool_name == "set_report_schedule":
            return await communication_service.set_report_schedule(
                session, tenant_id, **args
            )

        if tool_name == "disable_report_schedule":
            return await communication_service.disable_report_schedule(
                session, tenant_id
            )

        if tool_name == "schedule_meetings":
            from app.modules.goal_service import (
                create_schedule_goal, get_persons_by_role, add_waiting
            )
            role_filter = args.get("role_filter", "employee")
            owner_slots = args.get("owner_free_slots", "")
            meeting_date = args.get("meeting_date", "فردا")
            topic = args.get("meeting_topic", "جلسه خصوصی")

            persons = await get_persons_by_role(session, tenant_id, role_filter)
            if not persons:
                return f"⚠️ هیچ {role_filter} متصلی پیدا نشد."

            goal = await create_schedule_goal(
                session, tenant_id, user_id, persons,
                owner_slots, meeting_date, topic
            )

            # همزمان به همه پیام بده
            from app.modules.goal_service import get_steps
            steps = get_steps(goal)
            for step in steps:
                tid = step["person_telegram_id"]
                await add_waiting(session, goal, tid, "زمان مناسب")
                outbox.queue_message(user_id, {
                    "chat_id": tid,
                    "text": step["message"],
                })

            role_fa = {"employee": "کارمند", "customer": "مشتری",
                       "collaborator": "همکار"}.get(role_filter, role_filter)
            return (f"✅ به {len(persons)} {role_fa} همزمان پیام فرستادم.\n"
                    f"وقتی جواب دادن، نتیجه رو بهت گزارش میدم.")

        if tool_name == "send_broadcast":
            message = args.get("message", "")
            role_filter = args.get("role_filter")
            person_names = args.get("person_names")
            expects_reply = bool(args.get("expects_reply", False))
            goal = args.get("goal", "")  # هدف مکالمه
            next_step = args.get("next_step", "")  # مرحله بعد

            # چک عکس آپلود شده
            upload = pending_uploads.get_upload(user_id)

            broadcast, targets = await communication_service.create_broadcast(
                session, tenant_id, message,
                role_filter=role_filter, person_names=person_names,
                expects_reply=expects_reply,
            )
            if not broadcast:
                return "⚠️ گیرنده‌ای پیدا نشد. مطمئن شو افراد به ربات وصل شدن."

            for t in targets:
                if upload:
                    # عکس + کپشن
                    photo_bytes, mime = upload
                    outbox.queue_photo(user_id, t.person_telegram_id,
                                       photo_bytes, mime, message)
                else:
                    outbox.queue_message(user_id, t.person_telegram_id, message)
                t.delivered = True

            # ذخیره goal برای پیگیری
            if goal or next_step:
                import json as _json
                try:
                    broadcast.goal_json = _json.dumps({
                        "goal": goal,
                        "next_step": next_step,
                        "owner_user_id": user_id,
                    }, ensure_ascii=False)
                except Exception:
                    pass

            await session.commit()

            kind = "سؤال" if expects_reply else "پیام"
            result = f"✅ {kind} گروهی ({broadcast.display_id}) به {len(targets)} نفر فرستاده شد."
            if expects_reply:
                result += f"\nوقتی جواب دادن بهت خبر میدم."
            if goal:
                result += f"\nهدف: {goal}"
            return result

        if tool_name == "broadcast_status":
            return await communication_service.get_broadcast_status(
                session, tenant_id, args.get("broadcast_display_id")
            )

        if tool_name == "send_direct_message":
            person_name = args.get("person_name", "")
            message = args.get("message", "")
            # پیدا کردن شخص متصل
            from app.database.models.business import Person
            from sqlalchemy import select as _select
            person = await session.scalar(
                _select(Person).where(
                    Person.tenant_id == tenant_id,
                    Person.full_name.ilike(f"%{person_name}%"),
                    Person.telegram_id.isnot(None),
                ).limit(1)
            )
            if not person:
                return (f"⚠️ «{person_name}» پیدا نشد یا هنوز به ربات وصل نشده. "
                        f"اول باید لینک دعوت رو زده باشه.")
            outbox.queue_message(
                user_id, person.telegram_id,
                message
            )
            return f"✅ پیام به «{person.full_name}» فرستاده شد."

        # ─── مدیریت پیشرفته پرسن‌ها ───
        if tool_name == "delete_person":
            return await persons_service.delete_person(session, tenant_id, **args)

        if tool_name == "create_followup":
            from app.database.models.tenant import Tenant
            tenant = await session.get(Tenant, tenant_id)
            owner_tid = tenant.owner_telegram_id if tenant else user_id
            return await persons_service.create_followup(
                session, tenant_id, owner_tid,
                args.get("person_display_id", ""),
                args.get("message", ""),
                args.get("interval_minutes", 60),
                args.get("max_attempts", 0),
            )

        if tool_name == "stop_followup":
            return await persons_service.stop_followup(
                session, tenant_id, args.get("person_name", "")
            )

        if tool_name == "list_followups":
            return await persons_service.list_followups(session, tenant_id)

        if tool_name == "send_photo_to_person":
            upload = pending_uploads.get_upload(user_id)
            if not upload:
                return "⚠️ عکسی پیدا نکردم. اول عکس رو بفرست."
            photo_bytes, mime = upload
            person_name = args.get("person_name", "")
            caption = args.get("caption", "")
            from app.database.models.business import Person
            from sqlalchemy import select as _sel
            person = await session.scalar(
                _sel(Person).where(
                    Person.tenant_id == tenant_id,
                    Person.full_name.ilike(f"%{person_name}%"),
                    Person.telegram_id.isnot(None),
                ).limit(1)
            )
            if not person:
                return f"⚠️ «{person_name}» پیدا نشد یا به ربات وصل نشده."
            outbox.queue_photo(user_id, person.telegram_id, photo_bytes, mime, caption)
            return f"📷 عکس برای «{person.full_name}» ارسال می‌شه."

        if tool_name == "send_file_to_person":
            """ارسال هر نوع فایل (PDF، اکسل، ...) که کاربر آپلود کرده یا سیستم ساخته به یک شخص."""
            person_name = args.get("person_name", "")
            caption = args.get("caption", "")
            file_type = args.get("file_type", "any")  # invoice / pdf / excel / last_generated / any

            from app.database.models.business import Person
            from sqlalchemy import select as _sel

            # پیدا کردن شخص
            person = await session.scalar(
                _sel(Person).where(
                    Person.tenant_id == tenant_id,
                    Person.full_name.ilike(f"%{person_name}%"),
                    Person.telegram_id.isnot(None),
                ).limit(1)
            )
            if not person:
                return f"⚠️ «{person_name}» پیدا نشد یا به ربات وصل نشده."

            # پیدا کردن فایل
            file_bytes = None
            fname = "file"

            # ۱. آخرین فایل آپلود‌شده
            upload = pending_uploads.get_upload(user_id)
            if upload and file_type in ("any", "uploaded"):
                photo_bytes, mime = upload
                outbox.queue_photo(user_id, person.telegram_id, photo_bytes, mime, caption)
                return f"✅ فایل برای «{person.full_name}» ارسال شد."

            # ۲. فاکتور آخر
            if file_type in ("invoice", "any"):
                from app.modules.reports.invoice_excel import export_invoice_excel
                from app.database.models.business import Invoice
                last_inv = await session.scalar(
                    _sel(Invoice).where(
                        Invoice.tenant_id == tenant_id,
                    ).order_by(Invoice.id.desc()).limit(1)
                )
                if last_inv:
                    try:
                        buf, fname = await export_invoice_excel(session, last_inv.id)
                        if buf:
                            file_bytes = buf
                    except Exception:
                        pass

            # ۳. آخرین فایل تولیدشده توسط سیستم
            if not file_bytes:
                files = pending_files.peek_files(user_id)
                if files:
                    file_bytes, fname = files[-1]

            if file_bytes:
                import io as _io
                buf = file_bytes if hasattr(file_bytes, 'read') else _io.BytesIO(file_bytes if isinstance(file_bytes, bytes) else file_bytes.getvalue())
                outbox.queue_message(user_id, {
                    "type": "document",
                    "chat_id": person.telegram_id,
                    "document_buf": buf,
                    "filename": fname,
                    "caption": caption,
                })
                return f"✅ فایل «{fname}» برای «{person.full_name}» ارسال شد."

            return "⚠️ فایلی برای ارسال پیدا نشد. اول فایل رو آپلود کن یا بساز."

        # ─── اشتراک ───
        if tool_name == "request_trial":
            from app.modules.subscription_service import request_trial
            from app.database.models.tenant import Tenant
            tenant = await session.get(Tenant, tenant_id)
            owner_tid = tenant.owner_telegram_id if tenant else user_id
            msg, req_id = await request_trial(session, tenant_id, owner_tid)
            if req_id:
                outbox.queue_admin_notification(user_id, req_id, "trial", tenant)
            return msg

        if tool_name == "get_subscription_status":
            from app.database.models.tenant import Tenant, SubscriptionStatus
            from app.utils.jalali import to_jalali_str
            tenant = await session.get(Tenant, tenant_id)
            if not tenant:
                return "⚠️ اطلاعات پیدا نشد."
            if tenant.subscription_status == SubscriptionStatus.TRIAL:
                if tenant.trial_ends_at:
                    from datetime import timezone as _tz
                    remaining = (tenant.trial_ends_at - __import__('datetime').datetime.now(_tz.utc)).days
                    return (f"📋 وضعیت: تست رایگان فعال\n"
                            f"⏳ {remaining} روز دیگه تموم می‌شه\n"
                            f"تاریخ پایان: {to_jalali_str(tenant.trial_ends_at.date())}")
                return "⏳ منتظر تأیید ادمین هستی. کمی صبر کن."
            elif tenant.subscription_status == SubscriptionStatus.ACTIVE:
                remaining = (tenant.subscription_ends_at - __import__('datetime').datetime.now(__import__('datetime').timezone.utc)).days if tenant.subscription_ends_at else "نامحدود"
                return (f"✅ اشتراک فعال\n"
                        f"⏳ {remaining} روز باقی مانده\n"
                        f"تاریخ پایان: {to_jalali_str(tenant.subscription_ends_at.date()) if tenant.subscription_ends_at else '—'}")
            return "❌ اشتراک منقضی شده. برای تمدید رسید پرداخت بفرست."

        if tool_name == "submit_payment_receipt":
            upload = pending_uploads.get_upload(user_id)
            if not upload:
                return "⚠️ عکس رسید پیدا نکردم. لطفاً عکس رسید رو بفرست."
            photo_bytes, mime = upload
            from app.modules.subscription_service import submit_payment_receipt
            import base64 as _b64
            file_id = _b64.b64encode(photo_bytes[:20]).decode()  # شناسه موقت
            msg, req_id = await submit_payment_receipt(session, tenant_id, user_id, file_id)
            from app.database.models.tenant import Tenant
            tenant = await session.get(Tenant, tenant_id)
            outbox.queue_admin_notification(user_id, req_id, "payment", tenant, photo_bytes, mime)
            return msg

        # ─── فیش تصفیه حساب ───
        if tool_name == "generate_settlement":
            from app.modules.reports import settlement_service
            pdf_buf, fname, msg = await settlement_service.generate_settlement(
                session, tenant_id, user_id,
                employee_name=args.get("employee_name", ""),
                mode=args.get("mode", "auto"),
                year=args.get("year"),
                month_start=args.get("month_start"),
                day_start=args.get("day_start"),
                month_end=args.get("month_end"),
                day_end=args.get("day_end"),
                total_amount=args.get("total_amount"),
                work_hours=args.get("work_hours", 0),
                work_days=args.get("work_days", 0),
                overtime_hours=args.get("overtime_hours", 0),
                night_hours=args.get("night_hours", 0),
                holiday_days=args.get("holiday_days", 0),
                friday_days=args.get("friday_days", 0),
                leave_used=args.get("leave_used", 0),
                unused_leave=args.get("unused_leave", 0),
                shift_type=args.get("shift_type", ""),
                repair_wage=args.get("repair_wage", 0),
                loan_deduction=args.get("loan_deduction", 0),
                marital_status=args.get("marital_status", ""),
                children_status=args.get("children_status", ""),
                work_type=args.get("work_type", ""),
            )
            if pdf_buf:
                pending_files.add_file(user_id, pdf_buf, fname)
                return f"📄 فیش تصفیه حساب آماده شد و الان می‌فرستم.\n\n{msg}"
            return msg

        # ─── جواب صوتی (TTS) ───
        if tool_name == "voice_reply":
            from app.modules import tts_service
            text = args.get("text", "")
            voice_key = await tts_service.get_voice_key(session, tenant_id)
            buf, fname = await tts_service.generate_voice(text, voice_key=voice_key)
            if buf:
                pending_files.add_file(user_id, buf, fname)
                return "🎤 ویس آماده شد و الان می‌فرستم."
            return "⚠️ خطا در تولید صدا. متنی جواب می‌دم:\n\n" + text

        if tool_name == "set_voice":
            from app.modules.tts_service import set_voice as _set_voice, list_voices
            vk = args.get("voice_key", "list")
            if vk == "list":
                return await list_voices()
            return await _set_voice(session, tenant_id, vk)

        # ─── خروجی دسته‌جمعی ───
        if tool_name == "batch_export":
            from app.modules.reports import batch_service
            export_type = args.get("export_type", "settlement")
            output_format = args.get("output_format", "zip")
            filters = {
                "year": args.get("year"),
                "month_start": args.get("month_start"),
                "month_end": args.get("month_end"),
                "employee_names": args.get("employee_names"),
            }
            buf, fname, msg, files = await batch_service.batch_export(
                session, tenant_id, export_type, filters, output_format
            )
            if buf:
                # zip
                pending_files.add_file(user_id, buf, fname)
                return msg + "\n📎 فایل zip رو الان می‌فرستم."
            elif files:
                # separate
                for f_buf, f_name in files:
                    f_buf.seek(0)
                    pending_files.add_file(user_id, f_buf, f_name)
                return msg + "\n📎 فایل‌ها رو الان یکی یکی می‌فرستم."
            return msg

        # ─── بکاپ ───
        if tool_name == "backup_data":
            from app.modules import backup_service
            from app.core.config import settings
            full = args.get("full_system", False)
            if full:
                if user_id not in settings.admin_id_list:
                    return "⚠️ بکاپ کل سیستم فقط برای ادمین اصلیه."
                buf, fname = await backup_service.backup_full_system(session)
            else:
                buf, fname = await backup_service.backup_tenant(session, tenant_id)
            pending_files.add_file(user_id, buf, fname)
            return f"📦 بکاپ آماده شد و الان می‌فرستم."

        # ─── برند ───
        if tool_name == "save_brand_config":
            from app.database.models.business import BrandConfig
            from sqlalchemy import select as _sel
            brand = await session.scalar(
                _sel(BrandConfig).where(BrandConfig.tenant_id == tenant_id)
            )
            if not brand:
                brand = BrandConfig(tenant_id=tenant_id)
                session.add(brand)
            if args.get("primary_color"):
                brand.primary_color = args["primary_color"]
            if args.get("secondary_color"):
                brand.secondary_color = args["secondary_color"]
            if args.get("slogan"):
                brand.slogan = args["slogan"]
            if args.get("tone"):
                brand.tone = args["tone"]
            if "auto_send_approval" in args:
                brand.auto_send_approval = args["auto_send_approval"]
            await session.commit()
            return "✅ تنظیمات برند ذخیره شد."

        if tool_name == "get_brand_config":
            from app.database.models.business import BrandConfig
            from sqlalchemy import select as _sel
            brand = await session.scalar(
                _sel(BrandConfig).where(BrandConfig.tenant_id == tenant_id)
            )
            if not brand:
                return "هنوز تنظیمات برند ثبت نشده. بگو رنگ، شعار و لحنت چیه."
            lines = ["🎨 تنظیمات برند:"]
            if brand.primary_color:
                lines.append(f"رنگ اصلی: {brand.primary_color}")
            if brand.secondary_color:
                lines.append(f"رنگ ثانویه: {brand.secondary_color}")
            if brand.slogan:
                lines.append(f"شعار: {brand.slogan}")
            if brand.tone:
                lines.append(f"لحن: {brand.tone}")
            lines.append(f"تأیید قبل ارسال: {'بله' if brand.auto_send_approval else 'خیر'}")
            return "\n".join(lines)

        # ─── اقساط ───
        if tool_name == "add_installment":
            from app.modules import installment_service
            return await installment_service.add_installment(session, tenant_id, **args)
        if tool_name == "list_installments":
            from app.modules import installment_service
            return await installment_service.list_installments(session, tenant_id, **args)
        if tool_name == "pay_installment":
            from app.modules import installment_service
            return await installment_service.pay_installment(session, tenant_id, **args)
        if tool_name == "overdue_installments":
            from app.modules import installment_service
            return await installment_service.overdue_installments(session, tenant_id)

        # ─── تاریخچه خرید ───
        if tool_name == "customer_purchase_history":
            return await customers.customer_purchase_history(session, tenant_id, **args)

        # ─── طراحی پوستر ───
        if tool_name == "generate_poster":
            from app.modules import design_service
            # اگه عکس آپلود شده، به پوستر اضافه کن
            upload = pending_uploads.get_upload(user_id)
            if upload and not args.get("product_id"):
                # عکس مستقیم از آپلود — بدون نیاز به محصول
                args["_uploaded_image"] = upload[0]
            buf, fname, msg = await design_service.generate_poster(session, tenant_id, **{
                k: v for k, v in args.items() if k != "_uploaded_image"
            })
            if buf:
                pending_files.add_file(user_id, buf, fname)
                return msg + "\n📎 پوستر رو الان می‌فرستم."
            return msg

        if tool_name == "generate_slide_post":
            from app.modules import design_service
            slides_data = args.get("slides", [])
            size = args.get("size", "post")
            creativity = args.get("creativity", 30)
            files, msg = await design_service.generate_slide_post(
                session, tenant_id, slides_data, size, creativity
            )
            for buf, fname in files:
                pending_files.add_file(user_id, buf, fname)
            return msg

        if tool_name == "generate_catalog":
            from app.modules import design_service
            buf, fname, msg = await design_service.generate_catalog(
                session, tenant_id,
                product_ids=args.get("product_ids"),
                title=args.get("title", "کاتالوگ محصولات"),
            )
            if buf:
                pending_files.add_file(user_id, buf, fname)
                return msg + "\n📎 کاتالوگ رو الان می‌فرستم."
            return msg

        if tool_name == "crop_image":
            from app.modules import design_service
            upload = pending_uploads.get_upload(user_id)
            if not upload:
                return "⚠️ اول عکس رو بفرست بعد بگو برش بزنم."
            photo_bytes, _ = upload
            rows = args.get("rows", 1)
            cols = args.get("cols", 1)
            files = await design_service.crop_image(photo_bytes, rows, cols)
            for buf, fname in files:
                pending_files.add_file(user_id, buf, fname)
            return f"✅ {len(files)} تکه آماده شد."

        if tool_name == "save_design_template":
            from app.modules import design_service
            return await design_service.save_template(session, tenant_id, **args)

        if tool_name == "batch_design":
            from app.modules import design_service
            files, msg = await design_service.batch_design_from_template(
                session, tenant_id,
                template_name=args.get("template_name", ""),
                items=args.get("items", []),
            )
            for buf, fname in files:
                pending_files.add_file(user_id, buf, fname)
            return msg

        # ─── پروژه ───
        if tool_name == "create_project":
            from app.modules import project_service
            return await project_service.create_project(session, tenant_id, **args)
        if tool_name == "get_project_info":
            from app.modules import project_service
            return await project_service.get_project_info(session, tenant_id, **args)
        if tool_name == "add_project_document":
            from app.modules import project_service
            return await project_service.add_project_document(session, tenant_id, **args)
        if tool_name == "list_projects":
            from app.modules import project_service
            return await project_service.list_projects(session, tenant_id)
        if tool_name == "add_task":
            from app.modules import project_service
            return await project_service.add_task(session, tenant_id, **args)
        if tool_name == "relay_message_to_employee":
            from app.database.models.business import Person
            from sqlalchemy import select as _sel
            to_person = await session.scalar(_sel(Person).where(
                Person.tenant_id == tenant_id,
                Person.full_name.ilike(f"%{args.get('to_name', '')}%"),
                Person.telegram_id.isnot(None),
            ).limit(1))
            if not to_person:
                return f"⚠️ «{args.get('to_name')}» پیدا نشد یا وصل نیست."
            sender = await persons_service.get_person_by_telegram(session, user_id)
            sender_name = sender.full_name if sender else "همکار"
            msg_text = args.get("message", "")
            full_msg = f"پیام از {sender_name}:\n{msg_text}"
            outbox.queue_message(user_id, {"chat_id": to_person.telegram_id, "text": full_msg})
            if args.get("expect_reply", True):
                from app.modules.goal_service import create_approval_goal, add_waiting
                goal = await create_approval_goal(
                    session, tenant_id, user_id, to_person,
                    question=full_msg,
                    description=f"relay از {sender_name} به {to_person.full_name}",
                    action_if_positive="notify_owner",
                    message_if_positive=f"{to_person.full_name} پیام داد",
                )
                await add_waiting(session, goal, to_person.telegram_id, "reply")
                return f"✅ پیام به {to_person.full_name} فرستاده شد. وقتی جواب داد برات می‌فرستم."
            return f"✅ پیام به {to_person.full_name} فرستاده شد."

        if tool_name == "transfer_file_to_employee":
            upload = pending_uploads.get_upload(user_id)
            files_list = pending_files.peek_files(user_id)
            if not upload and not files_list:
                return "⚠️ فایلی برای ارسال پیدا نشد."
            from app.database.models.business import Person
            from sqlalchemy import select as _sel
            to_person = await session.scalar(_sel(Person).where(
                Person.tenant_id == tenant_id,
                Person.full_name.ilike(f"%{args.get('to_name', '')}%"),
                Person.telegram_id.isnot(None),
            ).limit(1))
            if not to_person:
                return f"⚠️ «{args.get('to_name')}» پیدا نشد."
            sender = await persons_service.get_person_by_telegram(session, user_id)
            caption = args.get("caption", "") or (f"از {sender.full_name}" if sender else "")
            if upload:
                photo_bytes, mime = upload
                outbox.queue_photo(user_id, to_person.telegram_id, photo_bytes, mime, caption)
            else:
                import io as _io
                buf, fname = files_list[-1]
                buf.seek(0)
                outbox.queue_message(user_id, {
                    "type": "document",
                    "chat_id": to_person.telegram_id,
                    "document_buf": _io.BytesIO(buf.read()),
                    "filename": fname,
                    "caption": caption,
                })
            return f"✅ فایل به {to_person.full_name} فرستاده شد."

        if tool_name == "apply_penalty_flow":
            from app.database.models.business import Employee
            from sqlalchemy import select as _sel
            emp = await session.scalar(_sel(Employee).where(
                Employee.tenant_id == tenant_id,
                Employee.name.ilike(f"%{args.get('employee_name', '')}%"),
            ).limit(1))
            if not emp:
                return f"⚠️ کارمند «{args.get('employee_name')}» پیدا نشد."
            vtype = args.get("violation_type", "deadline_miss")
            penalty_pct = float(args.get("penalty_percent", 0))
            fire_after = int(args.get("fire_after_count", 0))
            vtype_fa = {"deadline_miss": "ددلاین رد", "absence": "غیبت",
                        "late": "تأخیر", "quality": "کیفیت پایین"}.get(vtype, vtype)
            history = {}
            if hasattr(emp, 'notes') and emp.notes:
                try:
                    history = json.loads(emp.notes)
                except Exception:
                    pass
            violations = history.get("violations", [])
            violations.append({"type": vtype, "date": datetime.now(timezone.utc).isoformat()})
            history["violations"] = violations
            total = len([v for v in violations if v["type"] == vtype])
            if hasattr(emp, 'notes'):
                emp.notes = json.dumps(history, ensure_ascii=False)
            lines = [f"⚠️ تخلف «{vtype_fa}» برای {emp.name} ثبت شد — {total} بار"]
            if penalty_pct > 0:
                salary = float(emp.salary or 0)
                lines.append(f"💸 جریمه: {penalty_pct}٪ = {salary*penalty_pct/100:,.0f} تومان")
            if fire_after and total >= fire_after:
                emp.is_active = False
                lines.append(f"🔴 {emp.name} بعد از {total} تخلف اخراج شد.")
            await session.commit()
            return "\n".join(lines)

        if tool_name == "get_productivity_report":
            from app.database.models.business import Employee, DailyReport
            from sqlalchemy import select as _sel
            from datetime import timedelta
            period = args.get("period", "week")
            emp_name = args.get("employee_name", "")
            days = {"today": 1, "week": 7, "month": 30}.get(period, 7)
            since = datetime.now(timezone.utc) - timedelta(days=days)
            q = _sel(Employee).where(Employee.tenant_id == tenant_id, Employee.is_active == True)
            if emp_name:
                q = q.where(Employee.name.ilike(f"%{emp_name}%"))
            employees = (await session.scalars(q)).all()
            if not employees:
                return "⚠️ کارمندی پیدا نشد."
            lines = [f"📊 بهره‌وری — {period}:\n"]
            total_prod = 0
            count = 0
            for emp in employees:
                rpts = (await session.scalars(
                    _sel(DailyReport).where(
                        DailyReport.employee_id == emp.id,
                        DailyReport.report_date >= since,
                    )
                )).all()
                if rpts:
                    avg = sum(r.productivity_score or 0 for r in rpts) / len(rpts)
                    total_prod += avg
                    count += 1
                    em = "🟢" if avg >= 80 else ("🟡" if avg >= 60 else "🔴")
                    lines.append(f"{em} {emp.name}: {avg:.0f}٪")
                else:
                    lines.append(f"⚪ {emp.name}: گزارش نداره")
            if count > 1:
                lines.append(f"\n📈 میانگین: {total_prod/count:.0f}٪")
            return "\n".join(lines)

        if tool_name == "check_and_apply_autonomy":
            from app.database.models.business import TenantSettings
            from sqlalchemy import select as _sel
            ts = await session.scalar(_sel(TenantSettings).where(TenantSettings.tenant_id == tenant_id))
            if not ts:
                return "⚠️ تنظیمات پیدا نشد."
            rules = {}
            if ts.autonomy_rules:
                try:
                    rules = json.loads(ts.autonomy_rules)
                except Exception:
                    pass
            action = args.get("action_type", "")
            approved = args.get("approved", False)
            if approved:
                rules[action] = {"condition": args.get("condition", "always"),
                                  "approved_at": datetime.now(timezone.utc).isoformat()}
                ts.autonomy_rules = json.dumps(rules, ensure_ascii=False)
                await session.commit()
                return f"✅ قانون ثبت شد — دفعه بعد {action} خودکار اجرا میشه."
            else:
                rules.pop(action, None)
                ts.autonomy_rules = json.dumps(rules, ensure_ascii=False)
                await session.commit()
                return f"✅ ثبت شد — همیشه برای {action} تأیید می‌گیرم."

        if tool_name == "set_task_scoped_permission":
            from app.modules.goal_service import request_permission, approve_permission
            from app.database.models.business import Person
            from sqlalchemy import select as _sel
            person = await session.scalar(_sel(Person).where(
                Person.tenant_id == tenant_id,
                Person.full_name.ilike(f"%{args.get('person_name', '')}%"),
            ).limit(1))
            if not person:
                return "⚠️ شخص پیدا نشد."
            req = await request_permission(
                session, tenant_id, person.telegram_id, person.role,
                args.get("resource_type", ""), args.get("action", "read"),
            )
            await approve_permission(session, req.id, approval_type="once")
            return f"✅ دسترسی task-scoped برای «{person.full_name}» فعال شد."

        if tool_name == "notify_person_joined":
            """اطلاع‌رسانی داخلی — وقتی کسی وصل میشه."""
            from app.modules.notification_service import notify_owner_member_joined
            from app.database.models.business import Person
            from sqlalchemy import select as _sel
            person = await session.scalar(
                _sel(Person).where(Person.telegram_id == user_id)
            )
            if person:
                from app.database.models.tenant import Tenant
                tenant = await session.get(Tenant, tenant_id)
                if tenant:
                    import app.ai.outbox as _outbox
                    await _trigger_flows(
                        session, tenant_id, "employee_joined",
                        {"person_name": person.full_name, "role": person.role},
                        tenant.owner_telegram_id
                    )
            return "✅"

        if tool_name == "request_disconnect":
            person = await persons_service.get_person_by_telegram(session, user_id)
            if not person:
                return "⚠️ پروفایلت پیدا نشد."
            reason = args.get("reason", "")
            from app.database.models.tenant import Tenant
            tenant = await session.get(Tenant, tenant_id)
            if tenant:
                msg = f"📩 {person.full_name} می‌خواد از سیستم قطع بشه."
                if reason:
                    msg += f"\nدلیل: {reason}"
                msg += f"\n\nبرای تأیید بگو: «قطع اتصال {person.full_name} رو تأیید کن»"
                outbox.queue_message(user_id, {"chat_id": tenant.owner_telegram_id, "text": msg})
            return "✅ درخواستت به کارفرما فرستاده شد. منتظر تأییدشون باش."

        if tool_name == "move_task":
            from app.modules import project_service
            result = await project_service.move_task(session, tenant_id, **args)
            if args.get("new_list") == "approved":
                await _trigger_flows(session, tenant_id, "task_completed",
                                      {"task_id": args.get("task_id", "")}, user_id)
            return result
        if tool_name == "list_tasks":
            from app.modules import project_service
            return await project_service.list_tasks(session, tenant_id, **args)
        if tool_name == "project_report":
            from app.modules import project_service
            return await project_service.project_report(session, tenant_id)

        # ─── فلو ───
        if tool_name == "create_workflow":
            from app.modules import workflow_service
            trigger_condition = {
                "description": args.get("trigger_description", ""),
                "event": args.get("event_type", ""),
            }
            steps = args.get("steps", [])
            result = await workflow_service.create_workflow(
                session, tenant_id,
                name=args.get("name", ""),
                trigger_type=args.get("trigger_type", "condition"),
                trigger_condition=trigger_condition,
                steps=steps,
                target_role=args.get("target_role"),
                max_retries=args.get("max_retries", 3),
            )
            return result
        if tool_name == "list_workflows":
            from app.modules import workflow_service
            return await workflow_service.list_workflows(session, tenant_id)
        if tool_name == "delete_workflow":
            from app.modules import workflow_service
            return await workflow_service.delete_workflow(session, tenant_id, **args)
        if tool_name == "export_workflows_excel":
            from app.modules import workflow_service
            buf, fname = await workflow_service.export_workflows_excel(session, tenant_id)
            pending_files.add_file(user_id, buf, fname)
            return "📊 اکسل فلوها آماده شد."

        # ─── دسترسی ───
        if tool_name == "grant_permission":
            from app.modules import access_service
            return await access_service.grant_permission(session, tenant_id, **args)
        if tool_name == "list_permissions":
            from app.modules import access_service
            return await access_service.list_permissions(session, tenant_id)
        if tool_name == "revoke_permission":
            from app.modules import access_service
            return await access_service.revoke_permission(session, tenant_id, **args)
        if tool_name == "export_permissions_excel":
            from app.modules import access_service
            buf, fname = await access_service.export_permissions_excel(session, tenant_id)
            pending_files.add_file(user_id, buf, fname)
            return "🔐 اکسل دسترسی‌ها آماده شد (محرمانه)."

        # ─── گزارش روزانه ───
        if tool_name == "end_of_day_report":
            from app.modules import daily_report_service
            msg, _ = await daily_report_service.end_of_day_report(session, tenant_id)
            return msg

        # ─── داشبورد مالی ───
        if tool_name == "monthly_profit_loss":
            from app.modules import financial_dashboard
            return await financial_dashboard.monthly_profit_loss(session, tenant_id, **args)
        if tool_name == "cashflow_report":
            from app.modules import financial_dashboard
            return await financial_dashboard.cashflow_report(session, tenant_id, **args)
        if tool_name == "monthly_comparison":
            from app.modules import financial_dashboard
            return await financial_dashboard.monthly_comparison(session, tenant_id)
        if tool_name == "top_selling_products":
            from app.modules import financial_dashboard
            return await financial_dashboard.top_selling_products(session, tenant_id, **args)
        if tool_name == "financial_summary":
            from app.modules import financial_dashboard
            return await financial_dashboard.financial_summary(session, tenant_id)

        # ─── اطلاعیه مدیریت ───
        if tool_name == "send_announcement":
            from app.modules import announcement_service
            from app.ai.outbox import queue_message
            preview, tg_ids = await announcement_service.send_announcement(
                session, tenant_id,
                message=args.get("message", ""),
                target_role=args.get("target_role"),
                is_official=args.get("is_official", True),
            )
            if not tg_ids:
                return preview
            for tid in tg_ids:
                from app.database.models.business import TenantSettings
                from sqlalchemy import select as _sel
                ts = await session.scalar(_sel(TenantSettings).where(TenantSettings.tenant_id == tenant_id))
                header = "📢 اطلاعیه مدیریت\n\n" if args.get("is_official", True) else ""
                queue_message(user_id, {"chat_id": tid, "text": header + args.get("message", "")})
            return f"✅ اطلاعیه برای {len(tg_ids)} نفر فرستاده شد."

        if tool_name == "create_poll":
            from app.modules import announcement_service
            from app.ai.outbox import queue_message
            poll_msg, tg_ids, poll_data = await announcement_service.create_poll(
                session, tenant_id,
                question=args.get("question", ""),
                options=args.get("options", []),
                target_role=args.get("target_role"),
                is_anonymous=args.get("is_anonymous", False),
            )
            if not tg_ids:
                return "⚠️ هیچ شخص متصلی پیدا نشد."
            for tid in tg_ids:
                queue_message(user_id, {"chat_id": tid, "text": poll_msg})
            return f"📊 نظرسنجی برای {len(tg_ids)} نفر فرستاده شد."

        if tool_name == "send_checklist":
            from app.modules import announcement_service
            from app.ai.outbox import queue_message
            msg, tg_ids = await announcement_service.send_checklist(
                session, tenant_id,
                title=args.get("title", ""),
                items=args.get("items", []),
                target_role=args.get("target_role"),
            )
            for tid in tg_ids:
                queue_message(user_id, {"chat_id": tid, "text": msg})
            return f"📋 چک‌لیست برای {len(tg_ids)} نفر فرستاده شد."

        logger.info(f"[TOOL✗ UNKNOWN] {tool_name}")
        if tool_name == "disconnect_person":
            from app.modules.persons_service import disconnect_person
            return await disconnect_person(session, tenant_id,
                                           args.get("name", ""))

        if tool_name == "request_account_deletion":
            if not args.get("confirmed"):
                return (
                    "⚠️ قبل از حذف باید تأیید کنی.\n\n"
                    "با حذف اکانت:\n"
                    "• همه اطلاعات پاک میشه\n"
                    "• کارمندان دسترسی‌شون قطع میشه\n"
                    "• قابل بازگشت نیست\n\n"
                    "یه بکاپ کامل برات می‌فرستم. تأیید می‌کنی؟"
                )
            from app.modules.account_service import create_full_backup, delete_tenant_account
            buf = await create_full_backup(session, tenant_id)
            pending_files.add_file(user_id, buf, "backup.zip")
            result = await delete_tenant_account(session, tenant_id)
            return f"📦 بکاپ کامل آماده شد و ارسال میشه.\n{result}"

        if tool_name == "create_approval_goal":
            from app.modules.goal_service import create_approval_goal, add_waiting
            from app.database.models.business import Person
            from sqlalchemy import select as _sel
            target = await session.scalar(_sel(Person).where(
                Person.tenant_id == tenant_id,
                Person.full_name.ilike(f"%{args.get('target_name', '')}%"),
                Person.telegram_id.isnot(None),
            ).limit(1))
            if not target:
                return f"⚠️ «{args.get('target_name')}» پیدا نشد یا وصل نیست."
            goal = await create_approval_goal(
                session, tenant_id, user_id, target,
                question=args.get("question", ""),
                description=args.get("description", ""),
                action_if_positive=args.get("action_if_positive", "notify_owner"),
                message_if_positive=args.get("message_if_positive", ""),
                action_if_negative=args.get("action_if_negative", "notify_owner"),
                message_if_negative=args.get("message_if_negative", ""),
            )
            await add_waiting(session, goal, target.telegram_id, "approval")
            outbox.queue_message(user_id, {
                "chat_id": target.telegram_id,
                "text": args.get("question", ""),
            })
            return f"✅ سوال برای «{target.full_name}» فرستاده شد."

        if tool_name == "create_collection_goal":
            from app.modules.goal_service import (
                create_collection_goal, get_persons_by_role, add_waiting, get_steps
            )
            persons = await get_persons_by_role(
                session, tenant_id, args.get("role_filter", "employee")
            )
            if not persons:
                return "⚠️ هیچ شخص متصلی پیدا نشد."
            goal = await create_collection_goal(
                session, tenant_id, user_id, persons,
                question=args.get("question", ""),
                description=args.get("description", ""),
            )
            for step in get_steps(goal):
                tid = step["person_telegram_id"]
                await add_waiting(session, goal, tid, "info")
                outbox.queue_message(user_id, {
                    "chat_id": tid,
                    "text": step["message"],
                })
            return f"✅ سوال برای {len(persons)} نفر فرستاده شد."

        if tool_name == "request_permission_for_person":
            from app.modules.goal_service import request_permission
            from app.database.models.business import Person
            from sqlalchemy import select as _sel
            person = await session.scalar(_sel(Person).where(
                Person.tenant_id == tenant_id,
                Person.full_name.ilike(f"%{args.get('person_name', '')}%"),
            ).limit(1))
            if not person:
                return "⚠️ شخص پیدا نشد."
            req = await request_permission(
                session, tenant_id,
                person.telegram_id, person.role,
                args.get("resource_type", ""),
                args.get("action", "read"),
            )
            # به کارفرما پیشنهاد
            from app.database.models.tenant import Tenant
            tenant = await session.get(Tenant, tenant_id)
            if tenant:
                approval_type = args.get("suggested_approval_type", "once")
                suggest_msg = (
                    f"📋 «{person.full_name}» می‌خواد به {args.get('resource_type')} دسترسی داشته باشه.\n"
                    f"پیشنهاد: {approval_type}\n"
                    f"برای تأیید بگو: «درخواست {req.id} رو تأیید کن — {approval_type}»"
                )
                outbox.queue_message(user_id, {
                    "chat_id": tenant.owner_telegram_id,
                    "text": suggest_msg,
                })
            return f"✅ درخواست ثبت شد (ID: {req.id}). منتظر تأیید کارفرما."

        if tool_name == "approve_permission_request":
            from app.modules.goal_service import approve_permission
            from datetime import timedelta
            expires_at = None
            if args.get("expires_days"):
                expires_at = datetime.now(timezone.utc) + timedelta(days=args["expires_days"])
            return await approve_permission(
                session,
                request_id=args.get("request_id"),
                approval_type=args.get("approval_type", "always"),
                expires_at=expires_at,
                count=args.get("count"),
            )

        if tool_name == "search_memory":
            from app.modules.memory_service import search_messages
            from app.database.models.business import Person
            from sqlalchemy import select as _sel
            person_name = args.get("person_name", "")
            sender_id = None
            if person_name:
                p = await session.scalar(_sel(Person).where(
                    Person.tenant_id == tenant_id,
                    Person.full_name.ilike(f"%{person_name}%"),
                ).limit(1))
                if p:
                    sender_id = p.telegram_id
            results = await search_messages(session, tenant_id,
                                             args.get("query", ""),
                                             user_telegram_id=sender_id)
            if not results:
                return "چیزی پیدا نشد."
            lines = [f"🔍 نتایج جستجو:"]
            for r in results[:10]:
                lines.append(f"[{r['date']}] {r['from']}: {r['content'][:100]}")
            return "\n".join(lines)

        if tool_name == "get_thread_summary":
            from app.modules.memory_service import get_thread_summary
            return await get_thread_summary(session, tenant_id, args.get("topic", ""))

        if tool_name == "search_files":
            from app.modules.memory_service import search_files
            from app.database.models.business import Person
            from sqlalchemy import select as _sel
            sender_id = None
            if args.get("sender_name"):
                p = await session.scalar(_sel(Person).where(
                    Person.tenant_id == tenant_id,
                    Person.full_name.ilike(f"%{args['sender_name']}%"),
                ).limit(1))
                if p:
                    sender_id = p.telegram_id
            ft = args.get("file_type", "any")
            results = await search_files(session, tenant_id,
                                          query=args.get("query"),
                                          sender_telegram_id=sender_id,
                                          file_type=None if ft == "any" else ft)
            if not results:
                return "فایلی پیدا نشد."
            lines = ["📎 فایل‌های یافت‌شده:"]
            for r in results:
                lines.append(f"[{r['id']}] {r['from']} — {r['file_type']} — {r['file_name'] or r['caption'] or '—'} — {r['date']}")
            lines.append("\nبرای ارسال مجدد: شناسه فایل رو بگو")
            return "\n".join(lines)

        if tool_name == "resend_file":
            from app.modules.memory_service import search_files
            from app.database.models.business import Person, FileRecord
            from sqlalchemy import select as _sel
            rec = await session.get(FileRecord, args.get("file_record_id"))
            if not rec or not rec.file_id:
                return "⚠️ فایل پیدا نشد یا قابل ارسال مجدد نیست."
            person = await session.scalar(_sel(Person).where(
                Person.tenant_id == tenant_id,
                Person.full_name.ilike(f"%{args.get('receiver_name', '')}%"),
                Person.telegram_id.isnot(None),
            ).limit(1))
            if not person:
                return f"⚠️ «{args.get('receiver_name')}» پیدا نشد یا وصل نیست."
            outbox.queue_message(user_id, {
                "type": "resend_file",
                "chat_id": person.telegram_id,
                "file_id": rec.file_id,
                "file_type": rec.file_type,
                "caption": args.get("caption") or rec.caption or "",
            })
            return f"✅ فایل برای «{person.full_name}» ارسال میشه."

        return f"⚠️ ابزار ناشناخته: {tool_name}"

    except TypeError as e:
        logger.error(f"[TOOL✗ TYPE] {tool_name} | {e}")
        return f"⚠️ خطا در پردازش پارامترها: {e}"
    except Exception as e:
        logger.error(f"[TOOL✗ ERR] {tool_name} | {type(e).__name__}: {e}")
        return f"⚠️ خطا در اجرا: {e}"


# ═══════════════════════════════════════
# اجرای فلوهای رویداد‌محور
# ═══════════════════════════════════════

async def _trigger_flows(session, tenant_id: int, event_type: str,
                          event_data: dict, owner_user_id: int):
    """
    وقتی یه رویداد اتفاق می‌افته، فلوهای مرتبط رو اجرا کن.
    event_type: invoice_confirmed / task_completed / payment_received / ...
    """
    import json as _json
    from app.database.models.business import WorkFlow, Person
    from sqlalchemy import select as _sel
    import logging as _log
    logger = _log.getLogger("moonax.flows")

    flows = (await session.scalars(
        _sel(WorkFlow).where(
            WorkFlow.tenant_id == tenant_id,
            WorkFlow.is_active == True,
        )
    )).all()

    for flow in flows:
        try:
            cond = _json.loads(flow.trigger_condition) if flow.trigger_condition else {}
            # چک کن این فلو برای این رویداد هست
            flow_event = cond.get("event", "")
            if flow_event != event_type:
                continue

            steps = _json.loads(flow.steps_json) if flow.steps_json else []
            logger.info(f"[FLOW→] {flow.name} | event={event_type}")

            for step in steps:
                action = step.get("action", "")
                target_role = step.get("target_role", "")
                message = step.get("message", "").format(**event_data)
                file_type = step.get("file_type", "")

                if action == "send_message":
                    # ارسال پیام به نقش مشخص
                    persons = (await session.scalars(
                        _sel(Person).where(
                            Person.tenant_id == tenant_id,
                            Person.role == target_role,
                            Person.telegram_id.isnot(None),
                        )
                    )).all()
                    for p in persons:
                        outbox.queue_message(owner_user_id, {
                            "chat_id": p.telegram_id,
                            "text": message,
                        })

                elif action == "send_file":
                    # ارسال فایل به نقش مشخص
                    persons = (await session.scalars(
                        _sel(Person).where(
                            Person.tenant_id == tenant_id,
                            Person.role == target_role,
                            Person.telegram_id.isnot(None),
                        )
                    )).all()
                    if file_type == "invoice" and event_data.get("invoice_id"):
                        try:
                            from app.modules.reports.invoice_excel import export_invoice_excel
                            buf, fname = await export_invoice_excel(
                                session, event_data["invoice_id"]
                            )
                            if buf:
                                for p in persons:
                                    import io as _io
                                    buf.seek(0)
                                    outbox.queue_message(owner_user_id, {
                                        "type": "document",
                                        "chat_id": p.telegram_id,
                                        "document_buf": _io.BytesIO(buf.read()),
                                        "filename": fname,
                                        "caption": message,
                                    })
                        except Exception as e:
                            logger.error(f"[FLOW send_file error] {e}")

                elif action == "notify_owner":
                    outbox.queue_message(owner_user_id, {
                        "chat_id": owner_user_id,
                        "text": message,
                    })

        except Exception as e:
            import logging as _log2
            _log2.getLogger("moonax.flows").error(f"[FLOW ERROR] {flow.name}: {e}")
