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
    انتخاب هوشمند tools بر اساس نقش و کانتکست.
    کارفرما همیشه tools کامل دارد.
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

    # همیشه موجود
    always = {
        "update_tenant_info", "get_tenant_info", "backup_data", "voice_reply",
        "smart_search", "check_alerts", "add_reminder", "list_reminders",
        "complete_reminder", "delete_reminder", "get_report", "set_voice",
        "send_message_to_owner", "send_direct_message", "send_broadcast",
        "send_file_to_person", "send_photo_to_person",
        "create_employee_invite_link", "create_customer_invite_link",
        "create_collaborator_invite_link", "list_invite_links",
        "revoke_invite_link", "revoke_all_invite_links",
        "disconnect_person", "list_persons",
    }

    # بر اساس کانتکست
    ctx_tools = set()

    if any(w in ctx for w in ["کارمند","حقوق","فیش","پرسنل","استخدام","اصلاح","تغییر","ویرایش"]):
        ctx_tools |= {"add_employee","list_employees","update_employee","delete_employee",
                      "get_employee_detail","search_employees","employee_statistics",
                      "add_salary_payment","list_salary_payments","generate_settlement"}

    if any(w in ctx for w in ["مشتری","خریدار","مشتریان"]):
        ctx_tools |= {"add_customer","list_customers","update_customer","delete_customer",
                      "get_customer_detail","search_customers","customer_statistics",
                      "top_customers","customer_purchase_history"}

    if any(w in ctx for w in ["فاکتور","قسط","پرداخت","صورتحساب","سفارش"]):
        ctx_tools |= {"create_invoice","confirm_invoice","cancel_invoice","list_invoices",
                      "get_invoice_detail","export_invoice_excel","export_invoice_pdf",
                      "add_installment","list_installments","pay_installment","overdue_installments"}

    if any(w in ctx for w in ["محصول","کالا","انبار","موجودی"]):
        ctx_tools |= {"add_product","list_products","update_product","delete_product","inventory_report"}

    if any(w in ctx for w in ["هزینه","خرج"]):
        ctx_tools |= {"add_expense","delete_expense","debtors_report"}

    if any(w in ctx for w in ["پروژه","تسک","وظیفه","کار"]):
        ctx_tools |= {"create_project","get_project_info","add_project_document","list_projects",
                      "add_task","move_task","list_tasks","project_report","end_of_day_report"}

    if any(w in ctx for w in ["مالی","سود","زیان","درآمد","گزارش"]):
        ctx_tools |= {"monthly_profit_loss","cashflow_report","monthly_comparison",
                      "top_selling_products","financial_summary","sales_report","financial_report"}

    if any(w in ctx for w in ["پوستر","طراحی","عکس","بنر","گرافیک","تصویر"]):
        ctx_tools |= {"generate_poster","generate_slide_post","generate_catalog",
                      "crop_image","save_design_template","save_brand_config","get_brand_config",
                      "save_entity_photo","get_entity_photo"}

    if any(w in ctx for w in ["فلو","جریان","قانون","خودکار","اتوماتیک"]):
        ctx_tools |= {"create_workflow","list_workflows","delete_workflow","export_workflows_excel"}

    if any(w in ctx for w in ["دسترسی","اختیار","مجوز","سطح"]):
        ctx_tools |= {"grant_permission","list_permissions","revoke_permission","export_permissions_excel"}

    if any(w in ctx for w in ["اطلاعیه","نظرسنجی","اعلام","همه"]):
        ctx_tools |= {"send_announcement","create_poll","send_checklist"}

    if any(w in ctx for w in ["اکسل","خروجی","دانلود","گزارش"]):
        ctx_tools |= {"export_excel","get_excel_template","batch_export"}

    if any(w in ctx for w in ["حذف","حساب","اکانت","بکاپ"]):
        ctx_tools |= {"request_account_deletion","backup_data"}

    # اگه کانتکست خالی → همه tools پرکاربرد
    if not ctx_tools:
        ctx_tools = {
            "add_customer","list_customers","add_employee","list_employees",
            "create_invoice","list_invoices","add_product","list_products",
            "monthly_profit_loss","send_announcement","add_expense",
            "add_reminder","list_reminders",
        }

    # ترکیب و محدود کردن
    final_names = always | ctx_tools
    result = [tool_map[n] for n in final_names if n in tool_map]

    if len(result) > 64:
        # اولویت: always اول
        always_list = [tool_map[n] for n in always if n in tool_map]
        ctx_list = [tool_map[n] for n in ctx_tools if n in tool_map and n not in always]
        result = (always_list + ctx_list)[:64]

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
