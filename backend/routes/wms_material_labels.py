"""
WMS — Material Label Printing (Non-Fabric)
Generate printable barcode labels untuk materials: trims, accessories, chemicals, packaging, etc.

Endpoints:
  GET  /api/wms/materials/{material_id}/label-pdf    — single material label
  POST /api/wms/materials/labels/batch-pdf           — batch material labels
  
Label size: 90mm × 50mm (thermal printer compatible)
Barcode: Code128
"""

import io
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
    from barcode import Code128
    from barcode.writer import ImageWriter
    from PIL import Image as PILImage
    from reportlab.lib.utils import ImageReader
    REPORTLAB_OK = True
except ImportError:
    REPORTLAB_OK = False

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/wms/materials", tags=["wms-material-labels"])


def _now():
    return datetime.now(timezone.utc)


def _generate_barcode_image(code: str) -> io.BytesIO:
    """Generate Code128 barcode as PNG in memory."""
    buf = io.BytesIO()
    writer = ImageWriter()
    Code128(code, writer=writer).write(buf, options={
        "module_width": 0.35,
        "module_height": 10.0,
        "quiet_zone": 2.0,
        "text_distance": 2.0,
        "font_size": 6,
        "write_text": True
    })
    buf.seek(0)
    return buf


def _draw_material_label(material: dict, include_stock: bool = True) -> io.BytesIO:
    """
    Draw single material label (90mm × 50mm).
    
    Layout:
    ┌────────────────────────────────────┐
    │ CV. DEWI ADITYA - WAREHOUSE        │
    │ CODE: MAT-TRIM-001                 │
    │ Kancing Plastik Hitam 15mm         │
    │ Category: TRIM | UOM: pcs          │
    │ Stock: 5,000 pcs @ WH-B-R1-B3      │ (optional)
    │                                    │
    │   ||||||||||||||||||||||||||||     │ ← Barcode
    │   MAT-TRIM-001                     │
    └────────────────────────────────────┘
    """
    if not REPORTLAB_OK:
        raise HTTPException(500, "ReportLab/barcode library tidak tersedia")
    
    buf = io.BytesIO()
    W, H = 90 * mm, 50 * mm
    c = canvas.Canvas(buf, pagesize=(W, H))
    
    # Header
    c.setFont("Helvetica-Bold", 8)
    c.drawString(3 * mm, H - 7 * mm, "CV. DEWI ADITYA - WAREHOUSE")
    
    # Material Code
    c.setFont("Helvetica-Bold", 9)
    material_code = material.get('code') or material.get('material_code', 'N/A')
    c.drawString(3 * mm, H - 12 * mm, f"CODE: {material_code}")
    
    # Material Name
    c.setFont("Helvetica", 7)
    material_name = material.get('name') or material.get('material_name', '')
    # Truncate if too long
    if len(material_name) > 45:
        material_name = material_name[:42] + "..."
    c.drawString(3 * mm, H - 17 * mm, material_name)
    
    # Category & UOM
    category = material.get('category', 'MATERIAL')
    uom = material.get('uom', 'pcs')
    c.setFont("Helvetica", 6)
    c.drawString(3 * mm, H - 22 * mm, f"Category: {category} | UOM: {uom}")
    
    # Stock info (optional, jika include_stock=True dan data ada)
    if include_stock and 'stock_qty' in material:
        stock_qty = material.get('stock_qty', 0)
        location = material.get('location', '-')
        c.setFont("Helvetica", 6)
        c.drawString(3 * mm, H - 27 * mm, f"Stock: {stock_qty:,.0f} {uom} @ {location}")
    
    # Barcode
    try:
        barcode_buf = _generate_barcode_image(material_code)
        img = PILImage.open(barcode_buf)
        img_buf = io.BytesIO()
        img.save(img_buf, "PNG")
        img_buf.seek(0)
        c.drawImage(
            ImageReader(img_buf),
            3 * mm, 5 * mm,
            width=84 * mm, height=16 * mm,
            preserveAspectRatio=True
        )
    except Exception as e:
        log.warning(f"Barcode generation failed for {material_code}: {e}")
        c.setFont("Courier-Bold", 8)
        c.drawString(3 * mm, 10 * mm, f"[Barcode: {material_code}]")
    
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

@router.get("/{material_id}/label-pdf")
async def material_label_pdf(
    material_id: str,
    request: Request,
    token: Optional[str] = Query(None),
    include_stock: bool = Query(True, description="Include stock info in label")
):
    """
    Generate single material label PDF (90mm × 50mm).
    
    Query params:
      - token: optional JWT token (for direct browser download)
      - include_stock: include stock qty & location (default: true)
    
    Example:
      GET /api/wms/materials/mat-uuid-123/label-pdf?token=xxx&include_stock=true
    """
    await _auth_or_token(request, token)
    db = get_db()
    
    # Find material by ID or code
    material = await db.rahaza_materials.find_one(
        {"$or": [{"id": material_id}, {"code": material_id}]},
        {"_id": 0}
    )
    
    if not material:
        raise HTTPException(404, f"Material tidak ditemukan: {material_id}")
    
    # Optionally enrich with stock data
    if include_stock:
        # Get total stock across all locations
        stock_docs = await db.rahaza_material_stock.find(
            {"material_id": material.get('id')},
            {"_id": 0, "qty": 1, "location_id": 1}
        ).to_list(100)
        
        if stock_docs:
            total_stock = sum(s.get('qty', 0) for s in stock_docs)
            # RC-19: SSOT rahaza_material_stock pakai `location_id` (field `location` TIDAK ADA)
            # → resolve label posisi via wh_positions, fallback '-'
            main_loc_id = next((s.get('location_id') for s in stock_docs
                                if s.get('qty', 0) > 0 and s.get('location_id')), None)
            main_location = '-'
            if main_loc_id:
                pos = await db.wh_positions.find_one({"id": main_loc_id}, {"_id": 0, "label": 1, "barcode": 1})
                if pos:
                    main_location = pos.get('label') or pos.get('barcode') or '-'
            material['stock_qty'] = total_stock
            material['location'] = main_location
    
    # Generate PDF
    pdf_buf = _draw_material_label(material, include_stock=include_stock)
    
    filename = f"material-{material.get('code', material_id)}.pdf"
    return StreamingResponse(
        pdf_buf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


class BatchMaterialLabelsIn(BaseModel):
    material_ids: List[str]
    include_stock: bool = True


@router.post("/labels/batch-pdf")
async def batch_material_labels_pdf(data: BatchMaterialLabelsIn, request: Request):
    """
    Generate batch material labels PDF.
    Multiple labels arranged on A4 pages (3×3 = 9 labels per page).
    
    Request body:
    {
      "material_ids": ["mat-1", "mat-2", ...],
      "include_stock": true
    }
    
    Example:
      POST /api/wms/materials/labels/batch-pdf
      {
        "material_ids": ["MAT-TRIM-001", "MAT-TRIM-002", "MAT-ACC-001"],
        "include_stock": true
      }
    """
    await require_auth(request)
    
    if not data.material_ids:
        raise HTTPException(400, "material_ids tidak boleh kosong")
    
    if len(data.material_ids) > 100:
        raise HTTPException(400, "Maximum 100 materials per batch")
    
    db = get_db()
    
    # Fetch materials
    materials = await db.rahaza_materials.find(
        {"$or": [
            {"id": {"$in": data.material_ids}},
            {"code": {"$in": data.material_ids}}
        ]},
        {"_id": 0}
    ).to_list(100)
    
    if not materials:
        raise HTTPException(404, "Tidak ada material ditemukan")
    
    # Enrich with stock if requested
    if data.include_stock:
        material_ids = [m['id'] for m in materials if 'id' in m]
        stock_by_material = {}
        
        async for stock_doc in db.rahaza_material_stock.find(
            {"material_id": {"$in": material_ids}},
            {"_id": 0, "material_id": 1, "qty": 1, "location_id": 1}
        ):
            mat_id = stock_doc['material_id']
            if mat_id not in stock_by_material:
                stock_by_material[mat_id] = []
            stock_by_material[mat_id].append(stock_doc)
        
        # Add stock to materials — RC-19: location_id → label via wh_positions (batch)
        all_loc_ids = list({s.get('location_id') for docs_ in stock_by_material.values()
                            for s in docs_ if s.get('location_id')})
        pos_map = {}
        if all_loc_ids:
            async for pos in db.wh_positions.find(
                    {"id": {"$in": all_loc_ids}}, {"_id": 0, "id": 1, "label": 1, "barcode": 1}):
                pos_map[pos["id"]] = pos.get('label') or pos.get('barcode') or '-'
        for material in materials:
            mat_id = material.get('id')
            if mat_id in stock_by_material:
                stocks = stock_by_material[mat_id]
                total = sum(s.get('qty', 0) for s in stocks)
                loc_id = next((s.get('location_id') for s in stocks
                               if s.get('qty', 0) > 0 and s.get('location_id')), None)
                material['stock_qty'] = total
                material['location'] = pos_map.get(loc_id, '-')
    
    # Generate multi-page PDF with labels arranged in grid
    if not REPORTLAB_OK:
        raise HTTPException(500, "ReportLab tidak tersedia")
    
    from reportlab.lib.pagesizes import A4
    PAGE_W, PAGE_H = A4
    LABEL_W = 90 * mm
    LABEL_H = 50 * mm
    COLS = 3
    ROWS = 3
    LABELS_PER_PAGE = COLS * ROWS
    
    MARGIN_X = (PAGE_W - COLS * LABEL_W) / 2
    MARGIN_Y = (PAGE_H - ROWS * LABEL_H) / 2
    
    pdf_buf = io.BytesIO()
    c = canvas.Canvas(pdf_buf, pagesize=A4)
    c.setTitle(f"Material Labels Batch ({len(materials)} items)")
    
    for idx, material in enumerate(materials):
        col = idx % COLS
        row = (idx // COLS) % ROWS
        
        x = MARGIN_X + col * LABEL_W
        y = PAGE_H - MARGIN_Y - (row + 1) * LABEL_H
        
        # Draw individual label on canvas at (x, y)
        # We need to draw directly on the main canvas, not create separate PDF
        material_code = material.get('code') or material.get('material_code', 'N/A')
        material_name = material.get('name') or material.get('material_name', '')
        category = material.get('category', 'MATERIAL')
        uom = material.get('uom', 'pcs')
        
        # Border
        c.setStrokeColorRGB(0.85, 0.85, 0.85)
        c.setLineWidth(0.4)
        c.rect(x, y, LABEL_W, LABEL_H, stroke=1, fill=0)
        
        # Header
        c.setFont("Helvetica-Bold", 8)
        c.setFillColorRGB(0.2, 0.2, 0.2)
        c.drawString(x + 3*mm, y + LABEL_H - 7*mm, "CV. DEWI ADITYA")
        
        # Code
        c.setFont("Helvetica-Bold", 9)
        c.drawString(x + 3*mm, y + LABEL_H - 12*mm, f"CODE: {material_code}")
        
        # Name
        c.setFont("Helvetica", 7)
        if len(material_name) > 45:
            material_name = material_name[:42] + "..."
        c.drawString(x + 3*mm, y + LABEL_H - 17*mm, material_name)
        
        # Category
        c.setFont("Helvetica", 6)
        c.drawString(x + 3*mm, y + LABEL_H - 22*mm, f"{category} | {uom}")
        
        # Stock (if available)
        if data.include_stock and 'stock_qty' in material:
            stock_qty = material.get('stock_qty', 0)
            location = material.get('location', '-')
            c.drawString(x + 3*mm, y + LABEL_H - 27*mm, f"Stock: {stock_qty:,.0f} {uom} @ {location}")
        
        # Barcode
        try:
            barcode_buf = _generate_barcode_image(material_code)
            img = PILImage.open(barcode_buf)
            img_buf = io.BytesIO()
            img.save(img_buf, "PNG")
            img_buf.seek(0)
            c.drawImage(
                ImageReader(img_buf),
                x + 3*mm, y + 5*mm,
                width=84*mm, height=16*mm,
                preserveAspectRatio=True
            )
        except Exception as e:
            log.warning(f"Barcode failed: {e}")
            c.setFont("Courier", 6)
            c.drawString(x + 3*mm, y + 10*mm, material_code)
        
        # Page break after full page
        if (idx + 1) % LABELS_PER_PAGE == 0 and (idx + 1) < len(materials):
            c.showPage()
    
    c.save()
    pdf_buf.seek(0)
    
    return StreamingResponse(
        pdf_buf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="material_labels_batch_{len(materials)}.pdf"'}
    )
