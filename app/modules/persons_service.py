"""
سرویس مدیریت اشخاص و لینک‌های دعوت — نسخه ۳.

لینک کارمند:
  - نوع ۱ (خودثبتی): کارمند اطلاعاتش رو خودش پر می‌کنه
  - نوع ۲ (کارفرما ثبت): کارفرما اطلاعات رو پر کرده
  - هر دو رمزدار: یوزر=کد ملی، پسورد=شماره تماس
  - شرط: کارمند باید حداقل اسم+کد ملی+شماره تماس داشته باشه

لینک مشتری و همکار:
  - آشنا یا ناآشنا
  - بدون رمز
  - شرط: اطلاعات کسب‌وکار کامل باشه
"""
import hashlib
import secrets
from datetime import datetime, timezone, timedelta
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.models.business import Person, InviteLink, PersonCredential
from app.modules import roles
from app.utils.normalizer import format_amount


def _gen_token() -> str:
    return secrets.token_urlsafe(16)


def _hash_password(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()


async def _gen_person_display_id(session: AsyncSession, tenant_id: int) -> str:
    count = await session.scalar(
        select(func.count(Person.id)).where(Person.tenant_id == tenant_id)
    ) or 0
    return f"PER-{count + 1:04d}"


# ─────────────────────────────────────────────
# مدیریت اشخاص
# ─────────────────────────────────────────────

async def add_person(session: AsyncSession, tenant_id: int,
                      full_name: str, role: str,
                      phone: str = None, note: str = None) -> str:
    if role not in roles.INVITABLE_ROLES:
        return f"⚠️ نقش «{role}» معتبر نیست."

    did = await _gen_person_display_id(session, tenant_id)
    person = Person(
        tenant_id=tenant_id, display_id=did, role=role,
        full_name=full_name, phone=phone, note=note,
    )
    session.add(person)
    await session.commit()

    role_fa = roles.ROLE_LABELS.get(role, role)
    return (f"✅ {role_fa} «{full_name}» ثبت شد ({did})\n"
            f"برای وصل کردن به ربات: لینک دعوت برای {full_name} بساز")


async def list_persons(session: AsyncSession, tenant_id: int,
                       role: str = None) -> str:
    q = select(Person).where(Person.tenant_id == tenant_id, Person.is_active == True)
    if role:
        q = q.where(Person.role == role)
    q = q.order_by(Person.id.asc())
    persons = (await session.scalars(q)).all()

    if not persons:
        return "هنوز شخصی ثبت نشده."

    lines = ["👥 اشخاص:"]
    for p in persons:
        role_fa = roles.ROLE_LABELS.get(p.role, p.role)
        status = "🟢 متصل" if p.is_connected else "⚪ متصل‌نشده"
        lines.append(f"• [{p.display_id}] {p.full_name} — {role_fa} — {status}")
    return "\n".join(lines)


async def get_person_by_telegram(session: AsyncSession,
                                  telegram_id: int) -> Person | None:
    return await session.scalar(
        select(Person).where(
            Person.telegram_id == telegram_id,
            Person.is_active == True,
        )
    )


async def delete_person(session: AsyncSession, tenant_id: int,
                        display_id: str) -> str:
    raw = display_id.upper().replace("PER-", "").strip()
    person = await session.scalar(
        select(Person).where(
            Person.tenant_id == tenant_id,
            Person.display_id == display_id.upper() if "PER-" in display_id.upper() else True,
        )
    )
    if not person:
        try:
            pid = int(raw)
            person = await session.scalar(
                select(Person).where(
                    Person.tenant_id == tenant_id,
                    Person.id == pid,
                )
            )
        except ValueError:
            pass
    if not person:
        return f"⚠️ شخص پیدا نشد."
    person.is_active = False
    await session.commit()
    return f"🗑 «{person.full_name}» حذف شد."


# ─────────────────────────────────────────────
# لینک دعوت کارمند
# ─────────────────────────────────────────────

async def create_employee_invite_link(
    session: AsyncSession, tenant_id: int, bot_username: str,
    person_name: str, link_type: str = "self",  # self / prefilled
    password: str = None,
    expires_hours: int = 24 * 7,
    max_uses: int = 1,
) -> str:
    """
    ساخت لینک دعوت رمزدار کارمند.
    link_type:
      self     = خودثبتی (کارمند اطلاعاتش رو پر می‌کنه)
      prefilled = کارفرما اطلاعات رو پر کرده
    """
    # پیدا کردن کارمند
    from app.database.models.business import Employee
    emp = await session.scalar(
        select(Employee).where(
            Employee.tenant_id == tenant_id,
            Employee.name.ilike(f"%{person_name}%"),
        ).limit(1)
    )
    if not emp:
        return (f"⚠️ کارمندی با نام «{person_name}» پیدا نشد.\n"
                f"اول اطلاعاتش رو ثبت کن: اسم، کد ملی، شماره تماس حداقل لازمه.")

    # چک کردن اطلاعات ضروری
    missing = []
    if not emp.national_id:
        missing.append("کد ملی")
    if not emp.phone:
        missing.append("شماره تماس")
    if missing:
        return (f"⚠️ اطلاعات ضروری {emp.name} ناقصه: {', '.join(missing)}\n"
                f"اول این‌ها رو کامل کن بعد لینک می‌سازم.")

    # چک اگه قبلاً وصل شده
    existing_person = await session.scalar(
        select(Person).where(
            Person.tenant_id == tenant_id,
            Person.linked_employee_id == emp.id,
            Person.is_connected == True,
        )
    )
    if existing_person:
        return f"⚠️ {emp.name} قبلاً به ربات وصله."

    # پسورد پیش‌فرض = شماره تماس
    if not password:
        password = emp.phone

    # ساخت یا پیدا کردن Person متناظر
    person = await session.scalar(
        select(Person).where(
            Person.tenant_id == tenant_id,
            Person.linked_employee_id == emp.id,
        )
    )
    if not person:
        did = await _gen_person_display_id(session, tenant_id)
        person = Person(
            tenant_id=tenant_id, display_id=did,
            role=roles.ROLE_EMPLOYEE,
            full_name=emp.name, phone=emp.phone,
            linked_employee_id=emp.id,
        )
        session.add(person)
        await session.flush()

    expires_at = datetime.now(timezone.utc) + timedelta(hours=expires_hours)
    token = _gen_token()

    link_label = f"{'خودثبتی' if link_type == 'self' else 'کارفرما-ثبت'} — {emp.name}"
    invite = InviteLink(
        tenant_id=tenant_id, token=token, role=roles.ROLE_EMPLOYEE,
        label=link_label,
        lock_to_person_id=person.id,
        expires_at=expires_at,
        password=_hash_password(password),
        max_uses=max_uses,
    )
    # ذخیره link_type در label
    invite.label = f"{link_type}|{link_label}"
    session.add(invite)
    await session.commit()

    link_url = f"https://t.me/{bot_username}?start=inv_{token}"

    info = (f"🔗 لینک دعوت کارمند آماده شد:\n"
            f"👤 {emp.name}\n"
            f"🔑 نام کاربری: کد ملی ({emp.national_id})\n"
            f"🔑 گذرواژه اولیه: شماره تماس\n"
            f"📋 نوع: {'خودثبتی' if link_type == 'self' else 'اطلاعات توسط کارفرما'}\n"
            f"⏳ انقضا: ۷ روز")

    forward_msg = (f"سلام {emp.name}!\n"
                   f"برای دسترسی به سیستم روی لینک زیر بزن:\n\n"
                   f"[عضویت در تیم]({link_url})\n\n"
                   f"⚠️ نام کاربری‌ات مخصوص این مجموعه‌ست و به تلگرامت ربطی نداره.")

    # دو پیام جدا با SPLIT_MSG
    return f"{info}||SPLIT_MSG||{forward_msg}"


# ─────────────────────────────────────────────
# لینک دعوت مشتری
# ─────────────────────────────────────────────

async def create_customer_invite_link(
    session: AsyncSession, tenant_id: int, bot_username: str,
    acquaintance_type: str = "new",  # known / new
    person_name: str = None,
    person_phone: str = None,
    max_uses: int = None,
    expires_hours: int = None,
) -> str:
    """
    ساخت لینک مشتری.
    acquaintance_type: known=آشنا، new=ناآشنا
    """
    from app.database.models.business import TenantSettings
    from app.database.models.tenant import Tenant

    # چک اطلاعات کسب‌وکار
    tenant = await session.get(Tenant, tenant_id)
    ts = await session.scalar(
        select(TenantSettings).where(TenantSettings.tenant_id == tenant_id)
    )
    if not ts or not ts.business_description:
        return ("⚠️ قبل از ساخت لینک مشتری، توضیحات کسب‌وکارت رو کامل کن.\n"
                "بگو: «توضیحات کسب‌وکارم رو ثبت کن» و توضیح بده.")

    biz_name = tenant.name if tenant else "مجموعه"

    lock_person = None
    if person_name and acquaintance_type == "known":
        # پیدا کردن یا ساختن Person
        person = await session.scalar(
            select(Person).where(
                Person.tenant_id == tenant_id,
                Person.full_name.ilike(f"%{person_name}%"),
                Person.role == roles.ROLE_CUSTOMER,
            ).limit(1)
        )
        if not person:
            did = await _gen_person_display_id(session, tenant_id)
            person = Person(
                tenant_id=tenant_id, display_id=did,
                role=roles.ROLE_CUSTOMER,
                full_name=person_name, phone=person_phone,
            )
            session.add(person)
            await session.flush()
        lock_person = person

    expires_at = None
    if expires_hours:
        expires_at = datetime.now(timezone.utc) + timedelta(hours=expires_hours)

    token = _gen_token()
    biz_desc_short = (ts.business_description or "")[:200]

    invite = InviteLink(
        tenant_id=tenant_id, token=token, role=roles.ROLE_CUSTOMER,
        label=f"{'آشنا' if acquaintance_type == 'known' else 'ناآشنا'}|{person_name or 'عمومی'}",
        lock_to_person_id=lock_person.id if lock_person else None,
        expires_at=expires_at,
        max_uses=max_uses,
    )
    session.add(invite)
    await session.commit()

    link_url = f"https://t.me/{bot_username}?start=inv_{token}"

    if acquaintance_type == "known":
        msg = (f"سلام! 😊 من دستیار {biz_name} هستم، گفتن بیام پیشت که راحت‌تر باهم در ارتباط باشیم.\n\n"
               f"[ارتباط با ما]({link_url})")
    else:
        msg = (f"سلام! 😊 من دستیار {biz_name} هستم. {biz_desc_short}\n"
               f"هر وقت سوال یا کاری داشتی اینجام.\n\n"
               f"[ارتباط با ما]({link_url})")

    info = (f"🔗 لینک مشتری ساخته شد:\n"
            f"نوع: {'آشنا' if acquaintance_type == 'known' else 'ناآشنا'}\n"
            + (f"برای: {person_name}\n" if person_name else "")
            + (f"لیمیت: {max_uses} نفر\n" if max_uses else "نامحدود\n")
            + (f"انقضا: {expires_hours} ساعت\n" if expires_hours else "بدون انقضا\n"))

    return f"{info}\n\n---\n{msg}"


# ─────────────────────────────────────────────
# لینک دعوت همکار
# ─────────────────────────────────────────────

async def create_collaborator_invite_link(
    session: AsyncSession, tenant_id: int, bot_username: str,
    acquaintance_type: str = "new",
    person_name: str = None,
    max_uses: int = None,
    expires_hours: int = None,
) -> str:
    from app.database.models.business import TenantSettings
    from app.database.models.tenant import Tenant

    tenant = await session.get(Tenant, tenant_id)
    ts = await session.scalar(
        select(TenantSettings).where(TenantSettings.tenant_id == tenant_id)
    )
    if not ts or not ts.business_description:
        return ("⚠️ قبل از ساخت لینک همکار، توضیحات کسب‌وکارت رو کامل کن.")

    biz_name = tenant.name if tenant else "مجموعه"
    biz_desc_short = (ts.business_description or "")[:200]

    lock_person = None
    if person_name and acquaintance_type == "known":
        person = await session.scalar(
            select(Person).where(
                Person.tenant_id == tenant_id,
                Person.full_name.ilike(f"%{person_name}%"),
                Person.role.in_([roles.ROLE_COLLABORATOR, roles.ROLE_PARTNER]),
            ).limit(1)
        )
        if not person:
            did = await _gen_person_display_id(session, tenant_id)
            person = Person(
                tenant_id=tenant_id, display_id=did,
                role=roles.ROLE_COLLABORATOR,
                full_name=person_name,
            )
            session.add(person)
            await session.flush()
        lock_person = person

    expires_at = None
    if expires_hours:
        expires_at = datetime.now(timezone.utc) + timedelta(hours=expires_hours)

    token = _gen_token()
    invite = InviteLink(
        tenant_id=tenant_id, token=token, role=roles.ROLE_COLLABORATOR,
        label=f"{'آشنا' if acquaintance_type == 'known' else 'ناآشنا'}|{person_name or 'عمومی'}",
        lock_to_person_id=lock_person.id if lock_person else None,
        expires_at=expires_at, max_uses=max_uses,
    )
    session.add(invite)
    await session.commit()

    link_url = f"https://t.me/{bot_username}?start=inv_{token}"

    if acquaintance_type == "known":
        msg = (f"سلام! 😊 من دستیار {biz_name} هستم، گفتن باهات در ارتباط باشیم تا هماهنگی‌هامون راحت‌تر پیش بره.\n\n"
               f"[ارتباط با ما]({link_url})")
    else:
        msg = (f"سلام! 😊 من دستیار {biz_name} هستم. {biz_desc_short}\n"
               f"خوشحالم که آشنا شدیم.\n\n"
               f"[ارتباط با ما]({link_url})")

    info = (f"🔗 لینک همکار ساخته شد:\n"
            f"نوع: {'آشنا' if acquaintance_type == 'known' else 'ناآشنا'}\n"
            + (f"برای: {person_name}\n" if person_name else ""))

    return f"{info}\n\n---\n{msg}"


# ─────────────────────────────────────────────
# consume — ورود با لینک
# ─────────────────────────────────────────────

async def consume_invite_link(session: AsyncSession, token: str,
                               telegram_id: int, telegram_username: str = None,
                               full_name: str = None,
                               password_attempt: str = None) -> tuple[bool, str]:
    link = await session.scalar(
        select(InviteLink).where(InviteLink.token == token)
    )
    if not link:
        return False, "⚠️ این لینک معتبر نیست."
    if link.is_revoked:
        return False, "⚠️ این لینک لغو شده."

    # بررسی انقضا
    if link.expires_at:
        exp = link.expires_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if exp < datetime.now(timezone.utc):
            return False, "⚠️ این لینک منقضی شده. از کارفرما لینک جدید بخواه."

    # سقف استفاده
    if link.max_uses is not None and link.use_count >= link.max_uses:
        return False, "⚠️ ظرفیت این لینک پر شده."

    # رمز
    if link.password:
        if not password_attempt:
            return False, "PASSWORD_REQUIRED"
        # normalize شماره تماس (با/بدون 0 یا 98)
        attempts = [password_attempt]
        p = password_attempt.strip()
        if p.startswith("0"):
            attempts.append(p[1:])
            attempts.append("98" + p[1:])
        elif p.startswith("98"):
            attempts.append("0" + p[2:])
            attempts.append(p[2:])
        elif len(p) == 10:
            attempts.append("0" + p)
            attempts.append("98" + p)

        matched = any(
            _hash_password(a) == link.password or a == link.password
            for a in attempts
        )
        if not matched:
            return False, "WRONG_PASSWORD"

    # چک تکراری
    existing = await session.scalar(
        select(Person).where(
            Person.tenant_id == link.tenant_id,
            Person.telegram_id == telegram_id,
            Person.is_active == True,
        )
    )
    if existing:
        role_fa = roles.ROLE_LABELS.get(existing.role, existing.role)
        return False, f"شما قبلاً به‌عنوان {role_fa} عضو این مجموعه هستید."

    # اتصال
    if link.lock_to_person_id:
        person = await session.get(Person, link.lock_to_person_id)
        if not person:
            return False, "⚠️ رکورد مرتبط پیدا نشد."
        # اگه قبلاً وصل بوده ولی قطع شده (telegram_id=None) → اجازه اتصال مجدد
        if person.telegram_id and person.telegram_id != telegram_id:
            return False, "⚠️ این لینک قبلاً توسط شخص دیگه‌ای استفاده شده."
        person.telegram_id = telegram_id
        person.telegram_username = telegram_username
        person.connected_at = datetime.now(timezone.utc)
    else:
        did = await _gen_person_display_id(session, link.tenant_id)
        person = Person(
            tenant_id=link.tenant_id, display_id=did, role=link.role,
            full_name=full_name or "کاربر جدید",
            telegram_id=telegram_id, telegram_username=telegram_username,
            connected_at=datetime.now(timezone.utc),
        )
        session.add(person)

    link.use_count += 1

    # اگه کارمنده — credential بساز
    if link.role == roles.ROLE_EMPLOYEE and link.lock_to_person_id:
        from app.database.models.business import Employee
        if person.linked_employee_id:
            emp = await session.get(Employee, person.linked_employee_id)
            if emp and emp.national_id and emp.phone:
                existing_cred = await session.scalar(
                    select(PersonCredential).where(PersonCredential.person_id == person.id)
                )
                if not existing_cred:
                    cred = PersonCredential(
                        tenant_id=link.tenant_id, person_id=person.id,
                        username=emp.national_id,
                        password_hash=_hash_password(emp.phone),
                        must_change=True,
                    )
                    session.add(cred)

    await session.commit()

    # تشخیص نوع لینک برای پیام خوش‌آمد
    link_type = "prefilled"
    if link.label and "|" in link.label:
        link_type = link.label.split("|")[0]

    role_fa = roles.ROLE_LABELS.get(link.role, link.role)

    # پیام خوش‌آمد متناسب
    if link.role == roles.ROLE_EMPLOYEE:
        if link_type == "self":
            welcome = (f"✅ خوش اومدی {person.full_name}!\n\n"
                       f"اول یوزرنیم و پسوردت رو تغییر بده.\n"
                       f"⚠️ این یوزرنیم مخصوص این مجموعه‌ست و به تلگرامت ربطی نداره.\n\n"
                       f"یوزرنیم جدیدت رو بفرست (حداقل ۵ کاراکتر، فقط حروف لاتین و عدد و _):")
        else:
            welcome = (f"✅ خوش اومدی {person.full_name}!\n\n"
                       f"محتوای چتت کاملاً خصوصیه — حتی کارفرما نمی‌تونه ببینه.\n"
                       f"اول یوزرنیم و پسوردت رو تغییر بده.\n"
                       f"یوزرنیم جدیدت رو بفرست:")
        return True, welcome + "|CHANGE_CREDENTIALS"
    else:
        return True, f"✅ خوش اومدی! به‌عنوان {role_fa} وصل شدی."


# ─────────────────────────────────────────────
# مدیریت Credentials
# ─────────────────────────────────────────────

async def change_credentials(session: AsyncSession, telegram_id: int,
                               new_username: str = None,
                               new_password: str = None) -> str:
    """تغییر یوزرنیم و پسورد کارمند."""
    person = await get_person_by_telegram(session, telegram_id)
    if not person:
        return "⚠️ حساب پیدا نشد."

    cred = await session.scalar(
        select(PersonCredential).where(PersonCredential.person_id == person.id)
    )
    if not cred:
        return "⚠️ اطلاعات ورود پیدا نشد."

    if new_username:
        # اعتبارسنجی
        import re
        if not re.match(r'^[a-zA-Z0-9_]{5,30}$', new_username):
            return "⚠️ یوزرنیم باید ۵ تا ۳۰ کاراکتر، فقط حروف لاتین، عدد یا _ باشه."
        # چک تکراری
        existing = await session.scalar(
            select(PersonCredential).where(
                PersonCredential.username == new_username,
                PersonCredential.tenant_id == cred.tenant_id,
            )
        )
        if existing and existing.id != cred.id:
            return "⚠️ این یوزرنیم قبلاً استفاده شده. یکی دیگه انتخاب کن."
        cred.username = new_username

    if new_password:
        import re
        if len(new_password) < 8:
            return "⚠️ پسورد باید حداقل ۸ کاراکتر باشه."
        cred.password_hash = _hash_password(new_password)
        cred.must_change = False

    await session.commit()
    return "✅ اطلاعات ورودت بروز شد."


async def employee_change_password_request(session: AsyncSession,
                                             telegram_id: int,
                                             tenant_id: int) -> str:
    """کارمند می‌خواد پسورد تغییر بده — به کارفرما اطلاع بده."""
    person = await get_person_by_telegram(session, telegram_id)
    if not person:
        return "⚠️ حساب پیدا نشد."

    return (f"NOTIFY_OWNER|{tenant_id}|{person.full_name} می‌خواد پسوردش رو تغییر بده. "
            f"اگه موافقی بگو «پسورد {person.full_name} تغییر بشه» و پسورد جدید رو بگو.|"
            f"برای تغییر پسورد باید با کارفرما هماهنگ بشه. الان بهشون گفتم.")


# ─────────────────────────────────────────────
# لیست و مدیریت لینک‌ها
# ─────────────────────────────────────────────

async def list_invite_links(session: AsyncSession, tenant_id: int) -> str:
    links = (await session.scalars(
        select(InviteLink).where(
            InviteLink.tenant_id == tenant_id,
            InviteLink.is_revoked == False,
        ).order_by(InviteLink.id.desc())
    )).all()

    if not links:
        return "لینک دعوت فعالی نداری."

    now = datetime.now(timezone.utc)
    lines = ["🔗 لینک‌های دعوت:"]
    for lk in links:
        role_fa = roles.ROLE_LABELS.get(lk.role, lk.role)
        exp = lk.expires_at
        if exp:
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
            status = "منقضی" if exp < now else "فعال"
        else:
            status = "فعال"
        uses = f"{lk.use_count}/{lk.max_uses}" if lk.max_uses else f"{lk.use_count} بار"
        label = lk.label.split("|")[-1] if lk.label and "|" in lk.label else (lk.label or "—")
        lines.append(f"• {label} ({role_fa}) — {status} — {uses} — LNK-{lk.id}")
    return "\n".join(lines)


async def revoke_invite_link(session: AsyncSession, tenant_id: int,
                              link_id: str) -> str:
    raw = link_id.upper().replace("LNK-", "").strip()
    try:
        lid = int(raw)
    except ValueError:
        return "⚠️ شناسه نامعتبره. مثل LNK-3 بگو."

    link = await session.scalar(
        select(InviteLink).where(
            InviteLink.tenant_id == tenant_id,
            InviteLink.id == lid,
        )
    )
    if not link:
        return f"⚠️ لینک LNK-{lid} پیدا نشد."
    link.is_revoked = True
    await session.commit()
    return f"🚫 لینک لغو شد."


async def revoke_all_invite_links(session: AsyncSession, tenant_id: int) -> str:
    links = (await session.scalars(
        select(InviteLink).where(
            InviteLink.tenant_id == tenant_id,
            InviteLink.is_revoked == False,
        )
    )).all()
    if not links:
        return "لینک فعالی نداری."
    for lk in links:
        lk.is_revoked = True
    await session.commit()
    return f"🚫 {len(links)} لینک لغو شد."


# ─────────────────────────────────────────────
# Followup
# ─────────────────────────────────────────────

async def get_due_followups(session: AsyncSession):
    from datetime import datetime, timezone
    from app.database.models.business import PersonFollowup
    now = datetime.now(timezone.utc)
    return (await session.scalars(
        select(PersonFollowup).where(
            PersonFollowup.is_active == True,
            PersonFollowup.next_send_at <= now,
        )
    )).all()


# ═══════════════════════════════════════
# قطع اتصال / اتصال مجدد / حذف
# ═══════════════════════════════════════

async def disconnect_person(session: AsyncSession, tenant_id: int,
                             display_id_or_name: str) -> str:
    """قطع اتصال — کارمند می‌مونه ولی از ربات جدا میشه."""
    person = await _find_person(session, tenant_id, display_id_or_name)
    if not person:
        return f"⚠️ «{display_id_or_name}» پیدا نشد."
    if not person.is_connected:
        return f"⚠️ «{person.full_name}» اصلاً وصل نیست."

    person.telegram_id = None
    person.telegram_username = None
    person.connected_at = None
    # is_connected property از telegram_id محاسبه میشه

    # لینک‌های قبلی رو هم revoke کن
    from app.database.models.business import InviteLink
    old_links = (await session.scalars(
        select(InviteLink).where(
            InviteLink.tenant_id == tenant_id,
            InviteLink.lock_to_person_id == person.id,
            InviteLink.is_revoked == False,
        )
    )).all()
    for lk in old_links:
        lk.is_revoked = True

    await session.commit()
    return (f"✅ «{person.full_name}» از ربات قطع شد.\n"
            f"برای اتصال مجدد لینک دعوت جدید بساز.")


async def _find_person(session: AsyncSession, tenant_id: int,
                        query: str) -> "Person | None":
    """پیدا کردن Person با نام یا display_id."""
    q = query.strip().upper()
    if q.startswith("PER-"):
        return await session.scalar(
            select(Person).where(
                Person.tenant_id == tenant_id,
                Person.display_id == q,
            )
        )
    return await session.scalar(
        select(Person).where(
            Person.tenant_id == tenant_id,
            Person.full_name.ilike(f"%{query}%"),
            Person.is_active == True,
        ).limit(1)
    )
