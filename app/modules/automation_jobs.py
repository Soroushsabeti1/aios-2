"""
سرویس جاب‌های خودکار — فاز E.

جاب‌ها:
  - scrum_master_job: پیگیری تسک‌ها هر ۴ ساعت
  - workflow_executor_job: اجرای فلوهای خودکار هر ۱۵ دقیقه
  - birthday_job: تبریک تولد روزانه
  - contract_expiry_job: هشدار پایان قرارداد روزانه
  - installment_overdue_job: هشدار اقساط سررسید روزانه
  - end_of_day_job: گزارش پایان روز (۱۸ ایران)
  - weekly_incomplete_job: یادآور اطلاعات ناقص هفتگی
"""
import json
import logging
from datetime import datetime, timezone, timedelta, date

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════
# Scrum Master — پیگیری تسک‌ها
# ═══════════════════════════════════════

async def scrum_master_job(context):
    """هر ۴ ساعت — پیگیری تسک‌های در حال انجام."""
    from app.database.base import AsyncSessionLocal
    from app.database.models.business import ProjectTask, Person, Project
    from sqlalchemy import select

    async with AsyncSessionLocal() as session:
        now = datetime.now(timezone.utc)

        # تسک‌های در حال انجام
        tasks = (await session.scalars(
            select(ProjectTask).where(
                ProjectTask.list_type == "doing",
            )
        )).all()

        for task in tasks:
            if not task.assignee_id:
                continue

            person = await session.get(Person, task.assignee_id)
            if not person or not person.telegram_id:
                continue

            # چک ددلاین
            if task.deadline:
                deadline = task.deadline
                if deadline.tzinfo is None:
                    deadline = deadline.replace(tzinfo=timezone.utc)
                hours_left = (deadline - now).total_seconds() / 3600

                if hours_left < 0:
                    # ددلاین گذشته
                    if not task.deadline_violation:
                        task.deadline_violation = True
                        await session.commit()
                        try:
                            await context.bot.send_message(
                                chat_id=person.telegram_id,
                                text=f"⚠️ ددلاین تسک «{task.title}» گذشته. وضعیتش چیه؟"
                            )
                        except Exception:
                            pass
                        # به کارفرما خبر بده
                        await _notify_owner(context, session, task.tenant_id,
                                             f"⚠️ ددلاین تسک «{task.title}» ({person.full_name}) گذشت.")
                elif hours_left < 24:
                    # کمتر از ۲۴ ساعت مونده
                    try:
                        await context.bot.send_message(
                            chat_id=person.telegram_id,
                            text=f"⏰ ددلاین «{task.title}» کمتر از {int(hours_left)} ساعت دیگه‌ست. به موقع می‌رسی؟"
                        )
                    except Exception:
                        pass

            # پیگیری عادی — هر ۴ ساعت
            try:
                msg = f"سلام! وضعیت تسک «{task.title}» چطوره؟"
                if task.require_photo_report:
                    msg += " گزارش تصویری هم بفرست."
                await context.bot.send_message(
                    chat_id=person.telegram_id,
                    text=msg
                )
            except Exception:
                pass


# ═══════════════════════════════════════
# اجرای فلوهای خودکار
# ═══════════════════════════════════════

async def workflow_executor_job(context):
    """هر ۱۵ دقیقه — اجرای فلوهای زمان‌بندی‌شده."""
    from app.database.base import AsyncSessionLocal
    from app.database.models.business import WorkFlow
    from sqlalchemy import select

    async with AsyncSessionLocal() as session:
        flows = (await session.scalars(
            select(WorkFlow).where(
                WorkFlow.is_active == True,
                WorkFlow.trigger_type == "schedule",
            )
        )).all()

        now = datetime.now(timezone.utc)
        for flow in flows:
            try:
                cond = json.loads(flow.trigger_condition) if flow.trigger_condition else {}
                steps = json.loads(flow.steps_json) if flow.steps_json else []

                # چک زمان اجرا
                interval_minutes = cond.get("interval_minutes", 60)
                last_run_str = cond.get("last_run")
                if last_run_str:
                    last_run = datetime.fromisoformat(last_run_str)
                    if last_run.tzinfo is None:
                        last_run = last_run.replace(tzinfo=timezone.utc)
                    if (now - last_run).total_seconds() < interval_minutes * 60:
                        continue

                # اجرای مراحل
                for step in steps:
                    await _execute_flow_step(context, session, flow.tenant_id, step)

                # بروزرسانی زمان آخرین اجرا
                cond["last_run"] = now.isoformat()
                flow.trigger_condition = json.dumps(cond, ensure_ascii=False)
                await session.commit()

            except Exception as e:
                logger.error(f"workflow_executor: flow {flow.id}: {e}")


async def _execute_flow_step(context, session, tenant_id: int, step: dict):
    """اجرای یک مرحله از فلو."""
    action = step.get("action", "")
    message = step.get("message", "")
    target = step.get("target", "")

    if action == "notify_owner":
        await _notify_owner(context, session, tenant_id, message)
    elif action == "send_message":
        # ارسال به نقش خاص
        from app.database.models.business import Person
        from sqlalchemy import select
        persons = (await session.scalars(
            select(Person).where(
                Person.tenant_id == tenant_id,
                Person.role == target,
                Person.telegram_id.isnot(None),
            )
        )).all()
        for p in persons:
            try:
                await context.bot.send_message(chat_id=p.telegram_id, text=message)
            except Exception:
                pass


# ═══════════════════════════════════════
# تبریک تولد
# ═══════════════════════════════════════

async def birthday_job(context):
    """روزانه — تبریک تولد کارمندان و مشتریان."""
    from app.database.base import AsyncSessionLocal
    from app.database.models.business import Employee, Customer
    from app.database.models.tenant import Tenant
    from sqlalchemy import select

    today = date.today()

    async with AsyncSessionLocal() as session:
        tenants = (await session.scalars(select(Tenant).where(Tenant.is_active == True))).all()

        for tenant in tenants:
            # کارمندان
            emps = (await session.scalars(
                select(Employee).where(Employee.tenant_id == tenant.id)
            )).all()
            for emp in emps:
                if emp.birth_date and emp.birth_date.month == today.month and emp.birth_date.day == today.day:
                    # به کارفرما خبر بده
                    try:
                        await context.bot.send_message(
                            chat_id=tenant.owner_telegram_id,
                            text=f"🎂 امروز تولد {emp.name} هست!"
                        )
                    except Exception:
                        pass
                    # اگه تلگرام کارمند داره
                    if emp.telegram_id:
                        try:
                            await context.bot.send_message(
                                chat_id=int(emp.telegram_id),
                                text=f"🎂 تولدت مبارک {emp.name}! امیدوارم سال خوبی داشته باشی 😊"
                            )
                        except Exception:
                            pass

            # مشتریان
            custs = (await session.scalars(
                select(Customer).where(
                    Customer.tenant_id == tenant.id,
                    Customer.telegram_id.isnot(None),
                )
            )).all()
            for cust in custs:
                if cust.birth_date and cust.birth_date.month == today.month and cust.birth_date.day == today.day:
                    try:
                        await context.bot.send_message(
                            chat_id=int(cust.telegram_id),
                            text=f"🎂 تولدت مبارک {cust.name}! ممنون که همراه ما هستی 😊"
                        )
                    except Exception:
                        pass


# ═══════════════════════════════════════
# هشدار پایان قرارداد
# ═══════════════════════════════════════

async def contract_expiry_job(context):
    """روزانه — هشدار پایان قرارداد کارمندان."""
    from app.database.base import AsyncSessionLocal
    from app.database.models.business import Employee
    from app.database.models.tenant import Tenant
    from sqlalchemy import select

    today = date.today()
    warning_days = [30, 14, 7, 3, 1]

    async with AsyncSessionLocal() as session:
        tenants = (await session.scalars(select(Tenant).where(Tenant.is_active == True))).all()

        for tenant in tenants:
            emps = (await session.scalars(
                select(Employee).where(
                    Employee.tenant_id == tenant.id,
                    Employee.contract_end.isnot(None),
                )
            )).all()

            for emp in emps:
                if not emp.contract_end:
                    continue
                days_left = (emp.contract_end - today).days
                if days_left in warning_days:
                    try:
                        await context.bot.send_message(
                            chat_id=tenant.owner_telegram_id,
                            text=f"⚠️ قرارداد {emp.name} {days_left} روز دیگه تموم میشه ({emp.contract_end})"
                        )
                    except Exception:
                        pass


# ═══════════════════════════════════════
# هشدار اقساط سررسید
# ═══════════════════════════════════════

        # trigger flows برای contract_expiring
        try:
            from app.ai.dispatcher import _trigger_flows
            tenants_ids = set()
            async with AsyncSessionLocal() as s3:
                from app.database.models.business import Employee
                from sqlalchemy import select as _s3
                emps = (await s3.scalars(_s3(Employee))).all()
                tenants_ids = set(e.tenant_id for e in emps)
            for tid in tenants_ids:
                async with AsyncSessionLocal() as s4:
                    await _trigger_flows(s4, tid, "contract_expiring", {}, 0)
        except Exception:
            pass


async def installment_overdue_job(context):
    """روزانه — هشدار اقساط سررسید گذشته."""
    from app.database.base import AsyncSessionLocal
    from app.database.models.business import Installment, Invoice, Customer
    from app.database.models.tenant import Tenant
    from sqlalchemy import select
    from app.utils.normalizer import format_amount

    today = date.today()

    async with AsyncSessionLocal() as session:
        tenants = (await session.scalars(select(Tenant).where(Tenant.is_active == True))).all()

        for tenant in tenants:
            # اقساط سررسید گذشته
            overdue = (await session.scalars(
                select(Installment).where(
                    Installment.tenant_id == tenant.id,
                    Installment.due_date < today,
                    Installment.status == "پرداخت نشده",
                )
            )).all()

            if not overdue:
                continue

            total = sum(float(i.amount) for i in overdue)
            msg = (f"🔴 {len(overdue)} قسط سررسید گذشته — "
                   f"مجموع: {format_amount(int(total))} تومان\n"
                   f"برای جزئیات بگو «اقساط سررسید»")
            try:
                await context.bot.send_message(
                    chat_id=tenant.owner_telegram_id,
                    text=msg
                )
            except Exception:
                pass

            # یادآوری به مشتریان بدهکار
            for inst in overdue:
                try:
                    inv = await session.get(Invoice, inst.invoice_id)
                    if not inv:
                        continue
                    cust = await session.get(Customer, inv.customer_id) if inv.customer_id else None
                    if cust and cust.telegram_id:
                        await context.bot.send_message(
                            chat_id=int(cust.telegram_id),
                            text=f"یادآوری: قسط شماره {inst.installment_number} فاکتور {inv.display_id} "
                                 f"به مبلغ {format_amount(int(inst.amount))} تومان سررسیدش گذشته. "
                                 f"لطفاً پیگیری کنید."
                        )
                except Exception:
                    pass


# ═══════════════════════════════════════
# گزارش پایان روز
# ═══════════════════════════════════════

async def end_of_day_job(context):
    """روزانه ۱۸ ایران — گزارش پایان روز + بهره‌وری + درخواست گزارش از کارمندان."""
    from app.database.base import AsyncSessionLocal
    from app.database.models.business import Person, DailyReport, ProjectTask
    from app.database.models.tenant import Tenant
    from app.modules import daily_report_service
    from sqlalchemy import select, func
    from datetime import date

    async with AsyncSessionLocal() as session:
        tenants = (await session.scalars(select(Tenant).where(Tenant.is_active == True))).all()

        for tenant in tenants:
            employees = (await session.scalars(
                select(Person).where(
                    Person.tenant_id == tenant.id,
                    Person.role == "employee",
                    Person.telegram_id.isnot(None),
                )
            )).all()

            for emp in employees:
                try:
                    await context.bot.send_message(
                        chat_id=emp.telegram_id,
                        text=(
                            "گزارش امروزت رو بفرست:\n"
                            "• ورود و خروج چه ساعتی؟\n"
                            "• چقدر استراحت داشتی؟\n"
                            "• چی انجام دادی؟\n"
                            "• مانعی داشتی؟"
                        )
                    )
                except Exception:
                    pass

            # گزارش بهره‌وری تیم
            today = date.today()
            prod_lines = []
            for emp in employees:
                from app.modules.employees.service import get_employee_by_person
                emp_rec = await session.scalar(
                    select(__import__('app.database.models.business', fromlist=['Employee']).Employee).where(
                        __import__('app.database.models.business', fromlist=['Employee']).Employee.tenant_id == tenant.id,
                        __import__('app.database.models.business', fromlist=['Employee']).Employee.telegram_id == emp.telegram_id,
                    ).limit(1)
                )
                report = await session.scalar(
                    select(DailyReport).where(
                        DailyReport.tenant_id == tenant.id,
                        DailyReport.report_date == today,
                    ).order_by(DailyReport.id.desc()).limit(1)
                )
                if report and report.productivity_score:
                    score = report.productivity_score
                    em = "🟢" if score >= 80 else ("🟡" if score >= 60 else "🔴")
                    prod_lines.append(f"{em} {emp.full_name}: {score:.0f}٪")

            # گزارش کلی به کارفرما
            msg, _ = await daily_report_service.end_of_day_report(session, tenant.id)
            full_msg = f"📊 گزارش پایان روز:\n\n{msg}"
            if prod_lines:
                full_msg += "\n\n📈 بهره‌وری:\n" + "\n".join(prod_lines)

            try:
                await context.bot.send_message(
                    chat_id=tenant.owner_telegram_id,
                    text=full_msg
                )
            except Exception:
                pass


# ═══════════════════════════════════════
# یادآور هفتگی اطلاعات ناقص
# ═══════════════════════════════════════

async def weekly_incomplete_job(context):
    """هفتگی — یادآور اطلاعات ناقص و مستندات تکمیلی."""
    from app.database.base import AsyncSessionLocal
    from app.database.models.business import TenantSettings, Employee
    from app.database.models.tenant import Tenant
    from sqlalchemy import select

    async with AsyncSessionLocal() as session:
        tenants = (await session.scalars(select(Tenant).where(Tenant.is_active == True))).all()

        for tenant in tenants:
            ts = await session.scalar(
                select(TenantSettings).where(TenantSettings.tenant_id == tenant.id)
            )

            msgs = []

            # اطلاعات کسب‌وکار
            if not ts or not ts.business_description:
                msgs.append("• توضیحات کسب‌وکارت رو هنوز ثبت نکردی")

            # مستندات تکمیلی
            if ts and ts.business_description and (not ts.business_docs_json):
                msgs.append("• می‌تونی اسناد تکمیلی (PDF یا متن) برای معرفی بهتر مجموعه بفرستی")

            # کارمندان با اطلاعات ناقص
            emps = (await session.scalars(
                select(Employee).where(Employee.tenant_id == tenant.id)
            )).all()
            incomplete_emps = [e for e in emps if not e.national_id or not e.phone]
            if incomplete_emps:
                msgs.append(f"• {len(incomplete_emps)} کارمند اطلاعات ناقص دارن")

            if msgs:
                try:
                    await context.bot.send_message(
                        chat_id=tenant.owner_telegram_id,
                        text="📝 یادآور هفتگی:\n\n" + "\n".join(msgs) +
                             "\n\nهر چی کامل‌تر باشه بهتر می‌تونم کمکت کنم."
                    )
                except Exception:
                    pass


# ═══════════════════════════════════════
# Helper
# ═══════════════════════════════════════

async def timed_goals_job(context):
    """هر ۵ دقیقه — اجرای goal های زمان‌بندی‌شده."""
    from app.database.base import AsyncSessionLocal
    from app.modules.goal_service import execute_timed_goals
    async with AsyncSessionLocal() as session:
        await execute_timed_goals(context.bot, session)
    """ارسال پیام به کارفرما."""
    from app.database.models.tenant import Tenant
    tenant = await session.get(Tenant, tenant_id)
    if tenant:
        try:
            await context.bot.send_message(
                chat_id=tenant.owner_telegram_id,
                text=message
            )
        except Exception:
            pass


async def autonomy_reminder_job(context):
    """ماهانه — یادآوری دسترسی‌های فعال به کارفرما."""
    from app.database.base import AsyncSessionLocal
    from app.modules.goal_service import send_autonomy_reminders
    async with AsyncSessionLocal() as session:
        await send_autonomy_reminders(context.bot, session)
