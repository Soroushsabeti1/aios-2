"""
موتور AI — لایه‌ی واسط با OpenRouter — نسخه ۴.

این لایه عمداً جدا و قابل‌تعویض است: برای عوض کردن مدل
فقط کافی است OPENROUTER_MODEL در .env تغییر کند.

نسخه ۴: پشتیبانی از نقش — لحن و ابزارهای مجاز بر اساس نقش کاربر.
"""
import json
import httpx
from app.core.config import settings
from app.ai.prompts import get_system_prompt
from app.ai.tools import TOOLS
from app.modules import roles


def _tools_for_role(role: str, context_text: str = "") -> list:
    """
    ابزارهای مجاز — بدون تکراری، حداکثر ۶۴.
    اولویت‌بندی بر اساس کلمات کلیدی پیام کاربر.
    """
    allowed = roles.get_allowed_tools(role)
    if not allowed:
        return []

    # dedup
    tool_map = {}
    for t in TOOLS:
        name = t.get("function", {}).get("name", "")
        if name in allowed:
            tool_map[name] = t

    all_tools = list(tool_map.values())
    if len(all_tools) <= 64:
        return all_tools

    ctx = context_text.lower()

    # همیشه اضافه میشن
    always = ["update_tenant_info","get_tenant_info","request_trial","get_subscription_status",
              "backup_data","voice_reply","smart_search","check_alerts","save_entity_photo",
              "add_reminder","list_reminders","complete_reminder","delete_reminder",
              "get_report","sales_report","financial_report",]

    # بر اساس کانتکست
    context_tools = []
    if any(w in ctx for w in ["کارمند","حقوق","فیش","پرسنل","استخدام"]):
        context_tools += ["add_employee","list_employees","update_employee","delete_employee",
                         "get_employee_detail","search_employees","employee_statistics",
                         "add_salary_payment","list_salary_payments","generate_settlement",
                         "export_work_log","get_work_log_template","batch_export"]
    if any(w in ctx for w in ["مشتری","خریدار","مشتریان"]):
        context_tools += ["add_customer","list_customers","update_customer","delete_customer",
                         "get_customer_detail","search_customers","customer_statistics",
                         "top_customers","customer_purchase_history"]
    if any(w in ctx for w in ["فاکتور","قسط","پرداخت","صورتحساب"]):
        context_tools += ["create_invoice","confirm_invoice","cancel_invoice","list_invoices",
                         "get_invoice_detail","export_invoice_excel","export_invoice_pdf",
                         "add_installment","list_installments","pay_installment","overdue_installments"]
    if any(w in ctx for w in ["محصول","کالا","انبار","موجودی"]):
        context_tools += ["add_product","list_products","update_product","delete_product","inventory_report"]
    if any(w in ctx for w in ["هزینه","خرج","هزینه‌ها"]):
        context_tools += ["add_expense","delete_expense","debtors_report"]
    if any(w in ctx for w in ["پروژه","تسک","وظیفه"]):
        context_tools += ["create_project","get_project_info","add_project_document","list_projects",
                         "add_task","move_task","list_tasks","project_report","end_of_day_report"]
    if any(w in ctx for w in ["مالی","سود","زیان","درآمد","گزارش مالی"]):
        context_tools += ["monthly_profit_loss","cashflow_report","monthly_comparison",
                         "top_selling_products","financial_summary"]
    if any(w in ctx for w in ["پوستر","طراحی","عکس","بنر","کاتالوگ"]):
        context_tools += ["generate_poster","generate_slide_post","generate_catalog",
                         "crop_image","save_design_template","batch_design","save_brand_config","get_brand_config"]
    if any(w in ctx for w in ["لینک","دعوت"]):
        context_tools += ["create_employee_invite_link","create_customer_invite_link",
                         "create_collaborator_invite_link","list_invite_links",
                         "revoke_invite_link","revoke_all_invite_links"]
    if any(w in ctx for w in ["فلو","دسترسی","اختیار","مجوز"]):
        context_tools += ["create_workflow","list_workflows","delete_workflow","export_workflows_excel",
                         "grant_permission","list_permissions","revoke_permission","export_permissions_excel"]
    if any(w in ctx for w in ["پیام","اطلاعیه","نظرسنجی","بفرست","اعلام"]):
        context_tools += ["send_announcement","create_poll","send_checklist",
                         "send_broadcast","send_direct_message","view_messages","send_photo_to_person"]
    if any(w in ctx for w in ["اکسل","خروجی","گزارش","دانلود"]):
        context_tools += ["export_excel","get_excel_template","export_invoice_excel",
                         "export_invoice_pdf","export_work_log","export_workflows_excel",
                         "export_permissions_excel","batch_export"]

    # اگه کانتکست خالی بود — همه دسته‌ها
    if not context_tools:
        context_tools = list(tool_map.keys())

    # ساخت نتیجه
    seen = set()
    result = []
    for name in always + context_tools:
        if name and name not in seen and name in tool_map:
            seen.add(name)
            result.append(tool_map[name])
        if len(result) >= 64:
            break

    return result


class AIEngine:
    def __init__(self):
        self.api_key = settings.openrouter_api_key
        self.model = settings.openrouter_model
        self.base_url = settings.openrouter_base_url

    async def chat(self, messages: list[dict], use_tools: bool = True,
                   role: str = "owner", person_role: str = None,
                   tenant_settings: dict = None) -> dict:
        """
        یک درخواست به مدل می‌فرستد.
        """
        system_content = get_system_prompt(
            person_role=person_role,
            settings=tenant_settings or {},
        )
        system_content += "\n\n" + roles.get_role_tone(role)

        full_messages = [{"role": "system", "content": system_content}] + messages

        payload = {
            "model": self.model,
            "messages": full_messages,
        }

        if use_tools:
            # آخرین پیام کاربر رو برای انتخاب هوشمند tools استفاده کن
            last_user_text = ""
            for msg in reversed(messages):
                if msg.get("role") == "user":
                    content_val = msg.get("content", "")
                    if isinstance(content_val, str):
                        last_user_text = content_val
                    elif isinstance(content_val, list):
                        for part in content_val:
                            if isinstance(part, dict) and part.get("type") == "text":
                                last_user_text = part.get("text", "")
                                break
                    break
            role_tools = _tools_for_role(role, last_user_text)
            if role_tools:
                payload["tools"] = role_tools
                payload["tool_choice"] = "auto"

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/ai-business-os",
            "X-Title": "AI Business OS",
        }

        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
            )
            if resp.status_code != 200:
                import logging
                logging.getLogger(__name__).error(
                    "OpenRouter error %s: %s", resp.status_code, resp.text[:500]
                )
            resp.raise_for_status()
            data = resp.json()

        return data["choices"][0]["message"]

    @staticmethod
    def parse_tool_calls(message: dict) -> list[dict]:
        """فراخوانی‌های tool را از پیام مدل استخراج می‌کند."""
        calls = []
        for tc in message.get("tool_calls") or []:
            fn = tc.get("function", {})
            try:
                args = json.loads(fn.get("arguments", "{}"))
            except json.JSONDecodeError:
                args = {}
            calls.append({
                "id": tc.get("id"),
                "name": fn.get("name"),
                "arguments": args,
            })
        return calls


ai_engine = AIEngine()
