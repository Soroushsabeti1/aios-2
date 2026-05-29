"""سرویس ماژول کالا و انبار — نسخه ۲ با آیدی + best_selling واقعی."""
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.models.business import Product, InvoiceItem
from app.utils.normalizer import format_amount
from app.utils.id_generator import generate_display_id


async def add_product(session: AsyncSession, tenant_id: int, name: str,
                      category: str = None, unit: str = None, buy_price: float = 0,
                      sell_price: float = 0, stock: int = 0, min_stock: int = 0,
                      supplier: str = None, barcode: str = None, code: str = None) -> str:
    existing = await session.scalar(
        select(Product).where(Product.tenant_id == tenant_id, Product.name == name)
    )
    if existing:
        return f"⚠️ کالای «{name}» از قبل ثبت شده. (شناسه: {existing.display_id})"

    did = await generate_display_id(session, tenant_id, "products", Product)

    product = Product(
        tenant_id=tenant_id, display_id=did, name=name, category=category, unit=unit,
        buy_price=buy_price or 0, sell_price=sell_price or 0,
        stock=stock or 0, min_stock=min_stock or 0,
        supplier=supplier, barcode=barcode, code=code,
    )
    session.add(product)
    await session.commit()

    parts = [f"✅ کالای «{name}» ثبت شد (شناسه: {did})"]
    if stock:
        parts.append(f"📦 موجودی: {stock}" + (f" {unit}" if unit else ""))
    if sell_price:
        parts.append(f"🏷 قیمت فروش: {format_amount(int(sell_price))}")
    return "\n".join(parts)


async def list_products(session: AsyncSession, tenant_id: int, filter: str = "all") -> str:
    if filter == "best_selling":
        # join واقعی با InvoiceItem برای پرفروش‌ترین
        results = (await session.execute(
            select(
                Product.display_id, Product.name,
                func.coalesce(func.sum(InvoiceItem.quantity), 0).label("sold")
            )
            .outerjoin(InvoiceItem, InvoiceItem.product_id == Product.id)
            .where(Product.tenant_id == tenant_id)
            .group_by(Product.id)
            .order_by(func.coalesce(func.sum(InvoiceItem.quantity), 0).desc())
            .limit(10)
        )).all()

        if not results:
            return "کالایی ثبت نشده."

        lines = ["🔥 پرفروش‌ترین کالاها:"]
        for did, name, sold in results:
            lines.append(f"• [{did}] {name} — فروش: {sold}")
        return "\n".join(lines)

    query = select(Product).where(Product.tenant_id == tenant_id)
    if filter == "low_stock":
        query = query.where(Product.stock <= Product.min_stock)
    query = query.order_by(Product.name)

    products = (await session.scalars(query)).all()
    if not products:
        return "✅ هیچ کالایی رو به اتمام نیست." if filter == "low_stock" else "کالایی ثبت نشده."

    lines = []
    for p in products:
        line = f"• [{p.display_id}] {p.name} — موجودی: {p.stock}"
        if filter == "low_stock":
            line += f" ⚠️ (حداقل: {p.min_stock})"
        lines.append(line)

    header = {"low_stock": "⚠️ کالاهای رو به اتمام:"}.get(filter, "📦 کالاها:")
    return header + "\n" + "\n".join(lines)


async def update_product(session: AsyncSession, tenant_id: int, name: str,
                         new_name: str = None, new_sell_price: float = None,
                         new_buy_price: float = None, new_stock: int = None,
                         new_min_stock: int = None, new_category: str = None) -> str:
    """ویرایش یک کالا."""
    product = await session.scalar(
        select(Product).where(Product.tenant_id == tenant_id, Product.name == name)
    )
    if not product:
        return f"⚠️ کالای «{name}» پیدا نشد."

    changes = []
    if new_name and new_name != product.name:
        product.name = new_name
        changes.append(f"نام → {new_name}")
    if new_sell_price is not None:
        product.sell_price = new_sell_price
        changes.append(f"قیمت فروش → {format_amount(int(new_sell_price))}")
    if new_buy_price is not None:
        product.buy_price = new_buy_price
        changes.append(f"قیمت خرید → {format_amount(int(new_buy_price))}")
    if new_stock is not None:
        product.stock = new_stock
        changes.append(f"موجودی → {new_stock}")
    if new_min_stock is not None:
        product.min_stock = new_min_stock
        changes.append(f"حداقل موجودی → {new_min_stock}")
    if new_category:
        product.category = new_category
        changes.append(f"دسته → {new_category}")

    if not changes:
        return "تغییری اعمال نشد. بگو دقیقاً چی رو عوض کنم."

    await session.commit()
    return f"✅ کالای «{product.name}» ({product.display_id}) ویرایش شد:\n" + "\n".join(f"• {c}" for c in changes)


async def delete_product(session: AsyncSession, tenant_id: int, name: str) -> str:
    """حذف یک کالا."""
    product = await session.scalar(
        select(Product).where(Product.tenant_id == tenant_id, Product.name == name)
    )
    if not product:
        return f"⚠️ کالای «{name}» پیدا نشد."
    did = product.display_id
    await session.delete(product)
    await session.commit()
    return f"🗑 کالای «{name}» ({did}) حذف شد."
