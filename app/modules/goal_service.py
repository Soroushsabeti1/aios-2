"""
Goal Engine — موتور مکالمه هدفمند.
تمام سناریوها: A1-A12, B1-B10, C1-C8, D1-D5, E1-E8, F1-F7
"""
import json
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.models.business import ActiveGoal, Person, PermissionRequest
from app.database.models.tenant import Tenant


# ═══════════════════════════════════════
# ساخت و مدیریت Goal
# ═══════════════════════════════════════

async def create_goal(session: AsyncSession, tenant_id: int,
                       owner_user_id: int, description: str,
                       steps: list, goal_type: str = "general",
                       context: dict = None,
                       escalation: list = None,
                       execute_at: datetime = None) -> ActiveGoal:
    """ساخت یه goal جدید در دیتابیس."""
    goal = ActiveGoal(
        tenant_id=tenant_id,
        owner_user_id=owner_user_id,
        description=description,
        goal_type=goal_type,
        steps_json=json.dumps(steps, ensure_ascii=False),
        waiting_for_json=json.dumps({}, ensure_ascii=False),
        results_json=json.dumps({}, ensure_ascii=False),
        context_json=json.dumps(context or {}, ensure_ascii=False),
        escalation_json=json.dumps(escalation or [], ensure_ascii=False),
        execute_at=execute_at,
        status="active",
    )
    session.add(goal)
    await session.commit()
    return goal


async def get_goal(session: AsyncSession, goal_id: int) -> ActiveGoal | None:
    return await session.get(ActiveGoal, goal_id)


async def find_goal_by_reply(session: AsyncSession, tenant_id: int,
                              telegram_id: int) -> ActiveGoal | None:
    """پیدا کردن goal که منتظر جواب این شخصه."""
    goals = (await session.scalars(
        select(ActiveGoal).where(
            ActiveGoal.tenant_id == tenant_id,
            ActiveGoal.status == "active",
        )
    )).all()

    str_tid = str(telegram_id)
    for goal in goals:
        waiting = json.loads(goal.waiting_for_json or "{}")
        if str_tid in waiting:
            return goal
    return None


async def record_reply(session: AsyncSession, goal: ActiveGoal,
                        telegram_id: int, reply_text: str):
    """ثبت جواب یه شخص در goal."""
    results = json.loads(goal.results_json or "{}")
    waiting = json.loads(goal.waiting_for_json or "{}")
    results[str(telegram_id)] = reply_text
    waiting.pop(str(telegram_id), None)
    goal.results_json = json.dumps(results, ensure_ascii=False)
    goal.waiting_for_json = json.dumps(waiting, ensure_ascii=False)
    goal.updated_at = datetime.now(timezone.utc)
    await session.commit()


async def add_waiting(session: AsyncSession, goal: ActiveGoal,
                       telegram_id: int, waiting_for: str):
    """اضافه کردن یه شخص به لیست انتظار."""
    waiting = json.loads(goal.waiting_for_json or "{}")
    waiting[str(telegram_id)] = waiting_for
    goal.waiting_for_json = json.dumps(waiting, ensure_ascii=False)
    await session.commit()


async def complete_goal(session: AsyncSession, goal: ActiveGoal):
    goal.status = "done"
    await session.commit()


def get_waiting(goal: ActiveGoal) -> dict:
    return json.loads(goal.waiting_for_json or "{}")


def get_results(goal: ActiveGoal) -> dict:
    return json.loads(goal.results_json or "{}")


def get_context(goal: ActiveGoal) -> dict:
    return json.loads(goal.context_json or "{}")


def get_steps(goal: ActiveGoal) -> list:
    return json.loads(goal.steps_json or "[]")


# ═══════════════════════════════════════
# پردازش مرحله بعدی goal
# ═══════════════════════════════════════

async def process_next_step(session, goal: ActiveGoal, reply_text: str,
                              replier_telegram_id: int, bot,
                              outbox_fn) -> str | None:
    """
    بعد از دریافت جواب، مرحله بعد رو اجرا کن.
    شامل: conditional, aggregate, escalation, timed
    """
    steps = get_steps(goal)
    context = get_context(goal)
    results = get_results(goal)
    waiting = get_waiting(goal)

    # پیدا کردن اسم شخص
    person = await session.scalar(
        select(Person).where(Person.telegram_id == replier_telegram_id)
    )
    person_name = person.full_name if person else str(replier_telegram_id)

    # پیدا کردن step مرتبط
    current_step = None
    for step in steps:
        if step.get("person_telegram_id") == replier_telegram_id:
            current_step = step
            break

    if not current_step:
        return None

    # ─── پردازش conditional step ───
    next_action = current_step.get("next_action", "")
    condition = current_step.get("condition", "")

    if condition:
        # ارزیابی شرط
        reply_lower = reply_text.lower()
        positive = any(w in reply_lower for w in ["آره", "بله", "اوکی", "ok", "موافقم", "باشه", "yes"])
        negative = any(w in reply_lower for w in ["نه", "نخیر", "نمیخوام", "no", "موافق نیستم"])

        if condition == "if_positive" and positive:
            action = current_step.get("action_if_positive", "")
            msg = current_step.get("message_if_positive", "")
        elif condition == "if_negative" and negative:
            action = current_step.get("action_if_negative", "")
            msg = current_step.get("message_if_negative", "")
        else:
            action = next_action
            msg = current_step.get("follow_up_message", "")

        if action == "ask_followup" and msg:
            await add_waiting(session, goal, replier_telegram_id, "follow_up")
            try:
                await bot.send_message(chat_id=replier_telegram_id, text=msg)
            except Exception:
                pass
            return f"✅ سوال بعدی از {person_name} پرسیده شد."

        elif action == "notify_owner":
            tenant = await session.get(Tenant, goal.tenant_id)
            if tenant:
                report_msg = msg.format(
                    person_name=person_name,
                    reply=reply_text,
                    **context
                )
                try:
                    await bot.send_message(chat_id=tenant.owner_telegram_id,
                                            text=report_msg)
                except Exception:
                    pass
            return None

        elif action == "escalate":
            return await _escalate(session, goal, bot, outbox_fn)

    # ─── چک اینکه همه جواب دادن ───
    if not waiting:
        return await _finalize_goal(session, goal, bot)

    return None


async def _finalize_goal(session, goal: ActiveGoal, bot) -> str:
    """وقتی همه جواب دادن، گزارش نهایی به کارفرما."""
    results = get_results(goal)
    context = get_context(goal)

    tenant = await session.get(Tenant, goal.tenant_id)
    if not tenant:
        return "خطا در یافتن tenant"

    # ساخت گزارش با اسامی واقعی
    lines = [f"📊 نتیجه «{goal.description}»:\n"]
    for tid_str, answer in results.items():
        person = await session.scalar(
            select(Person).where(Person.telegram_id == int(tid_str))
        )
        name = person.full_name if person else tid_str
        lines.append(f"• {name}: {answer}")

    # اگه aggregate لازمه (مثلاً بهترین ساعت مشترک)
    if goal.goal_type == "schedule_meeting":
        lines.append("\n🗓 پیشنهاد: بهترین ساعت مشترک رو انتخاب کن و بگو جلسه تنظیم بشه.")

    try:
        await bot.send_message(
            chat_id=tenant.owner_telegram_id,
            text="\n".join(lines)
        )
    except Exception:
        pass

    # اگه recurring باشه، دوباره راه‌اندازی کن
    ctx_data = json.loads(goal.context_json or "{}")
    if ctx_data.get("recurring"):
        await restart_recurring_goal(session, goal, bot)
    else:
        await complete_goal(session, goal)
    return "گزارش به کارفرما فرستاده شد."


async def _escalate(session, goal: ActiveGoal, bot, outbox_fn) -> str:
    """اجرای escalation chain."""
    escalation = json.loads(goal.escalation_json or "[]")
    if not escalation:
        return "escalation chain خالیه"

    next_person_id = escalation.pop(0)
    goal.escalation_json = json.dumps(escalation, ensure_ascii=False)
    await session.commit()

    person = await session.scalar(
        select(Person).where(Person.telegram_id == next_person_id))
    if person:
        await add_waiting(session, goal, next_person_id, "escalated_reply")
        try:
            await bot.send_message(
                chat_id=next_person_id,
                text=f"📢 موضوع «{goal.description}» نیاز به توجه شما داره."
            )
        except Exception:
            pass

    return "موضوع به سطح بالاتر ارجاع داده شد."


# ═══════════════════════════════════════
# Permission Engine
# ═══════════════════════════════════════

async def request_permission(session: AsyncSession, tenant_id: int,
                               requester_telegram_id: int,
                               requester_role: str,
                               resource_type: str, action: str,
                               resource_id: int = None) -> PermissionRequest:
    """ثبت درخواست دسترسی."""
    req = PermissionRequest(
        tenant_id=tenant_id,
        requester_telegram_id=requester_telegram_id,
        requester_role=requester_role,
        resource_type=resource_type,
        action=action,
        resource_id=resource_id,
        status="pending",
    )
    session.add(req)
    await session.commit()
    return req


async def check_permission_granted(session: AsyncSession, tenant_id: int,
                                     requester_telegram_id: int,
                                     resource_type: str, action: str) -> bool:
    """چک کردن دسترسی از PermissionRequest های تأییدشده."""
    now = datetime.now(timezone.utc)
    req = await session.scalar(
        select(PermissionRequest).where(
            PermissionRequest.tenant_id == tenant_id,
            PermissionRequest.requester_telegram_id == requester_telegram_id,
            PermissionRequest.resource_type == resource_type,
            PermissionRequest.action == action,
            PermissionRequest.status == "approved",
        ).order_by(PermissionRequest.id.desc()).limit(1)
    )
    if not req:
        return False
    if req.approval_type == "once":
        # فقط یه بار — بعد از استفاده غیرفعال بشه
        req.status = "used"
        await session.commit()
        return True
    if req.approval_type == "always":
        return True
    if req.approval_type == "until_date" and req.approval_expires_at:
        return req.approval_expires_at > now
    if req.approval_type == "count" and req.approval_count:
        if req.approval_count > 0:
            req.approval_count -= 1
            await session.commit()
            return True
        return False
    return True


async def approve_permission(session: AsyncSession, request_id: int,
                               approval_type: str = "always",
                               expires_at: datetime = None,
                               count: int = None) -> str:
    """تأیید درخواست دسترسی توسط کارفرما."""
    req = await session.get(PermissionRequest, request_id)
    if not req:
        return "⚠️ درخواست پیدا نشد."
    req.status = "approved"
    req.approval_type = approval_type
    req.approval_expires_at = expires_at
    req.approval_count = count
    await session.commit()
    return f"✅ دسترسی تأیید شد ({approval_type})."


# ═══════════════════════════════════════
# Timed Goal Executor (job)
# ═══════════════════════════════════════


async def execute_timed_goals(bot, session: AsyncSession):
    """اجرای goal های زمان‌بندی‌شده + timeout retry — هر ۵ دقیقه."""
    from datetime import timedelta
    now = datetime.now(timezone.utc)

    # اجرای goal های زمان‌دار
    due_goals = (await session.scalars(
        select(ActiveGoal).where(
            ActiveGoal.status == "active",
            ActiveGoal.execute_at.isnot(None),
            ActiveGoal.execute_at <= now,
        )
    )).all()

    for goal in due_goals:
        try:
            steps = get_steps(goal)
            for step in steps:
                tid = step.get("person_telegram_id")
                msg = step.get("message", "")
                if tid and msg:
                    await add_waiting(session, goal, tid, "timed_reply")
                    try:
                        await bot.send_message(chat_id=tid, text=msg)
                    except Exception:
                        pass
            goal.execute_at = None
            await session.commit()
        except Exception:
            pass

    # Timeout + Retry
    timeout_goals = (await session.scalars(
        select(ActiveGoal).where(
            ActiveGoal.status == "active",
        )
    )).all()

    for goal in timeout_goals:
        waiting = json.loads(goal.waiting_for_json or "{}")
        if not waiting:
            continue
        ctx = json.loads(goal.context_json or "{}")
        timeout_hours = int(ctx.get("timeout_hours", 24))
        updated = goal.updated_at
        if updated.tzinfo is None:
            updated = updated.replace(tzinfo=timezone.utc)
        if now - updated < timedelta(hours=timeout_hours):
            continue

        if goal.retry_count < goal.max_retries:
            goal.retry_count += 1
            goal.updated_at = now
            for tid_str in list(waiting.keys()):
                for step in get_steps(goal):
                    if str(step.get("person_telegram_id")) == tid_str:
                        retry_msg = step.get("retry_message") or step.get("message", "")
                        if retry_msg:
                            try:
                                await bot.send_message(chat_id=int(tid_str), text=retry_msg)
                            except Exception:
                                pass
            await session.commit()
        else:
            from app.database.models.tenant import Tenant
            tenant = await session.get(Tenant, goal.tenant_id)
            if tenant:
                names = []
                for tid_str in waiting.keys():
                    p = await session.scalar(
                        select(Person).where(Person.telegram_id == int(tid_str))
                    )
                    names.append(p.full_name if p else str(tid_str))
                names_str = ", ".join(names)
                report = (
                    "timeout — " + goal.description + " — "
                    + str(goal.max_retries) + " بار تلاش — بی‌جواب: " + names_str
                )
                try:
                    await bot.send_message(
                        chat_id=tenant.owner_telegram_id,
                        text=report
                    )
                except Exception:
                    pass
            goal.status = "timeout"
            await session.commit()


async def create_schedule_goal(session: AsyncSession, tenant_id: int,
                                 owner_user_id: int, persons: list,
                                 owner_free_slots: str,
                                 meeting_date: str = "فردا",
                                 topic: str = "جلسه خصوصی") -> ActiveGoal:
    """ساخت goal برای ست کردن جلسه با چند نفر."""
    steps = []
    for p in persons:
        steps.append({
            "person_telegram_id": p.telegram_id,
            "person_name": p.full_name,
            "message": (f"سلام {p.full_name}! {meeting_date} می‌خوام یه جلسه خصوصی باهات داشته باشم. "
                       f"من {owner_free_slots} آزادم. کدوم ساعت برات بهتره؟"),
            "waiting_for": "زمان مناسب",
        })
    return await create_goal(
        session, tenant_id, owner_user_id,
        description=f"{topic} — {meeting_date} — {owner_free_slots}",
        steps=steps,
        goal_type="schedule_meeting",
        context={"owner_free_slots": owner_free_slots, "date": meeting_date},
    )


async def create_collection_goal(session: AsyncSession, tenant_id: int,
                                    owner_user_id: int, persons: list,
                                    question: str, description: str) -> ActiveGoal:
    """ساخت goal برای جمع‌آوری اطلاعات از چند نفر."""
    steps = [{"person_telegram_id": p.telegram_id,
               "person_name": p.full_name,
               "message": question.replace("{name}", p.full_name)}
              for p in persons]
    return await create_goal(
        session, tenant_id, owner_user_id,
        description=description,
        steps=steps,
        goal_type="collect_info",
    )


async def create_approval_goal(session: AsyncSession, tenant_id: int,
                                 owner_user_id: int, target: Person,
                                 question: str, description: str,
                                 action_if_positive: str = "notify_owner",
                                 message_if_positive: str = "",
                                 action_if_negative: str = "notify_owner",
                                 message_if_negative: str = "") -> ActiveGoal:
    """ساخت goal برای گرفتن تأیید + اقدام بعدی."""
    steps = [{
        "person_telegram_id": target.telegram_id,
        "person_name": target.full_name,
        "message": question,
        "condition": "if_positive",
        "action_if_positive": action_if_positive,
        "message_if_positive": message_if_positive,
        "action_if_negative": action_if_negative,
        "message_if_negative": message_if_negative,
    }]
    return await create_goal(
        session, tenant_id, owner_user_id,
        description=description,
        steps=steps,
        goal_type="approval",
    )


# ═══════════════════════════════════════
# Permission Engine پیشرفته
# ═══════════════════════════════════════

async def check_advanced_permission(session: AsyncSession, tenant_id: int,
                                     requester_telegram_id: int,
                                     resource_type: str, action: str,
                                     amount: float = None,
                                     category: str = None,
                                     entity_id: int = None,
                                     task_id: int = None,
                                     project_id: int = None) -> tuple[bool, str]:
    """
    چک دسترسی پیشرفته با همه شرایط:
    threshold, category, time-of-day, entity, task, project
    Returns: (allowed, reason)
    """
    from datetime import datetime, timezone
    import json

    now = datetime.now(timezone.utc)
    current_hour = now.hour

    # دریافت همه permission های تأییدشده
    perms = (await session.scalars(
        select(PermissionRequest).where(
            PermissionRequest.tenant_id == tenant_id,
            PermissionRequest.requester_telegram_id == requester_telegram_id,
            PermissionRequest.resource_type == resource_type,
            PermissionRequest.action == action,
            PermissionRequest.status == "approved",
        )
    )).all()

    for perm in perms:
        meta = {}
        try:
            if hasattr(perm, 'meta_json') and perm.meta_json:
                meta = json.loads(perm.meta_json)
        except Exception:
            pass

        # چک entity خاص
        if entity_id and meta.get("entity_id") and meta["entity_id"] != entity_id:
            continue

        # چک task خاص
        if task_id and meta.get("task_id") and meta["task_id"] != task_id:
            continue

        # چک project خاص
        if project_id and meta.get("project_id") and meta["project_id"] != project_id:
            continue

        # چک threshold مبلغ
        if amount is not None and meta.get("max_amount"):
            if amount > float(meta["max_amount"]):
                return False, f"مبلغ {amount:,.0f} بالاتر از حد مجاز {meta['max_amount']:,.0f}ه"

        # چک category
        if category and meta.get("allowed_categories"):
            if category not in meta["allowed_categories"]:
                return False, f"دسته‌بندی «{category}» مجاز نیست"

        # چک time-of-day
        if meta.get("time_start") and meta.get("time_end"):
            t_start = int(meta["time_start"])
            t_end = int(meta["time_end"])
            if not (t_start <= current_hour <= t_end):
                return False, f"فقط بین ساعت {t_start} تا {t_end} مجازه"

        # چک انقضا
        if perm.approval_type == "until_date" and perm.approval_expires_at:
            exp = perm.approval_expires_at
            if exp.tzinfo is None:
                from datetime import timezone as _tz
                exp = exp.replace(tzinfo=_tz.utc)
            if exp < now:
                continue

        # چک تعداد
        if perm.approval_type == "count":
            if not perm.approval_count or perm.approval_count <= 0:
                continue
            perm.approval_count -= 1
            await session.commit()

        # همه شرایط OK
        return True, "مجاز"

    return False, "دسترسی ندارد"


async def create_advanced_permission(session: AsyncSession, tenant_id: int,
                                      requester_telegram_id: int, requester_role: str,
                                      resource_type: str, action: str,
                                      approval_type: str = "always",
                                      max_amount: float = None,
                                      allowed_categories: list = None,
                                      time_start: int = None,
                                      time_end: int = None,
                                      entity_id: int = None,
                                      task_id: int = None,
                                      project_id: int = None,
                                      expires_days: int = None) -> PermissionRequest:
    """ساخت permission پیشرفته با همه شرایط."""
    import json
    from datetime import timedelta

    meta = {}
    if max_amount: meta["max_amount"] = max_amount
    if allowed_categories: meta["allowed_categories"] = allowed_categories
    if time_start is not None: meta["time_start"] = time_start
    if time_end is not None: meta["time_end"] = time_end
    if entity_id: meta["entity_id"] = entity_id
    if task_id: meta["task_id"] = task_id
    if project_id: meta["project_id"] = project_id

    expires_at = None
    if expires_days:
        from datetime import timezone
        expires_at = datetime.now(timezone.utc) + timedelta(days=expires_days)

    req = PermissionRequest(
        tenant_id=tenant_id,
        requester_telegram_id=requester_telegram_id,
        requester_role=requester_role,
        resource_type=resource_type,
        action=action,
        status="approved",
        approval_type=approval_type,
        approval_expires_at=expires_at,
    )
    # meta_json در صورت وجود فیلد
    if hasattr(req, 'meta_json'):
        req.meta_json = json.dumps(meta, ensure_ascii=False)
    session.add(req)
    await session.commit()
    return req


async def get_hierarchical_approver(session: AsyncSession, tenant_id: int,
                                     person_telegram_id: int) -> "Person | None":
    """پیدا کردن سرپرست یه شخص برای hierarchical approval."""
    person = await session.scalar(
        select(Person).where(Person.telegram_id == person_telegram_id)
    )
    if not person:
        return None
    # پیدا کردن سرپرست (role بالاتر)
    role_hierarchy = ["customer", "collaborator", "employee", "owner"]
    current_idx = role_hierarchy.index(person.role) if person.role in role_hierarchy else 0
    if current_idx >= len(role_hierarchy) - 1:
        return None
    # پیدا کردن کسی با نقش بالاتر
    higher_role = role_hierarchy[current_idx + 1]
    return await session.scalar(
        select(Person).where(
            Person.tenant_id == tenant_id,
            Person.role == higher_role,
            Person.telegram_id.isnot(None),
        ).limit(1)
    )


async def send_autonomy_reminders(bot, session: AsyncSession):
    """یادآوری دوره‌ای به کارفرماها — دسترسی‌های فعال."""
    from app.database.models.business import TenantSettings
    from app.database.models.tenant import Tenant
    from datetime import timedelta
    import json

    tenants = (await session.scalars(
        select(Tenant).where(Tenant.is_active == True)
    )).all()

    for tenant in tenants:
        ts = await session.scalar(
            select(TenantSettings).where(TenantSettings.tenant_id == tenant.id)
        )
        if not ts or not ts.autonomy_rules:
            continue
        try:
            rules = json.loads(ts.autonomy_rules)
        except Exception:
            continue
        if not rules:
            continue
        # هر ۳۰ روز یادآوری
        last_reminder_key = "last_autonomy_reminder"
        docs = {}
        if ts.business_docs_json:
            try:
                docs = json.loads(ts.business_docs_json)
            except Exception:
                pass
        from datetime import timezone
        last = docs.get(last_reminder_key)
        now = datetime.now(timezone.utc)
        if last:
            last_dt = datetime.fromisoformat(last)
            if last_dt.tzinfo is None:
                last_dt = last_dt.replace(tzinfo=timezone.utc)
            if now - last_dt < timedelta(days=30):
                continue
        # ارسال یادآوری
        rule_names = list(rules.keys())
        msg = (
            "📋 یادآوری دوره‌ای دسترسی‌های فعال:\n\n"
            + "\n".join(f"• {r}" for r in rule_names[:5])
            + ("\n..." if len(rule_names) > 5 else "")
            + "\n\nمیخوای تغییری بدی؟ «لیست دسترسی‌ها» رو بنویس."
        )
        try:
            await bot.send_message(chat_id=tenant.owner_telegram_id, text=msg)
            docs[last_reminder_key] = now.isoformat()
            ts.business_docs_json = json.dumps(docs, ensure_ascii=False)
            await session.commit()
        except Exception:
            pass


async def create_recurring_goal(session: AsyncSession, tenant_id: int,
                                  owner_user_id: int, description: str,
                                  steps_template: list,
                                  repeat_interval_days: int = 7,
                                  context: dict = None) -> "ActiveGoal":
    """Goal تکراری — هر X روز دوباره اجرا میشه."""
    from datetime import timezone, timedelta
    ctx = context or {}
    ctx["recurring"] = True
    ctx["repeat_days"] = repeat_interval_days
    next_run = datetime.now(timezone.utc) + timedelta(days=repeat_interval_days)
    return await create_goal(
        session, tenant_id, owner_user_id,
        description=description,
        steps=steps_template,
        goal_type="recurring",
        context=ctx,
        execute_at=next_run,
    )


async def restart_recurring_goal(session: AsyncSession, goal: "ActiveGoal",
                                   bot) -> None:
    """بعد از تموم شدن goal تکراری، یه نسخه جدید میسازه."""
    from datetime import timezone, timedelta
    ctx = json.loads(goal.context_json or "{}")
    if not ctx.get("recurring"):
        return
    repeat_days = int(ctx.get("repeat_days", 7))
    next_run = datetime.now(timezone.utc) + timedelta(days=repeat_days)
    # reset goal
    goal.status = "active"
    goal.waiting_for_json = json.dumps({})
    goal.results_json = json.dumps({})
    goal.retry_count = 0
    goal.execute_at = next_run
    goal.updated_at = datetime.now(timezone.utc)
    await session.commit()


async def detect_stacked_owner_messages(session: AsyncSession, tenant_id: int,
                                          owner_telegram_id: int,
                                          messages: list[str]) -> list[dict]:
    """
    وقتی کارفرما چند پیام تلمبار فرستاده — تشخیص بده کدوم جواب برای کدومه.
    Returns: list of {message, likely_goal_id, confidence}
    """
    goals = (await session.scalars(
        select(ActiveGoal).where(
            ActiveGoal.tenant_id == tenant_id,
            ActiveGoal.status == "active",
        )
    )).all()

    results = []
    for msg in messages:
        msg_lower = msg.lower()
        best_match = None
        best_score = 0

        for goal in goals:
            desc = goal.description.lower()
            ctx = json.loads(goal.context_json or "{}")
            # امتیاز شباهت ساده
            score = 0
            for word in msg_lower.split():
                if word in desc:
                    score += 2
                for ctx_val in str(ctx).lower().split():
                    if word in ctx_val:
                        score += 1

            if score > best_score:
                best_score = score
                best_match = goal

        results.append({
            "message": msg,
            "likely_goal_id": best_match.id if best_match and best_score > 2 else None,
            "goal_description": best_match.description if best_match and best_score > 2 else "عمومی",
            "confidence": min(best_score * 10, 100),
        })

    return results


# ═══════════════════════════════════════
# AI Autonomy Levels
# ═══════════════════════════════════════

AI_AUTONOMY_LEVELS = {
    "full": "همه کارها رو بدون پرسیدن انجام بده",
    "notify": "انجام بده ولی خبر بده",
    "confirm": "قبل از انجام تأیید بگیر",
    "manual": "هرگز خودکار انجام نده",
}


async def get_ai_autonomy_level(session: AsyncSession, tenant_id: int,
                                 action_type: str) -> str:
    """سطح خودمختاری AI برای یه نوع اقدام."""
    from app.database.models.business import TenantSettings
    ts = await session.scalar(
        select(TenantSettings).where(TenantSettings.tenant_id == tenant_id)
    )
    if not ts or not ts.autonomy_rules:
        return "confirm"
    try:
        rules = json.loads(ts.autonomy_rules)
        return rules.get(action_type, {}).get("level", "confirm")
    except Exception:
        return "confirm"


async def set_ai_autonomy_level(session: AsyncSession, tenant_id: int,
                                  action_type: str, level: str) -> str:
    """تنظیم سطح خودمختاری."""
    from app.database.models.business import TenantSettings
    if level not in AI_AUTONOMY_LEVELS:
        return f"⚠️ سطح نامعتبر. انتخاب کن: {', '.join(AI_AUTONOMY_LEVELS.keys())}"
    ts = await session.scalar(
        select(TenantSettings).where(TenantSettings.tenant_id == tenant_id)
    )
    if not ts:
        return "⚠️ تنظیمات پیدا نشد."
    rules = {}
    if ts.autonomy_rules:
        try:
            rules = json.loads(ts.autonomy_rules)
        except Exception:
            pass
    rules[action_type] = {"level": level, "description": AI_AUTONOMY_LEVELS[level]}
    ts.autonomy_rules = json.dumps(rules, ensure_ascii=False)
    await session.commit()
    return f"✅ سطح دسترسی برای «{action_type}» به «{AI_AUTONOMY_LEVELS[level]}» تغییر کرد."


# ═══════════════════════════════════════
# Escalation by Amount
# ═══════════════════════════════════════

async def check_amount_escalation(session: AsyncSession, tenant_id: int,
                                   amount: float, action_type: str,
                                   owner_telegram_id: int,
                                   bot, description: str = "") -> tuple[bool, str]:
    """
    اگه مبلغ از حد مجاز بیشتر بود، به کارفرما escalate کن.
    Returns: (needs_approval, message)
    """
    from app.database.models.business import TenantSettings
    ts = await session.scalar(
        select(TenantSettings).where(TenantSettings.tenant_id == tenant_id)
    )
    thresholds = {}
    if ts and ts.autonomy_rules:
        try:
            rules = json.loads(ts.autonomy_rules)
            thresholds = rules.get("amount_thresholds", {})
        except Exception:
            pass

    threshold = thresholds.get(action_type, 0)
    if threshold and amount > threshold:
        msg = (
            "مبلغ " + str(int(amount)) + " تومان بالاتر از حد مجازه. تأیید می‌کنی؟"
        )
        try:
            await bot.send_message(chat_id=owner_telegram_id, text=msg)
        except Exception:
            pass
        return True, "منتظر تأیید کارفرما"
    return False, "مجاز"


# ═══════════════════════════════════════
# Goal Branching با نقش جدید
# ═══════════════════════════════════════

async def branch_to_new_role(session: AsyncSession, goal: "ActiveGoal",
                               new_role: str, message: str,
                               bot, owner_user_id: int):
    """وارد کردن نقش جدید در مکالمه بر اساس جواب."""
    persons = await get_persons_by_role(session, goal.tenant_id, new_role)
    if not persons:
        return
    for person in persons:
        await add_waiting(session, goal, person.telegram_id, f"branch_{new_role}")
        try:
            await bot.send_message(chat_id=person.telegram_id, text=message)
        except Exception:
            pass
    steps = get_steps(goal)
    steps.append({
        "person_telegram_id": persons[0].telegram_id,
        "person_name": persons[0].full_name,
        "message": message,
        "role": new_role,
        "is_branch": True,
    })
    goal.steps_json = json.dumps(steps, ensure_ascii=False)
    await session.commit()
