"""
فلوهای ساختاریافته — onboarding, sales funnel, support, approval chain.
"""
from sqlalchemy.ext.asyncio import AsyncSession
from app.modules.goal_service import create_goal, add_waiting, get_persons_by_role


# ═══════════════════════════════════════
# ۱. Onboarding کارمند جدید
# ═══════════════════════════════════════

async def start_employee_onboarding(session: AsyncSession, tenant_id: int,
                                     owner_user_id: int, person,
                                     bot) -> str:
    """شروع فلوی آشنایی با کارمند جدید."""
    steps = [
        {
            "person_telegram_id": person.telegram_id,
            "person_name": person.full_name,
            "message": (
                f"سلام {person.full_name}! به تیم خوش اومدی 🎉\n\n"
                "چند سوال کوتاه دارم تا بهتر بشناختمت:\n"
                "۱. تجربه کاری قبلیت چی بوده؟\n"
                "۲. در چه ساعاتی بیشتر در دسترسی؟\n"
                "۳. چه ابزارهایی بلدی؟"
            ),
            "waiting_for": "onboarding_intro",
        }
    ]
    goal = await create_goal(
        session, tenant_id, owner_user_id,
        description=f"onboarding {person.full_name}",
        steps=steps,
        goal_type="onboarding",
        context={"person_id": person.id, "phase": "intro"},
    )
    await add_waiting(session, goal, person.telegram_id, "intro")
    try:
        await bot.send_message(chat_id=person.telegram_id, text=steps[0]["message"])
    except Exception:
        pass
    return f"✅ فلوی onboarding برای {person.full_name} شروع شد."


# ═══════════════════════════════════════
# ۲. Sales Funnel
# ═══════════════════════════════════════

async def start_sales_funnel(session: AsyncSession, tenant_id: int,
                               owner_user_id: int, customer,
                               product_name: str, bot) -> str:
    """شروع فلوی فروش — از علاقه تا پرداخت."""
    steps = [
        {
            "person_telegram_id": customer.telegram_id,
            "person_name": customer.full_name,
            "message": (
                f"سلام {customer.full_name}! "
                f"شنیدم به {product_name} علاقه‌مندی. "
                "می‌خوای اطلاعات بیشتری بهت بدم؟"
            ),
            "condition": "if_positive",
            "action_if_positive": "ask_followup",
            "message_if_positive": (
                f"عالیه! {product_name} چند مدل داره. "
                "کدوم بیشتر به دردت می‌خوره — "
                "استفاده شخصی یا تجاری؟"
            ),
            "action_if_negative": "notify_owner",
            "message_if_negative": f"{customer.full_name} علاقه‌ای به {product_name} نداشت.",
            "waiting_for": "sales_interest",
        }
    ]
    goal = await create_goal(
        session, tenant_id, owner_user_id,
        description=f"sales funnel — {customer.full_name} — {product_name}",
        steps=steps,
        goal_type="sales_funnel",
        context={"product_name": product_name, "customer_id": customer.id, "phase": "interest"},
    )
    await add_waiting(session, goal, customer.telegram_id, "interest")
    try:
        await bot.send_message(chat_id=customer.telegram_id, text=steps[0]["message"])
    except Exception:
        pass
    # trigger ساخت فاکتور خودکار بعد از تأیید
    import json as _j
    ctx = _j.loads(goal.context_json or "{}")
    ctx["auto_invoice_on_confirm"] = True
    ctx["auto_invoice_product"] = product_name
    goal.context_json = _j.dumps(ctx, ensure_ascii=False)
    await session.commit()

    return f"✅ فلوی فروش برای {customer.full_name} شروع شد."


# ═══════════════════════════════════════
# ۳. Support Escalation
# ═══════════════════════════════════════

async def start_support_flow(session: AsyncSession, tenant_id: int,
                               owner_user_id: int, customer,
                               issue: str, bot,
                               support_person=None) -> str:
    """شروع فلوی پشتیبانی — از سوال تا حل مشکل."""
    escalation_chain = []
    if support_person and support_person.telegram_id:
        escalation_chain.append(support_person.telegram_id)
    escalation_chain.append(owner_user_id)

    steps = [
        {
            "person_telegram_id": customer.telegram_id,
            "person_name": customer.full_name,
            "message": (
                f"سلام {customer.full_name}! "
                "مشکلت رو دریافت کردم. "
                "چند سوال بپرسم تا بهتر کمک کنم:\n"
                f"مشکل: {issue}\n"
                "این مشکل از کِی شروع شده؟"
            ),
            "waiting_for": "support_details",
            "condition": "if_positive",
            "action_if_positive": "ask_followup",
            "message_if_positive": "ممنون. قبلاً این مشکل پیش اومده؟",
            "action_if_negative": "escalate",
        }
    ]
    goal = await create_goal(
        session, tenant_id, owner_user_id,
        description=f"support — {customer.full_name} — {issue[:50]}",
        steps=steps,
        goal_type="support",
        context={"issue": issue, "customer_id": customer.id},
        escalation=escalation_chain,
        context_hours_timeout=2,
    )
    await add_waiting(session, goal, customer.telegram_id, "support_details")
    try:
        await bot.send_message(chat_id=customer.telegram_id, text=steps[0]["message"])
    except Exception:
        pass
    # اگه ۲ ساعت جواب نداد، escalate به support_person سپس owner
    import json as _j
    ctx2 = _j.loads(goal.context_json or "{}")
    ctx2["timeout_hours"] = 2
    goal.context_json = _j.dumps(ctx2, ensure_ascii=False)
    await session.commit()

    return f"✅ فلوی پشتیبانی برای {customer.full_name} شروع شد."


# ═══════════════════════════════════════
# ۴. Approval Chain
# ═══════════════════════════════════════

async def start_approval_chain(session: AsyncSession, tenant_id: int,
                                 owner_user_id: int, approvers: list,
                                 subject: str, description: str,
                                 bot) -> str:
    """
    زنجیره تأیید — هر نفر تأیید کرد، بعدی می‌رود.
    approvers: لیست Person که باید تأیید کنن
    """
    if not approvers:
        return "⚠️ هیچ تأییدکننده‌ای مشخص نشده."

    first = approvers[0]
    rest_ids = [p.telegram_id for p in approvers[1:]]

    steps = [
        {
            "person_telegram_id": first.telegram_id,
            "person_name": first.full_name,
            "message": (
                f"درخواست تأیید: {subject}\n\n"
                f"{description}\n\n"
                "تأیید می‌کنی؟"
            ),
            "condition": "if_positive",
            "action_if_positive": "ask_followup" if rest_ids else "notify_owner",
            "message_if_positive": (
                f"✅ {first.full_name} تأیید کرد."
                + (f" در انتظار تأیید بعدی..." if rest_ids else " همه تأیید کردن!")
            ),
            "action_if_negative": "notify_owner",
            "message_if_negative": f"❌ {first.full_name} رد کرد: {subject}",
            "waiting_for": "approval",
        }
    ]

    goal = await create_goal(
        session, tenant_id, owner_user_id,
        description=f"approval chain — {subject}",
        steps=steps,
        goal_type="approval_chain",
        context={
            "subject": subject,
            "remaining_approvers": rest_ids,
            "approved_by": [],
        },
        escalation=[],
    )
    await add_waiting(session, goal, first.telegram_id, "approval")
    try:
        await bot.send_message(chat_id=first.telegram_id, text=steps[0]["message"])
    except Exception:
        pass
    return f"✅ زنجیره تأیید شروع شد — {len(approvers)} نفر باید تأیید کنن."
