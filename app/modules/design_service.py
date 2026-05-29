"""
سرویس طراحی — Flux تصویرساز + Pillow متن فارسی.

قابلیت‌ها:
  - تولید پوستر (پس‌زمینه AI + متن فارسی با فونت)
  - پست اسلایدی زنجیره‌ای
  - کاتالوگ PDF چندصفحه‌ای
  - برش عکس
  - تمپلیت ذخیره + دسته‌جمعی
  - بایگانی عکس
"""
from __future__ import annotations
import io
import json
import base64
import httpx
from PIL import Image, ImageDraw, ImageFont
import arabic_reshaper
from bidi.algorithm import get_display
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.database.models.business import (
    BrandConfig, DesignTemplate, DesignHistory, EntityPhoto, Product,
)

FLUX_MODEL = "black-forest-labs/flux.2-pro"

SIZE_PRESETS = {
    "story": (1080, 1920),
    "post": (1080, 1080),
    "landscape": (1920, 1080),
    "a4": (2480, 3508),
    "a5": (1748, 2480),
}

# فونت پیش‌فرض (اگه کارفرما فونت نداده)
_DEFAULT_FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"


# ═══════════════════════════════════════
# Flux API
# ═══════════════════════════════════════

async def _generate_image_flux(prompt: str, width: int = 1080, height: int = 1080) -> bytes | None:
    """تولید تصویر با Flux از OpenRouter — روش صحیح."""
    try:
        import httpx as _httpx
        async with _httpx.AsyncClient(timeout=120.0) as client:
            # روش صحیح OpenRouter برای Flux: chat/completions
            resp = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.openrouter_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": FLUX_MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )

            if resp.status_code == 200:
                data = resp.json()
                # جواب ممکنه URL عکس باشه
                content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                if content:
                    # اگه URL هست
                    if content.strip().startswith("http"):
                        img_resp = await client.get(content.strip(), timeout=60)
                        if img_resp.status_code == 200:
                            return img_resp.content
                    # اگه base64 هست
                    else:
                        import base64
                        try:
                            return base64.b64decode(content)
                        except Exception:
                            pass
                # بعضی مدل‌ها توی data.url برمیگردونن
                url = data.get("data", [{}])[0].get("url", "")
                if url:
                    img_resp = await client.get(url, timeout=60)
                    return img_resp.content

            import logging
            logging.getLogger(__name__).error(
                f"Flux error {resp.status_code}: {resp.text[:200]}"
            )
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Flux exception: {e}")

    return None

def _render_persian_text(img: Image.Image, text: str, position: tuple,
                          font_path: str = None, font_size: int = 48,
                          color: str = "#FFFFFF", max_width: int = None) -> Image.Image:
    """نوشتن متن فارسی روی عکس با فونت واقعی."""
    draw = ImageDraw.Draw(img)

    try:
        font = ImageFont.truetype(font_path or _DEFAULT_FONT_PATH, font_size)
    except Exception:
        font = ImageFont.load_default()

    # reshape فارسی
    reshaped = arabic_reshaper.reshape(text)
    bidi_text = get_display(reshaped)

    # word wrap
    if max_width:
        words = bidi_text.split()
        lines = []
        current = ""
        for word in words:
            test = f"{current} {word}".strip()
            bbox = draw.textbbox((0, 0), test, font=font)
            if bbox[2] - bbox[0] > max_width and current:
                lines.append(current)
                current = word
            else:
                current = test
        if current:
            lines.append(current)
    else:
        lines = [bidi_text]

    x, y = position
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        text_w = bbox[2] - bbox[0]
        # وسط‌چین
        draw.text((x + (max_width - text_w) // 2 if max_width else x, y),
                  line, font=font, fill=color)
        y += bbox[3] - bbox[1] + 10

    return img


async def _get_brand(session: AsyncSession, tenant_id: int) -> BrandConfig | None:
    return await session.scalar(
        select(BrandConfig).where(BrandConfig.tenant_id == tenant_id)
    )


async def _get_font_path(session: AsyncSession, tenant_id: int,
                          font_type: str = "title") -> str:
    """مسیر فونت — اول از برند، بعد پیش‌فرض."""
    brand = await _get_brand(session, tenant_id)
    if brand and brand.fonts_json:
        try:
            fonts = json.loads(brand.fonts_json)
            path = fonts.get(font_type)
            if path:
                return path
        except Exception:
            pass
    return _DEFAULT_FONT_PATH


# ═══════════════════════════════════════
# تولید پوستر
# ═══════════════════════════════════════

async def generate_poster(session: AsyncSession, tenant_id: int,
                           title: str, subtitle: str = "",
                           size_preset: str = "post",
                           creativity: int = 50,
                           bg_prompt: str = None,
                           product_id: int = None) -> tuple[io.BytesIO | None, str, str]:
    """
    تولید پوستر.
    Returns: (image_buffer, filename, message)
    """
    w, h = SIZE_PRESETS.get(size_preset, (1080, 1080))
    brand = await _get_brand(session, tenant_id)

    # ساخت پرامپت انگلیسی برای Flux
    if bg_prompt:
        prompt = bg_prompt
    else:
        prompt = (
            f"Professional modern advertising poster background, "
            f"clean design, {size_preset} format, "
            f"no text, no letters, no words, "
            f"suitable for product promotion, "
            f"creativity level: {creativity}%"
        )
        if brand and brand.primary_color:
            prompt += f", brand color scheme: {brand.primary_color}"

    # تولید پس‌زمینه
    img_bytes = await _generate_image_flux(prompt, w, h)
    if not img_bytes:
        return None, "", "⚠️ خطا در تولید تصویر. دوباره امتحان کن."

    img = Image.open(io.BytesIO(img_bytes)).resize((w, h))

    # عکس محصول (اگه داده شده)
    if product_id:
        photo = await session.scalar(
            select(EntityPhoto).where(
                EntityPhoto.tenant_id == tenant_id,
                EntityPhoto.entity_type == "product",
                EntityPhoto.entity_id == product_id,
                EntityPhoto.is_primary == True,
            )
        )
        if photo:
            prod_img = Image.open(io.BytesIO(photo.photo))
            prod_img.thumbnail((w // 3, h // 3))
            # وسط پایین
            px = (w - prod_img.width) // 2
            py = h - prod_img.height - 50
            img.paste(prod_img, (px, py), prod_img if prod_img.mode == 'RGBA' else None)

    # لوگو
    if brand and brand.logo:
        try:
            logo = Image.open(io.BytesIO(brand.logo))
            logo.thumbnail((150, 150))
            img.paste(logo, (w - logo.width - 30, 30),
                      logo if logo.mode == 'RGBA' else None)
        except Exception:
            pass

    # متن فارسی
    title_font = await _get_font_path(session, tenant_id, "title")
    body_font = await _get_font_path(session, tenant_id, "body")
    color = brand.primary_color if brand and brand.primary_color else "#FFFFFF"

    img = _render_persian_text(img, title, (40, 60), title_font, 64, color, w - 80)
    if subtitle:
        img = _render_persian_text(img, subtitle, (40, 160), body_font, 36, "#EEEEEE", w - 80)

    # شعار
    if brand and brand.slogan:
        img = _render_persian_text(img, brand.slogan, (40, h - 100), body_font, 24, "#CCCCCC", w - 80)

    buf = io.BytesIO()
    img.save(buf, format="PNG", quality=95)
    buf.seek(0)

    fname = f"poster_{size_preset}.png"
    return buf, fname, "✅ پوستر آماده شد."


# ═══════════════════════════════════════
# پست اسلایدی
# ═══════════════════════════════════════

async def generate_slide_post(session: AsyncSession, tenant_id: int,
                                slides_data: list[dict],
                                size: str = "post",
                                creativity: int = 30) -> tuple[list[tuple[io.BytesIO, str]], str]:
    """
    پست اسلایدی — هر slide: {title, subtitle, bg_prompt?}
    Returns: ([(buf, fname), ...], message)
    """
    files = []
    w, h = SIZE_PRESETS.get(size, (1080, 1080))

    for i, slide in enumerate(slides_data, 1):
        buf, fname, msg = await generate_poster(
            session, tenant_id,
            title=slide.get("title", ""),
            subtitle=slide.get("subtitle", ""),
            size_preset=size,
            creativity=creativity,
            bg_prompt=slide.get("bg_prompt"),
        )
        if buf:
            files.append((buf, f"slide_{i}.png"))

    if not files:
        return [], "⚠️ هیچ اسلایدی تولید نشد."

    return files, f"✅ {len(files)} اسلاید آماده شد."


# ═══════════════════════════════════════
# کاتالوگ PDF
# ═══════════════════════════════════════

async def generate_catalog(session: AsyncSession, tenant_id: int,
                            product_ids: list[int] = None,
                            title: str = "کاتالوگ محصولات") -> tuple[io.BytesIO | None, str, str]:
    """کاتالوگ PDF از محصولات."""
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A4

    if product_ids:
        products = []
        for pid in product_ids:
            p = await session.get(Product, pid)
            if p and p.tenant_id == tenant_id:
                products.append(p)
    else:
        products = (await session.scalars(
            select(Product).where(Product.tenant_id == tenant_id).limit(50)
        )).all()

    if not products:
        return None, "", "⚠️ محصولی پیدا نشد."

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    w, h = A4

    for i, prod in enumerate(products):
        if i > 0 and i % 3 == 0:
            c.showPage()

        y = h - 100 - (i % 3) * 250

        # عکس محصول
        photo = await session.scalar(
            select(EntityPhoto).where(
                EntityPhoto.tenant_id == tenant_id,
                EntityPhoto.entity_type == "product",
                EntityPhoto.entity_id == prod.id,
                EntityPhoto.is_primary == True,
            )
        )
        if photo:
            try:
                img = Image.open(io.BytesIO(photo.photo))
                img.thumbnail((150, 150))
                img_buf = io.BytesIO()
                img.save(img_buf, format="PNG")
                img_buf.seek(0)
                from reportlab.lib.utils import ImageReader
                c.drawImage(ImageReader(img_buf), 50, y - 150, 150, 150)
            except Exception:
                pass

        # اطلاعات
        c.setFont("Helvetica-Bold", 14)
        c.drawRightString(w - 50, y, prod.name or "")
        c.setFont("Helvetica", 11)
        if prod.sell_price:
            from app.utils.normalizer import format_amount
            c.drawRightString(w - 50, y - 25, f"{format_amount(int(prod.sell_price))}")
        if prod.category:
            c.drawRightString(w - 50, y - 45, prod.category)

    c.save()
    buf.seek(0)

    fname = f"catalog_{title}.pdf"
    return buf, fname, f"✅ کاتالوگ {len(products)} محصول آماده شد."


# ═══════════════════════════════════════
# برش عکس
# ═══════════════════════════════════════

async def crop_image(image_bytes: bytes, rows: int = 1, cols: int = 1,
                      output_size: tuple = None) -> list[tuple[io.BytesIO, str]]:
    """برش عکس به تکه‌های مساوی."""
    img = Image.open(io.BytesIO(image_bytes))
    w, h = img.size
    tile_w = w // cols
    tile_h = h // rows

    files = []
    for r in range(rows):
        for c in range(cols):
            box = (c * tile_w, r * tile_h, (c + 1) * tile_w, (r + 1) * tile_h)
            tile = img.crop(box)
            if output_size:
                tile = tile.resize(output_size)
            buf = io.BytesIO()
            tile.save(buf, format="PNG")
            buf.seek(0)
            files.append((buf, f"crop_{r+1}_{c+1}.png"))

    return files


# ═══════════════════════════════════════
# تمپلیت
# ═══════════════════════════════════════

async def save_template(session: AsyncSession, tenant_id: int,
                         name: str, size_preset: str = "post",
                         bg_prompt: str = None, creativity: int = 20,
                         fixed_elements: str = None, free_elements: str = None,
                         layout_json: str = None) -> str:
    w, h = SIZE_PRESETS.get(size_preset, (1080, 1080))
    tmpl = DesignTemplate(
        tenant_id=tenant_id, name=name, size_preset=size_preset,
        width=w, height=h, background_prompt=bg_prompt,
        creativity_percent=creativity,
        fixed_elements=fixed_elements, free_elements=free_elements,
        layout_json=layout_json,
    )
    session.add(tmpl)
    await session.commit()
    return f"✅ تمپلیت «{name}» ذخیره شد."


async def batch_design_from_template(session: AsyncSession, tenant_id: int,
                                       template_name: str,
                                       items: list[dict]) -> tuple[list[tuple[io.BytesIO, str]], str]:
    """طراحی دسته‌جمعی از تمپلیت."""
    tmpl = await session.scalar(
        select(DesignTemplate).where(
            DesignTemplate.tenant_id == tenant_id,
            DesignTemplate.name == template_name,
        )
    )
    if not tmpl:
        return [], f"⚠️ تمپلیت «{template_name}» پیدا نشد."

    files = []
    for item in items:
        buf, fname, msg = await generate_poster(
            session, tenant_id,
            title=item.get("title", ""),
            subtitle=item.get("subtitle", ""),
            size_preset=tmpl.size_preset,
            creativity=tmpl.creativity_percent,
            bg_prompt=tmpl.background_prompt,
            product_id=item.get("product_id"),
        )
        if buf:
            files.append((buf, item.get("filename", fname)))

    return files, f"✅ {len(files)} طرح از تمپلیت «{template_name}» آماده شد."


# ═══════════════════════════════════════
# بایگانی
# ═══════════════════════════════════════

async def archive_design(session: AsyncSession, tenant_id: int,
                           image_bytes: bytes, mime: str = "image/png",
                           task_name: str = None,
                           entity_type: str = None, entity_id: int = None,
                           template_id: int = None) -> str:
    history = DesignHistory(
        tenant_id=tenant_id, template_id=template_id,
        task_name=task_name, entity_type=entity_type, entity_id=entity_id,
        output_image=image_bytes, output_mime=mime, is_archived=True,
    )
    session.add(history)
    await session.commit()
    return "✅ طرح بایگانی شد."
