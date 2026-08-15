"""
WMS — Finished Goods (FG) Label Printing
Generate printable labels untuk produk jadi dengan QR code.

Endpoints:
  GET  /api/wms/fg/{fg_id}/label-pdf        — single FG label
  POST /api/wms/fg/labels/batch-pdf         — batch FG labels
  
Label size: 100mm × 70mm (larger for more info)
Includes: QR Code (for mobile scan to product detail)
"""

import io
import json
import logging
from typing import List, Optional
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Request, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from database import get_db
from auth import require_auth, verify_token_str

try:
    from reportlab.pdfgen import canvas
    from reportlab.lib.units import mm
    from reportlab.lib.pagesizes import A4
    from barcode import Code128
    from barcode.writer import ImageWriter
    import qrcode
    from PIL import Image as PILImage
    from reportlab.lib.utils import ImageReader
    REPORTLAB_OK = True
except ImportError:
    REPORTLAB_OK = False

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/wms/fg", tags=["wms-fg-labels"])


def _now():
    return datetime.now(timezone.utc)


def _generate_qr_code(data: str) -> io.BytesIO:
    """Generate QR code as PNG in memory."""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=2,
    )
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, "PNG")
    buf.seek(0)
    return buf


def _generate_barcode_image(code: str) -> io.BytesIO:
    """Generate Code128 barcode as PNG in memory."""
    buf = io.BytesIO()
    writer = ImageWriter()
    Code128(code, writer=writer).write(buf, options={
        "module_width": 0.3,
        "module_height": 8.0,
        "quiet_zone": 2.0,
        "text_distance": 2.0,
        "font_size": 6,
        "write_text": True
    })
    buf.seek(0)
    return buf


def _draw_fg_label(fg: dict) -> io.BytesIO:
    """
    Draw single FG label (100mm × 70mm).
    
    Layout:
    ┌────────────────────────────────────────┐
    │ CV. DEWI ADITYA                        │
    │ FINISHED GOODS                         │
    │                                        │
    │ SKU: KBT-MODEL-A-M                     │
    │ Kemeja Batik Model A - Size M          │
    │ Style: KBT-A | Color: Navy             │
    │                                        │
    │ Batch: B-2026-05-27-001                │
    │ Carton: 50 pcs | QC: PASS              │
    │                                        │
    │ [QR Code]      ||||||||||||||||        │
    │                SKU-CODE-128            │
    └────────────────────────────────────────┘
    """
    if not REPORTLAB_OK:
        raise HTTPException(500, "ReportLab/qrcode library tidak tersedia")
    
    buf = io.BytesIO()
    W, H = 100 * mm, 70 * mm
    c = canvas.Canvas(buf, pagesize=(W, H))
    
    # Header
    c.setFont("Helvetica-Bold", 10)
    c.drawString(3 * mm, H - 8 * mm, "CV. DEWI ADITYA")
    c.setFont("Helvetica", 7)
    c.drawString(3 * mm, H - 13 * mm, "FINISHED GOODS")
    
    # SKU Code (prominent)
    c.setFont("Helvetica-Bold", 11)
    sku_code = fg.get('sku') or fg.get('sku_code', 'N/A')
    c.drawString(3 * mm, H - 20 * mm, f"SKU: {sku_code}")
    
    # Product Name
    c.setFont("Helvetica", 8)
    product_name = fg.get('product_name', '')
    if len(product_name) > 40:
        product_name = product_name[:37] + "..."
    c.drawString(3 * mm, H - 26 * mm, product_name)
    
    # Style & Color
    c.setFont("Helvetica", 7)
    style = fg.get('style_code', '-')
    color = fg.get('color', '-')
    c.drawString(3 * mm, H - 31 * mm, f"Style: {style} | Color: {color}")
    
    # Batch Number
    c.setFont("Helvetica-Bold", 7)
    batch = fg.get('batch_number', '-')
    c.drawString(3 * mm, H - 37 * mm, f"Batch: {batch}")
    
    # Carton Qty & QC Status
    c.setFont("Helvetica", 7)
    carton_qty = fg.get('carton_qty', 0)
    qc_status = fg.get('qc_status', 'PENDING')
    c.drawString(3 * mm, H - 42 * mm, f"Carton: {carton_qty} pcs | QC: {qc_status}")
    
    # QR Code (left side, bottom)
    try:
        # QR code contains JSON data for mobile scanning
        qr_data = json.dumps({
            "type": "fg",
            "sku": sku_code,
            "batch": batch,
            "product": product_name,
            "qty": carton_qty,
            "timestamp": _now().isoformat()
        })
        qr_buf = _generate_qr_code(qr_data)
        qr_img = PILImage.open(qr_buf)
        qr_img_buf = io.BytesIO()
        qr_img.save(qr_img_buf, "PNG")
        qr_img_buf.seek(0)
        
        # Draw QR code (25mm × 25mm)
        c.drawImage(
            ImageReader(qr_img_buf),
            3 * mm, 3 * mm,
            width=25 * mm, height=25 * mm,
            preserveAspectRatio=True
        )
    except Exception as e:
        log.warning(f"QR code generation failed: {e}")
        c.setFont("Courier", 6)
        c.drawString(3 * mm, 15 * mm, "[QR N/A]")
    
    # Barcode (right side, bottom) - SKU barcode
    try:
        barcode_buf = _generate_barcode_image(sku_code)
        barcode_img = PILImage.open(barcode_buf)
        barcode_img_buf = io.BytesIO()
        barcode_img.save(barcode_img_buf, "PNG")
        barcode_img_buf.seek(0)
        
        # Draw barcode
        c.drawImage(
            ImageReader(barcode_img_buf),
            32 * mm, 5 * mm,
            width=65 * mm, height=20 * mm,
            preserveAspectRatio=True
        )
    except Exception as e:
        log.warning(f"Barcode generation failed: {e}")
        c.setFont("Courier-Bold", 8)
        c.drawString(32 * mm, 15 * mm, f"[Barcode: {sku_code}]")
    
    c.save()
    buf.seek(0)
    return buf


async def _auth_or_token(request: Request, token: Optional[str] = None):
    """Auth via header or token query param."""
    if token:
        user = verify_token_str(token)
        if user:
            return user
    return await require_auth(request)


# ══════════════════════════════════════════════════════════════════════════════
# Routes
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/{fg_id}/label-pdf")
async def fg_label_pdf(
    fg_id: str,
    request: Request,
    token: Optional[str] = Query(None)
):
    """
    Generate single FG label PDF (100mm × 70mm).
    
    Query params:
      - token: optional JWT token (for direct browser download)
    
    Example:
      GET /api/wms/fg/fg-uuid-123/label-pdf?token=xxx
      
    FG data can come from:
      - rahaza_fg_matrix (finished goods matrix)
      - Custom FG collection
    """
    await _auth_or_token(request, token)
    db = get_db()
    
    # Try find in FG matrix first
    fg = await db.rahaza_fg_matrix.find_one(
        {"$or": [{"id": fg_id}, {"sku": fg_id}, {"sku_code": fg_id}]},
        {"_id": 0}
    )
    
    if not fg:
        raise HTTPException(404, f"Finished Good tidak ditemukan: {fg_id}")
    
    # Generate PDF
    pdf_buf = _draw_fg_label(fg)
    
    filename = f"fg-{fg.get('sku', fg_id)}.pdf"
    return StreamingResponse(
        pdf_buf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


class BatchFGLabelsIn(BaseModel):
    fg_ids: List[str]
    
    class Config:
        json_schema_extra = {
            "example": {
                "fg_ids": ["SKU-001", "SKU-002", "SKU-003"]
            }
        }


@router.post("/labels/batch-pdf")
async def batch_fg_labels_pdf(data: BatchFGLabelsIn, request: Request):
    """
    Generate batch FG labels PDF.
    Multiple labels arranged on A4 pages (2×3 = 6 labels per page).
    
    Request body:
    {
      "fg_ids": ["SKU-001", "SKU-002", ...]
    }
    
    Each label is 100mm × 70mm, so we can fit 2 columns × 3 rows per A4.
    """
    await require_auth(request)
    
    if not data.fg_ids:
        raise HTTPException(400, "fg_ids tidak boleh kosong")
    
    if len(data.fg_ids) > 100:
        raise HTTPException(400, "Maximum 100 FG items per batch")
    
    db = get_db()
    
    # Fetch FG items
    fg_items = await db.rahaza_fg_matrix.find(
        {"$or": [
            {"id": {"$in": data.fg_ids}},
            {"sku": {"$in": data.fg_ids}},
            {"sku_code": {"$in": data.fg_ids}}
        ]},
        {"_id": 0}
    ).to_list(100)
    
    if not fg_items:
        raise HTTPException(404, "Tidak ada FG items ditemukan")
    
    # Generate multi-page PDF with labels arranged in grid
    if not REPORTLAB_OK:
        raise HTTPException(500, "ReportLab tidak tersedia")
    
    PAGE_W, PAGE_H = A4
    LABEL_W = 100 * mm
    LABEL_H = 70 * mm
    COLS = 2
    ROWS = 3
    LABELS_PER_PAGE = COLS * ROWS
    
    MARGIN_X = (PAGE_W - COLS * LABEL_W) / 2
    MARGIN_Y = (PAGE_H - ROWS * LABEL_H) / 2
    
    pdf_buf = io.BytesIO()
    c = canvas.Canvas(pdf_buf, pagesize=A4)
    c.setTitle(f"FG Labels Batch ({len(fg_items)} items)")
    
    for idx, fg in enumerate(fg_items):
        col = idx % COLS
        row = (idx // COLS) % ROWS
        
        x = MARGIN_X + col * LABEL_W
        y = PAGE_H - MARGIN_Y - (row + 1) * LABEL_H
        
        # Draw label border
        c.setStrokeColorRGB(0.85, 0.85, 0.85)
        c.setLineWidth(0.4)
        c.rect(x, y, LABEL_W, LABEL_H, stroke=1, fill=0)
        
        # Header
        c.setFont("Helvetica-Bold", 10)
        c.setFillColorRGB(0.2, 0.2, 0.2)
        c.drawString(x + 3*mm, y + LABEL_H - 8*mm, "CV. DEWI ADITYA")
        c.setFont("Helvetica", 7)
        c.drawString(x + 3*mm, y + LABEL_H - 13*mm, "FINISHED GOODS")
        
        # SKU
        c.setFont("Helvetica-Bold", 11)
        sku_code = fg.get('sku') or fg.get('sku_code', 'N/A')
        c.drawString(x + 3*mm, y + LABEL_H - 20*mm, f"SKU: {sku_code}")
        
        # Product name
        c.setFont("Helvetica", 8)
        product_name = fg.get('product_name', '')
        if len(product_name) > 40:
            product_name = product_name[:37] + "..."
        c.drawString(x + 3*mm, y + LABEL_H - 26*mm, product_name)
        
        # Style & Color
        c.setFont("Helvetica", 7)
        style = fg.get('style_code', '-')
        color = fg.get('color', '-')
        c.drawString(x + 3*mm, y + LABEL_H - 31*mm, f"Style: {style} | Color: {color}")
        
        # Batch
        c.setFont("Helvetica-Bold", 7)
        batch = fg.get('batch_number', '-')
        c.drawString(x + 3*mm, y + LABEL_H - 37*mm, f"Batch: {batch}")
        
        # Carton & QC
        c.setFont("Helvetica", 7)
        carton_qty = fg.get('carton_qty', 0)
        qc_status = fg.get('qc_status', 'PENDING')
        c.drawString(x + 3*mm, y + LABEL_H - 42*mm, f"Carton: {carton_qty} pcs | QC: {qc_status}")
        
        # QR Code
        try:
            qr_data = json.dumps({
                "type": "fg",
                "sku": sku_code,
                "batch": batch,
                "product": product_name,
                "qty": carton_qty
            })
            qr_buf = _generate_qr_code(qr_data)
            qr_img = PILImage.open(qr_buf)
            qr_img_buf = io.BytesIO()
            qr_img.save(qr_img_buf, "PNG")
            qr_img_buf.seek(0)
            c.drawImage(
                ImageReader(qr_img_buf),
                x + 3*mm, y + 3*mm,
                width=25*mm, height=25*mm,
                preserveAspectRatio=True
            )
        except Exception as e:
            log.warning(f"QR failed: {e}")
        
        # Barcode
        try:
            barcode_buf = _generate_barcode_image(sku_code)
            barcode_img = PILImage.open(barcode_buf)
            barcode_img_buf = io.BytesIO()
            barcode_img.save(barcode_img_buf, "PNG")
            barcode_img_buf.seek(0)
            c.drawImage(
                ImageReader(barcode_img_buf),
                x + 32*mm, y + 5*mm,
                width=65*mm, height=20*mm,
                preserveAspectRatio=True
            )
        except Exception as e:
            log.warning(f"Barcode failed: {e}")
        
        # Page break
        if (idx + 1) % LABELS_PER_PAGE == 0 and (idx + 1) < len(fg_items):
            c.showPage()
    
    c.save()
    pdf_buf.seek(0)
    
    return StreamingResponse(
        pdf_buf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="fg_labels_batch_{len(fg_items)}.pdf"'}
    )


@router.post("/label-pdf/custom")
async def custom_fg_label_pdf(fg: dict, request: Request):
    """
    Generate FG label from custom data (no DB lookup).
    Useful for ad-hoc label printing.
    
    Request body: FG object with required fields:
    {
      "sku": "SKU-001",
      "product_name": "Kemeja Batik Model A - Size M",
      "style_code": "KBT-A",
      "color": "Navy",
      "batch_number": "B-2026-05-27-001",
      "carton_qty": 50,
      "qc_status": "PASS"
    }
    """
    await require_auth(request)
    
    if not fg.get('sku'):
        raise HTTPException(400, "Field 'sku' wajib diisi")
    
    # Generate PDF
    pdf_buf = _draw_fg_label(fg)
    
    filename = f"fg-custom-{fg['sku']}.pdf"
    return StreamingResponse(
        pdf_buf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )
