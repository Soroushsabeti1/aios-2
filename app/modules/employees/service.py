"""سرویس ماژول کارمندان (HR) — نسخه ۲ با فیلدهای جدید و آیدی."""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.models.business import Employee, SalaryPayment
from app.data.iran_geo import find_province
from app.utils.normalizer import format_amount
from app.utils.jalali import parse_jalali, to_jalali_str
from app.utils.id_generator import generate_display_id


async def add_employee(session: AsyncSession, tenant_id: int, name: str,
                       national_id: str = None, phone: str = None, birth_date: str = None,
                       marital_status: str = None, children_count: int = 0,
                       city: str = None, address: str = None,
                       role: str = None, shift_type: str = None,
                       monthly_work_days: int = 26,
                       base_salary: float = 0, deductions: float = 0,
                       bank_account: str = None, leave_days: int = 0,
                       insurance_number: str = None, insurance_amount: float = 0,
                       insurance_start: str = None, hire_date: str = None,
                       contract_end: str = None, code: str = None) -> str:
    existing = await session.scalar(
        select(Employee).where(Employee.tenant_id == tenant_id, Employee.name == name)
    )
    if existing:
        return f"⚠️ کارمند «{name}» از قبل ثبت شده. (شناسه: {existing.display_id})"

    province = find_province(city) if city else None
    did = await generate_display_id(session, tenant_id, "employees", Employee)

    employee = Employee(
        tenant_id=tenant_id, display_id=did, name=name, national_id=national_id,
        phone=phone, birth_date=parse_jalali(birth_date) if birth_date else None,
        marital_status=marital_status, children_count=children_count or 0,
        city=city, province=province, address=address,
        role=role, shift_type=shift_type,
        monthly_work_days=monthly_work_days or 26,
        base_salary=base_salary or 0, deductions=deductions or 0,
        bank_account=bank_account, leave_days=leave_days or 0,
        insurance_number=insurance_number, insurance_amount=insurance_amount or 0,
        insurance_start=parse_jalali(insurance_start) if insurance_start else None,
        hire_date=parse_jalali(hire_date) if hire_date else None,
        contract_end=parse_jalali(contract_end) if contract_end else None,
        code=code,
    )
    session.add(employee)
    await session.flush()

    # راه الف: همزمان یک رکورد Person با نقش employee بساز و به هم وصل کن
    # تا بتوان برای این کارمند لینک دعوت ساخت.
    from app.database.models.business import Person
    from sqlalchemy import func as _func
    person_count = await session.scalar(
        select(_func.count(Person.id)).where(Person.tenant_id == tenant_id)
    ) or 0
    person = Person(
        tenant_id=tenant_id,
        display_id=f"PER-{person_count + 1:04d}",
        role="employee",
        full_name=name,
        phone=phone,
        linked_employee_id=employee.id,
    )
    session.add(person)
    await session.commit()

    parts = [f"✅ کارمند «{name}» ثبت شد (شناسه: {did})"]
    if role:
        parts.append(f"💼 {role}")
    if city:
        parts.append(f"📍 {city}" + (f" ({province})" if province else ""))
    if base_salary:
        parts.append(f"💰 حقوق: {format_amount(int(base_salary))}")
    if employee.hire_date:
        parts.append(f"📅 استخدام: {to_jalali_str(employee.hire_date)}")
    if employee.contract_end:
        parts.append(f"📆 پایان قرارداد: {to_jalali_str(employee.contract_end)}")
    parts.append("💡 برای وصل کردنش به تلگرام بگو «لینک دعوت برای " + name + " بساز».")
    return "\n".join(parts)


async def list_employees(session: AsyncSession, tenant_id: int,
                         filter: str = "all", city: str = None) -> str:
    query = select(Employee).where(Employee.tenant_id == tenant_id)
    if filter == "by_city" and city:
        query = query.where(Employee.city == city)
    query = query.order_by(Employee.name)

    employees = (await session.scalars(query)).all()
    if not employees:
        return "کارمندی با این مشخصات پیدا نشد."

    lines = []
    for e in employees:
        line = f"• [{e.display_id}] {e.name}"
        if e.role:
            line += f" — {e.role}"
        if e.city:
            line += f" ({e.city})"
        lines.append(line)

    header = f"👔 کارمندان {city}:" if filter == "by_city" else "👔 کارمندان:"
    return header + "\n" + "\n".join(lines)


async def add_salary_payment(session: AsyncSession, tenant_id: int,
                             employee_name: str, amount: float,
                             payment_date: str = None, period: str = None,
                             payment_method: str = None, note: str = None) -> str:
    emp = await session.scalar(
        select(Employee).where(Employee.tenant_id == tenant_id, Employee.name == employee_name)
    )
    if not emp:
        return f"کارمند «{employee_name}» پیدا نشد."

    payment = SalaryPayment(
        tenant_id=tenant_id, employee_id=emp.id, amount=amount,
        payment_date=parse_jalali(payment_date) if payment_date else None,
        period=period, payment_method=payment_method, note=note,
    )
    session.add(payment)
    await session.commit()
    return (f"✅ پرداخت {format_amount(int(amount))} به «{employee_name}» ثبت شد.\n"
            f"📅 {period or ''}")


async def list_salary_payments(session: AsyncSession, tenant_id: int,
                               employee_name: str) -> str:
    emp = await session.scalar(
        select(Employee).where(Employee.tenant_id == tenant_id, Employee.name == employee_name)
    )
    if not emp:
        return f"کارمند «{employee_name}» پیدا نشد."

    payments = (await session.scalars(
        select(SalaryPayment).where(
            SalaryPayment.tenant_id == tenant_id,
            SalaryPayment.employee_id == emp.id,
        ).order_by(SalaryPayment.payment_date.desc()).limit(10)
    )).all()

    if not payments:
        return f"هیچ پرداختی برای «{employee_name}» ثبت نشده."

    lines = [f"💰 تاریخچه پرداخت «{employee_name}» [{emp.display_id}]:"]
    for p in payments:
        d = to_jalali_str(p.payment_date) if p.payment_date else "—"
        lines.append(f"• {d} — {format_amount(int(p.amount))}" + (f" ({p.period})" if p.period else ""))
    return "\n".join(lines)


async def update_employee(session: AsyncSession, tenant_id: int, name: str,
                          new_name: str = None, new_role: str = None,
                          new_phone: str = None, new_base_salary: float = None,
                          new_city: str = None, new_national_id: str = None,
                          new_contract_end: str = None,
                          new_bank_account: str = None) -> str:
    """ویرایش اطلاعات یک کارمند."""
    emp = await session.scalar(
        select(Employee).where(Employee.tenant_id == tenant_id, Employee.name == name)
    )
    if not emp:
        return f"⚠️ کارمند «{name}» پیدا نشد."

    changes = []
    if new_name and new_name != emp.name:
        emp.name = new_name
        changes.append(f"نام → {new_name}")
    if new_role:
        emp.role = new_role
        changes.append(f"نقش → {new_role}")
    if new_phone:
        emp.phone = new_phone
        changes.append(f"تلفن → {new_phone}")
    if new_base_salary is not None:
        emp.base_salary = new_base_salary
        changes.append(f"حقوق → {format_amount(int(new_base_salary))}")
    if new_city:
        emp.city = new_city
        emp.province = find_province(new_city)
        changes.append(f"شهر → {new_city}")
    if new_national_id:
        emp.national_id = new_national_id
        changes.append(f"کد ملی → {new_national_id}")
    if new_contract_end:
        emp.contract_end = parse_jalali(new_contract_end)
        changes.append(f"پایان قرارداد → {to_jalali_str(emp.contract_end)}")
    if new_bank_account:
        emp.bank_account = new_bank_account
        changes.append("شماره حساب بروز شد")

    if not changes:
        return "تغییری اعمال نشد. بگو دقیقاً چی رو عوض کنم."

    await session.commit()
    return f"✅ کارمند «{emp.name}» ({emp.display_id}) ویرایش شد:\n" + "\n".join(f"• {c}" for c in changes)


async def delete_employee(session: AsyncSession, tenant_id: int, name: str) -> str:
    """حذف یک کارمند — رکورد Person متناظر هم پاک می‌شود."""
    try:
        emp = await session.scalar(
            select(Employee).where(
                Employee.tenant_id == tenant_id,
                Employee.name.ilike(f"%{name}%"),
            ).limit(1)
        )
        if not emp:
            return f"⚠️ کارمند «{name}» پیدا نشد."

        did = emp.display_id
        emp_name = emp.name

        # حذف PersonCredential اول
        from app.database.models.business import Person, PersonCredential
        linked_person = await session.scalar(
            select(Person).where(
                Person.tenant_id == tenant_id,
                Person.linked_employee_id == emp.id,
            )
        )
        if linked_person:
            cred = await session.scalar(
                select(PersonCredential).where(
                    PersonCredential.person_id == linked_person.id
                )
            )
            if cred:
                await session.delete(cred)
                await session.flush()
            await session.delete(linked_person)
            await session.flush()

        await session.delete(emp)
        await session.commit()
        return f"🗑 کارمند «{emp_name}» ({did}) حذف شد."

    except Exception as e:
        await session.rollback()
        return f"⚠️ حذف ممکن نشد: {e}"


async def get_employee_detail(session: AsyncSession, tenant_id: int,
                               name: str) -> str:
    """اطلاعات کامل یک کارمند — شامل شماره حساب، بیمه، آدرس و ..."""
    emp = await session.scalar(
        select(Employee).where(
            Employee.tenant_id == tenant_id,
            Employee.name.ilike(f"%{name}%"),
        ).limit(1)
    )
    if not emp:
        return f"⚠️ کارمندی با نام «{name}» پیدا نشد."

    lines = [f"👔 اطلاعات کامل کارمند «{emp.name}» [{emp.display_id}]:"]
    if emp.code:
        lines.append(f"🔖 کد پرسنلی: {emp.code}")
    if emp.national_id:
        lines.append(f"🪪 کد ملی: {emp.national_id}")
    if emp.phone:
        lines.append(f"📞 تلفن: {emp.phone}")
    if emp.birth_date:
        lines.append(f"🎂 تولد: {to_jalali_str(emp.birth_date)}")
    if emp.role:
        lines.append(f"💼 نقش: {emp.role}")
    if emp.work_mode:
        lines.append(f"📋 نحوه کار: {emp.work_mode}")
    if emp.contract_type:
        lines.append(f"📄 نوع قرارداد: {emp.contract_type}")
    if emp.shift_type:
        lines.append(f"🔄 نوبت کاری: {emp.shift_type}")
    if emp.marital_status:
        lines.append(f"💍 تأهل: {emp.marital_status}")
    if emp.children_count:
        lines.append(f"👶 فرزند: {emp.children_count}")
    if emp.province or emp.city:
        lines.append(f"📍 {emp.city or ''} {('(' + emp.province + ')') if emp.province else ''}")
    if emp.address:
        lines.append(f"🏠 آدرس: {emp.address}")
    if emp.postal_code:
        lines.append(f"📮 کد پستی: {emp.postal_code}")
    if emp.base_salary:
        lines.append(f"💰 حقوق پایه: {format_amount(int(emp.base_salary))}")
    if emp.deductions:
        lines.append(f"➖ کسورات: {format_amount(int(emp.deductions))}")
    if emp.bank_account:
        lines.append(f"🏦 شماره حساب: {emp.bank_account}")
    if emp.insurance_number:
        lines.append(f"🏥 شماره بیمه: {emp.insurance_number}")
    if emp.insurance_amount:
        lines.append(f"💊 مبلغ بیمه: {format_amount(int(emp.insurance_amount))}")
    if emp.insurance_start:
        lines.append(f"📅 شروع بیمه: {to_jalali_str(emp.insurance_start)}")
    if emp.hire_date:
        lines.append(f"📅 تاریخ استخدام: {to_jalali_str(emp.hire_date)}")
    if emp.contract_end:
        lines.append(f"📆 پایان قرارداد: {to_jalali_str(emp.contract_end)}")
    if emp.annual_leave:
        lines.append(f"🏖 مرخصی استحقاقی: {emp.annual_leave} روز")
    if emp.bale_id:
        lines.append(f"💬 بله: {emp.bale_id}")
    if emp.telegram_id:
        lines.append(f"📱 تلگرام: {emp.telegram_id}")
    if emp.rubika_id:
        lines.append(f"📲 روبیکا: {emp.rubika_id}")
    return "\n".join(lines)


async def search_employees(session: AsyncSession, tenant_id: int,
                            sort_by: str = "name", order: str = "asc",
                            filter_field: str = None, filter_value: str = None,
                            limit: int = 20) -> str:
    """جستجو و مرتب‌سازی کارمندان."""
    from sqlalchemy import desc as _desc

    query = select(Employee).where(Employee.tenant_id == tenant_id)

    # فیلتر
    if filter_field and filter_value:
        field_map = {
            "city": Employee.city, "role": Employee.role,
            "marital_status": Employee.marital_status,
            "work_mode": Employee.work_mode, "contract_type": Employee.contract_type,
            "shift_type": Employee.shift_type,
        }
        col = field_map.get(filter_field)
        if col is not None:
            query = query.where(col.ilike(f"%{filter_value}%"))

    # مرتب‌سازی
    sort_map = {
        "name": Employee.name, "salary": Employee.base_salary,
        "hire_date": Employee.hire_date, "city": Employee.city,
    }
    sort_col = sort_map.get(sort_by, Employee.name)
    if order == "desc":
        query = query.order_by(_desc(sort_col))
    else:
        query = query.order_by(sort_col)

    query = query.limit(limit)
    employees = (await session.scalars(query)).all()
    if not employees:
        return "کارمندی پیدا نشد."

    lines = [f"👔 کارمندان (مرتب بر اساس {sort_by}):"]
    for i, e in enumerate(employees, 1):
        line = f"{i}. [{e.display_id}] {e.name}"
        if sort_by == "salary" and e.base_salary:
            line += f" — {format_amount(int(e.base_salary))}"
        if e.role:
            line += f" ({e.role})"
        if e.city:
            line += f" [{e.city}]"
        lines.append(line)
    return "\n".join(lines)


async def employee_statistics(session: AsyncSession, tenant_id: int) -> str:
    """آمار کلی کارمندان."""
    from sqlalchemy import func as _func

    employees = (await session.scalars(
        select(Employee).where(Employee.tenant_id == tenant_id)
    )).all()

    if not employees:
        return "هیچ کارمندی ثبت نشده."

    total = len(employees)
    married = sum(1 for e in employees if e.marital_status in ("متاهل", "متأهل"))
    salaries = [e.base_salary for e in employees if e.base_salary]
    avg_salary = sum(salaries) / len(salaries) if salaries else 0
    max_salary = max(salaries) if salaries else 0
    min_salary = min(salaries) if salaries else 0
    cities = set(e.city for e in employees if e.city)

    lines = [
        f"📊 آمار کارمندان:",
        f"👥 تعداد کل: {total}",
        f"💍 متاهل: {married} | مجرد: {total - married}",
        f"💰 میانگین حقوق: {format_amount(int(avg_salary))}",
        f"📈 بیشترین: {format_amount(int(max_salary))}",
        f"📉 کمترین: {format_amount(int(min_salary))}",
        f"🏙 شهرها: {', '.join(cities) if cities else '—'}",
    ]
    return "\n".join(lines)
