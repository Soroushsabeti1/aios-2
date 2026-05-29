"""
سرویس تولید PDF فارسی — راست‌چین، با لوگو و فونت فارسی.
از reportlab استفاده می‌کند. برای رندر درست حروف فارسی به
arabic-reshaper و python-bidi نیاز است (در requirements.txt).
"""
import io
import os
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# مسیر فونت‌ها
_BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
_FONT_DIR = os.path.join(_BASE, "assets", "fonts")
_FONT_REGULAR = os.path.join(_FONT_DIR, "Persian.ttf")
_FONT_BOLD = os.path.join(_FONT_DIR, "Persian-Bold.ttf")

_FONTS_REGISTERED = False

# تلاش برای import کتابخانه‌های شکل‌دهی فارsی
try:
    import arabic_reshaper
    from bidi.algorithm import get_display
    _RESHAPE_OK = True
except ImportError:
    _RESHAPE_OK = False


def _register_fonts():
    global _FONTS_REGISTERED
    if _FONTS_REGISTERED:
        return
    try:
        if os.path.exists(_FONT_REGULAR):
            pdfmetrics.registerFont(TTFont("Persian", _FONT_REGULAR))
        if os.path.exists(_FONT_BOLD):
            pdfmetrics.registerFont(TTFont("Persian-Bold", _FONT_BOLD))
        _FONTS_REGISTERED = True
    except Exception:
        pass


def _fa(text: str) -> str:
    """شکل‌دهی متن فارسی برای نمایش درست (اتصال حروف + راست‌چین)."""
    if text is None:
        return ""
    text = str(text)
    if _RESHAPE_OK:
        try:
            reshaped = arabic_reshaper.reshape(text)
            return get_display(reshaped)
        except Exception:
            return text
    return text


def _font(bold=False):
    if bold and _FONTS_REGISTERED:
        return "Persian-Bold"
    if _FONTS_REGISTERED:
        return "Persian"
    return "Helvetica-Bold" if bold else "Helvetica"


class PersianPDF:
    """سازنده‌ی PDF فارسی راست‌چین."""

    def __init__(self, title: str = "گزارش"):
        _register_fonts()
        self.buf = io.BytesIO()
        self.c = canvas.Canvas(self.buf, pagesize=A4)
        self.width, self.height = A4
        self.margin = 20 * mm
        self.y = self.height - self.margin
        self.title = title

    def _check_page(self, needed=15 * mm):
        if self.y < self.margin + needed:
            self.c.showPage()
            self.y = self.height - self.margin

    def header(self, business_name: str, logo_bytes: bytes = None,
               subtitle: str = None):
        """سربرگ با لوگو و نام فروشگاه."""
        # لوگو سمت راست
        if logo_bytes:
            try:
                from reportlab.lib.utils import ImageReader
                img = ImageReader(io.BytesIO(logo_bytes))
                self.c.drawImage(
                    img, self.width - self.margin - 25 * mm, self.y - 22 * mm,
                    width=25 * mm, height=25 * mm, mask="auto",
                    preserveAspectRatio=True,
                )
            except Exception:
                pass

        # نام فروشگاه (راست‌چین)
        self.c.setFont(_font(bold=True), 18)
        self.c.setFillColor(colors.HexColor("#1F2937"))
        self.c.drawRightString(
            self.width - self.margin - 30 * mm, self.y - 8 * mm, _fa(business_name)
        )

        # عنوان گزارش
        self.c.setFont(_font(bold=True), 14)
        self.c.setFillColor(colors.HexColor("#3B82F6"))
        self.c.drawRightString(
            self.width - self.margin - 30 * mm, self.y - 16 * mm, _fa(self.title)
        )

        if subtitle:
            self.c.setFont(_font(), 9)
            self.c.setFillColor(colors.HexColor("#6B7280"))
            self.c.drawRightString(
                self.width - self.margin - 30 * mm, self.y - 22 * mm, _fa(subtitle)
            )

        # تاریخ تولید (چپ)
        self.c.setFont(_font(), 8)
        self.c.setFillColor(colors.HexColor("#9CA3AF"))
        self.c.drawString(
            self.margin, self.y - 8 * mm,
            datetime.now().strftime("%Y/%m/%d - %H:%M"),
        )

        self.y -= 30 * mm
        # خط جداکننده
        self.c.setStrokeColor(colors.HexColor("#E5E7EB"))
        self.c.line(self.margin, self.y, self.width - self.margin, self.y)
        self.y -= 8 * mm

    def section(self, title: str):
        """عنوان بخش."""
        self._check_page()
        self.c.setFont(_font(bold=True), 12)
        self.c.setFillColor(colors.HexColor("#1F2937"))
        self.c.drawRightString(self.width - self.margin, self.y, _fa(title))
        self.y -= 7 * mm

    def line_item(self, label: str, value: str = ""):
        """یک خط متن: برچسب راست، مقدار چپ‌تر."""
        self._check_page()
        self.c.setFont(_font(), 10)
        self.c.setFillColor(colors.HexColor("#374151"))
        self.c.drawRightString(self.width - self.margin, self.y, _fa(label))
        if value:
            self.c.setFont(_font(bold=True), 10)
            self.c.drawString(self.margin, self.y, _fa(value))
        self.y -= 6 * mm

    def table(self, headers: list[str], rows: list[list]):
        """جدول راست‌چین."""
        self._check_page(30 * mm)
        n_cols = len(headers)
        usable = self.width - 2 * self.margin
        col_w = usable / n_cols
        row_h = 8 * mm

        # هدر
        self.c.setFillColor(colors.HexColor("#3B82F6"))
        self.c.rect(self.margin, self.y - row_h, usable, row_h, fill=1, stroke=0)
        self.c.setFont(_font(bold=True), 9)
        self.c.setFillColor(colors.white)
        for i, h in enumerate(headers):
            # ستون‌ها از راست به چپ
            x_center = self.width - self.margin - (i + 0.5) * col_w
            self.c.drawCentredString(x_center, self.y - row_h + 2.5 * mm, _fa(h))
        self.y -= row_h

        # ردیف‌ها
        self.c.setFont(_font(), 9)
        for r_idx, row in enumerate(rows):
            self._check_page(row_h + 5 * mm)
            if r_idx % 2 == 1:
                self.c.setFillColor(colors.HexColor("#F9FAFB"))
                self.c.rect(self.margin, self.y - row_h, usable, row_h, fill=1, stroke=0)
            self.c.setFillColor(colors.HexColor("#374151"))
            for i, cell in enumerate(row):
                x_center = self.width - self.margin - (i + 0.5) * col_w
                self.c.drawCentredString(x_center, self.y - row_h + 2.5 * mm, _fa(str(cell)))
            # خط زیر ردیف
            self.c.setStrokeColor(colors.HexColor("#E5E7EB"))
            self.c.line(self.margin, self.y - row_h, self.width - self.margin, self.y - row_h)
            self.y -= row_h
        self.y -= 5 * mm

    def spacer(self, mm_height=5):
        self.y -= mm_height * mm

    def footer_note(self, text: str):
        """یادداشت پایانی."""
        self._check_page()
        self.c.setFont(_font(), 8)
        self.c.setFillColor(colors.HexColor("#9CA3AF"))
        self.c.drawCentredString(self.width / 2, self.margin / 2, _fa(text))

    def build(self) -> io.BytesIO:
        self.c.save()
        self.buf.seek(0)
        return self.buf


async def make_report_pdf(business_name: str, report_title: str,
                          sections: list[dict], logo_bytes: bytes = None,
                          subtitle: str = None) -> io.BytesIO:
    """
    ساخت PDF گزارش عمومی.
    sections: لیستی از {"type": "lines"/"table", "title": ..., "data": ...}
      - lines: data = [(label, value), ...]
      - table: data = {"headers": [...], "rows": [[...], ...]}
    """
    pdf = PersianPDF(title=report_title)
    pdf.header(business_name, logo_bytes, subtitle)

    for sec in sections:
        if sec.get("title"):
            pdf.section(sec["title"])
        if sec["type"] == "lines":
            for item in sec["data"]:
                if isinstance(item, (list, tuple)):
                    pdf.line_item(item[0], item[1] if len(item) > 1 else "")
                else:
                    pdf.line_item(str(item))
        elif sec["type"] == "table":
            pdf.table(sec["data"]["headers"], sec["data"]["rows"])
        pdf.spacer(4)

    pdf.footer_note("تولید‌شده توسط دستیار هوشمند کسب‌وکار")
    return pdf.build()


async def make_invoice_pdf(session, tenant_id: int, invoice_display_id: str):
    """PDF فاکتور فارسی."""
    from sqlalchemy import select
    from app.database.models.business import Invoice, InvoiceItem
    from app.database.models.tenant import Tenant
    from app.utils.normalizer import format_amount
    from app.utils.jalali import to_jalali_str

    invoice = await session.scalar(
        select(Invoice).where(Invoice.tenant_id == tenant_id,
                              Invoice.display_id == invoice_display_id)
    )
    if not invoice:
        return None, None, f"فاکتور {invoice_display_id} پیدا نشد."

    tenant = await session.get(Tenant, tenant_id)
    items = (await session.scalars(
        select(InvoiceItem).where(InvoiceItem.invoice_id == invoice.id)
    )).all()

    status_labels = {"draft": "پیش‌فاکتور", "confirmed": "تأیید‌شده",
                     "paid": "پرداخت‌شده", "cancelled": "کنسل"}

    pdf = PersianPDF(title=f"فاکتور {invoice.display_id}")
    pdf.header(
        tenant.name if tenant else "فروشگاه",
        tenant.logo if tenant else None,
        subtitle=(tenant.phone or "") if tenant else "",
    )

    pdf.line_item(f"وضعیت: {status_labels.get(invoice.status, invoice.status)}")
    pdf.line_item(f"مشتری: {invoice.customer_name or '—'}")
    pdf.line_item(f"تاریخ: {to_jalali_str(invoice.invoice_date) if invoice.invoice_date else '—'}")
    pdf.spacer(3)

    headers = ["ردیف", "نام کالا", "تعداد", "فی", "جمع"]
    rows = []
    for i, it in enumerate(items, 1):
        rows.append([
            i, it.product_name, it.quantity,
            format_amount(int(it.unit_price)),
            format_amount(int(it.total_price)),
        ])
    pdf.table(headers, rows)

    pdf.line_item("جمع کل:", format_amount(int(invoice.total)))
    if invoice.discount:
        pdf.line_item("تخفیف:", format_amount(int(invoice.discount)))
    if invoice.tax:
        pdf.line_item("مالیات:", format_amount(int(invoice.tax)))
    pdf.line_item("مبلغ نهایی:", format_amount(int(invoice.final_amount)))
    if invoice.paid:
        pdf.line_item("پرداخت‌شده:", format_amount(int(invoice.paid)))

    pdf.spacer(5)
    if tenant and (tenant.card_number or tenant.sheba):
        if tenant.card_number:
            pdf.line_item(f"شماره کارت: {tenant.card_number}")
        if tenant.sheba:
            pdf.line_item(f"شبا: {tenant.sheba}")
        if tenant.account_holder:
            pdf.line_item(f"به نام: {tenant.account_holder}")

    pdf.spacer(10)
    pdf.line_item("مهر و امضای فروشنده:                            امضای خریدار:")

    pdf.footer_note("این فاکتور پس از مهر و امضا معتبر است.")
    fname = f"فاکتور_{invoice.display_id}.pdf"
    return pdf.build(), fname, None


async def make_data_report_pdf(session, tenant_id: int, report_type: str,
                               period: str = "month"):
    """PDF گزارش‌های داده‌ای: مالی/فروش/بدهکاران/انبار/هفتگی."""
    from app.database.models.tenant import Tenant
    from app.modules.reports import advanced_reports, alerts_service

    tenant = await session.get(Tenant, tenant_id)
    biz_name = tenant.name if tenant else "فروشگاه"
    logo = tenant.logo if tenant else None

    titles = {
        "financial": "گزارش مالی", "sales": "گزارش فروش",
        "debtors": "گزارش بدهکاران", "inventory": "گزارش انبار",
        "weekly": "گزارش هفتگی",
    }
    title = titles.get(report_type, "گزارش")

    # متن گزارش رو از سرویس‌های موجود می‌گیریم و خط‌به‌خط می‌چینیم
    if report_type == "financial":
        text = await advanced_reports.financial_report(session, tenant_id, period=period)
    elif report_type == "sales":
        text = await advanced_reports.sales_report(session, tenant_id, period=period)
    elif report_type == "debtors":
        text = await advanced_reports.debtors_report(session, tenant_id)
    elif report_type == "inventory":
        text = await advanced_reports.inventory_report(session, tenant_id)
    elif report_type == "weekly":
        text = await alerts_service.generate_weekly_report(session, tenant_id)
    else:
        text = "گزارشی یافت نشد."

    # تبدیل متن به خطوط
    lines = [ln for ln in text.split("\n") if ln.strip()]
    sections = [{"type": "lines", "title": None, "data": lines}]

    pdf_buf = await make_report_pdf(biz_name, title, sections, logo)
    fname = f"{title}.pdf"
    return pdf_buf, fname
