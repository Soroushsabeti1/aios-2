"""سرویس پروژه و تسک — ترلوی چتی با Scrum Master."""
import json
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.models.business import Project, ProjectTask
from app.utils.id_generator import generate_display_id

LIST_TYPES = {
    "backlog": "همه کارها",
    "this_week": "این هفته",
    "next": "بعدی",
    "doing": "در حال انجام",
    "review": "در انتظار تکمیل",
    "approved": "تأیید شده",
}

PRIORITY_ICONS = {"urgent": "🔴", "high": "🟡", "normal": "🟢", "low": "⚪"}


async def create_project(session: AsyncSession, tenant_id: int,
                          name: str, description: str = None) -> str:
    did = await generate_display_id(session, tenant_id, "projects", Project)
    project = Project(tenant_id=tenant_id, display_id=did,
                      name=name, description=description)
    session.add(project)
    await session.commit()
    return f"✅ پروژه «{name}» ساخته شد ({did})"


async def list_projects(session: AsyncSession, tenant_id: int) -> str:
    projects = (await session.scalars(
        select(Project).where(Project.tenant_id == tenant_id)
        .order_by(Project.created_at.desc())
    )).all()
    if not projects:
        return "هنوز پروژه‌ای نداری."
    lines = ["📁 پروژه‌ها:"]
    icons = {"active": "🟢", "completed": "✅", "archived": "📦"}
    for p in projects:
        lines.append(f"{icons.get(p.status,'⚪')} [{p.display_id}] {p.name}")
    return "\n".join(lines)


async def get_project_info(session: AsyncSession, tenant_id: int, name: str) -> str:
    proj = await session.scalar(
        select(Project).where(Project.tenant_id == tenant_id,
                               Project.name.ilike(f"%{name}%")).limit(1)
    )
    if not proj:
        return f"⚠️ پروژه «{name}» پیدا نشد."
    lines = [f"📁 {proj.name} [{proj.display_id}] — {proj.status}"]
    if proj.description:
        lines.append(proj.description)
    # تعداد تسک‌ها
    tasks = (await session.scalars(
        select(ProjectTask).where(ProjectTask.project_id == proj.id)
    )).all()
    if tasks:
        doing = sum(1 for t in tasks if t.list_type == "doing")
        approved = sum(1 for t in tasks if t.list_type == "approved")
        lines.append(f"تسک‌ها: {len(tasks)} کل | {doing} در حال انجام | {approved} تأیید شده")
    if proj.documents_json:
        try:
            docs = json.loads(proj.documents_json)
            lines.append(f"مستندات: {len(docs)} سند")
        except Exception:
            pass
    return "\n".join(lines)


async def add_project_document(session: AsyncSession, tenant_id: int,
                                 name: str, document_text: str) -> str:
    proj = await session.scalar(
        select(Project).where(Project.tenant_id == tenant_id,
                               Project.name.ilike(f"%{name}%")).limit(1)
    )
    if not proj:
        return f"⚠️ پروژه «{name}» پیدا نشد."
    docs = []
    if proj.documents_json:
        try:
            docs = json.loads(proj.documents_json)
        except Exception:
            pass
    docs.append({"text": document_text, "date": datetime.now(timezone.utc).isoformat()})
    proj.documents_json = json.dumps(docs, ensure_ascii=False)
    await session.commit()
    return f"✅ مستند به «{proj.name}» اضافه شد. (مجموع: {len(docs)})"


async def add_task(session: AsyncSession, tenant_id: int,
                    project_name: str, title: str,
                    description: str = None, task_type: str = None,
                    priority: str = "normal", assignee_id: int = None,
                    estimated_hours: float = None, deadline_str: str = None,
                    require_photo_report: bool = False,
                    follow_up_hours: int = 4) -> str:
    proj = await session.scalar(
        select(Project).where(Project.tenant_id == tenant_id,
                               Project.name.ilike(f"%{project_name}%")).limit(1)
    )
    if not proj:
        return f"⚠️ پروژه «{project_name}» پیدا نشد."

    deadline = None
    if deadline_str:
        try:
            from app.utils.jalali import parse_jalali
            deadline_date = parse_jalali(deadline_str)
            deadline = datetime.combine(deadline_date, datetime.min.time()).replace(tzinfo=timezone.utc)
        except Exception:
            pass

    task = ProjectTask(
        tenant_id=tenant_id, project_id=proj.id,
        title=title, description=description, task_type=task_type,
        list_type="backlog", priority=priority,
        assignee_id=assignee_id, estimated_hours=estimated_hours,
        deadline=deadline, require_photo_report=require_photo_report,
        follow_up_hours=follow_up_hours,
    )
    session.add(task)
    await session.commit()

    icon = PRIORITY_ICONS.get(priority, "🟢")
    return (f"✅ تسک «{title}» اضافه شد {icon}\n"
            f"پروژه: {proj.name}\n"
            + (f"مجری: باید اساین بشه\n" if not assignee_id else "")
            + (f"تخمین: {estimated_hours} ساعت\n" if estimated_hours else "")
            + (f"ددلاین: {deadline_str}\n" if deadline_str else ""))


async def move_task(session: AsyncSession, tenant_id: int,
                     task_id: int, new_list: str) -> str:
    task = await session.get(ProjectTask, task_id)
    if not task or task.tenant_id != tenant_id:
        return "⚠️ تسک پیدا نشد."
    old_list = task.list_type
    task.list_type = new_list

    # ثبت در تاریخچه
    history = []
    if task.history_json:
        try:
            history = json.loads(task.history_json)
        except Exception:
            pass
    history.append({
        "action": "move",
        "from": old_list, "to": new_list,
        "time": datetime.now(timezone.utc).isoformat(),
    })
    task.history_json = json.dumps(history, ensure_ascii=False)

    # زمان شروع
    if new_list == "doing" and not task.start_time:
        task.start_time = datetime.now(timezone.utc)
    if new_list == "approved":
        task.end_time = datetime.now(timezone.utc)
        if task.start_time:
            diff = (task.end_time - task.start_time).total_seconds() / 3600
            task.actual_hours = round(diff, 2)

    await session.commit()
    return f"✅ تسک «{task.title}» به «{LIST_TYPES.get(new_list, new_list)}» منتقل شد."


async def list_tasks(session: AsyncSession, tenant_id: int,
                      project_name: str = None,
                      list_type: str = None,
                      assignee_id: int = None) -> str:
    q = select(ProjectTask).where(ProjectTask.tenant_id == tenant_id)
    if project_name:
        proj = await session.scalar(
            select(Project).where(Project.tenant_id == tenant_id,
                                   Project.name.ilike(f"%{project_name}%")).limit(1)
        )
        if proj:
            q = q.where(ProjectTask.project_id == proj.id)
    if list_type:
        q = q.where(ProjectTask.list_type == list_type)
    if assignee_id:
        q = q.where(ProjectTask.assignee_id == assignee_id)

    tasks = (await session.scalars(q.order_by(ProjectTask.created_at.desc()).limit(30))).all()
    if not tasks:
        return "تسکی پیدا نشد."

    lines = [f"📋 تسک‌ها ({LIST_TYPES.get(list_type,'همه')}):"]
    for t in tasks:
        icon = PRIORITY_ICONS.get(t.priority, "🟢")
        dd = ""
        if t.deadline:
            from app.utils.jalali import to_jalali_str
            dd = f" | ددلاین: {to_jalali_str(t.deadline.date())}"
        lines.append(f"{icon} [{t.id}] {t.title}{dd}")
    return "\n".join(lines)


async def project_report(session: AsyncSession, tenant_id: int) -> str:
    """گزارش لحظه‌ای همه پروژه‌ها."""
    projects = (await session.scalars(
        select(Project).where(Project.tenant_id == tenant_id,
                               Project.status == "active")
    )).all()
    if not projects:
        return "پروژه فعالی نداری."

    now = datetime.now(timezone.utc)
    lines = [f"📊 گزارش لحظه‌ای پروژه‌ها — {now.strftime('%H:%M')}:"]

    for proj in projects:
        tasks = (await session.scalars(
            select(ProjectTask).where(ProjectTask.project_id == proj.id)
        )).all()
        if not tasks:
            continue

        doing = [t for t in tasks if t.list_type == "doing"]
        review = [t for t in tasks if t.list_type == "review"]
        approved = [t for t in tasks if t.list_type == "approved"]

        # ددلاین‌های نزدیک
        overdue = [t for t in tasks
                   if t.deadline and t.deadline < now
                   and t.list_type not in ("approved",)]

        lines.append(f"\n📁 {proj.name}:")
        lines.append(f"⚙️ در حال انجام: {len(doing)} | ⏳ انتظار تکمیل: {len(review)} | ✅ تأیید: {len(approved)}")
        if overdue:
            lines.append(f"⚠️ تأخیر: {len(overdue)} تسک")
            for t in overdue[:3]:
                lines.append(f"  • {t.title}")

    return "\n".join(lines)
