"""
ابزارسازی ادمین — ساخت tool جدید از چت.
"""
import json
import os
from datetime import datetime, timezone

CUSTOM_TOOLS_FILE = "/app/data/custom_tools.json"


def load_custom_tools() -> list:
    """بارگذاری tool های سفارشی از فایل."""
    try:
        if os.path.exists(CUSTOM_TOOLS_FILE):
            with open(CUSTOM_TOOLS_FILE) as f:
                return json.load(f)
    except Exception:
        pass
    return []


def save_custom_tool(tool_def: dict, handler_code: str) -> str:
    """ذخیره tool جدید."""
    tools = load_custom_tools()
    tool_name = tool_def.get("function", {}).get("name", "")
    if not tool_name:
        return "⚠️ نام tool مشخص نیست."
    # حذف tool قبلی با همین نام
    tools = [t for t in tools if t.get("tool", {}).get("function", {}).get("name") != tool_name]
    tools.append({
        "tool": tool_def,
        "handler": handler_code,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    os.makedirs(os.path.dirname(CUSTOM_TOOLS_FILE), exist_ok=True)
    with open(CUSTOM_TOOLS_FILE, "w") as f:
        json.dump(tools, f, ensure_ascii=False, indent=2)
    return f"✅ Tool «{tool_name}» ذخیره شد."


def get_custom_tool_definitions() -> list:
    """دریافت tool definitions برای ارسال به AI."""
    return [item["tool"] for item in load_custom_tools()]


async def execute_custom_tool(tool_name: str, args: dict,
                               session, tenant_id: int, user_id: int) -> str:
    """اجرای tool سفارشی."""
    tools = load_custom_tools()
    for item in tools:
        if item["tool"].get("function", {}).get("name") == tool_name:
            handler = item.get("handler", "")
            if not handler:
                return f"⚠️ handler برای {tool_name} تعریف نشده."
            try:
                local_vars = {
                    "args": args,
                    "session": session,
                    "tenant_id": tenant_id,
                    "user_id": user_id,
                    "result": "",
                }
                exec(handler, {}, local_vars)
                return str(local_vars.get("result", "✅ اجرا شد."))
            except Exception as e:
                return f"⚠️ خطا در اجرا: {e}"
    return f"⚠️ tool «{tool_name}» پیدا نشد."
