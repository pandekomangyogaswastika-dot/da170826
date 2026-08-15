"""
PORTAL CUTTING — Roll Kain ➜ Kain Pola (Potongan)
CV. Dewi Aditya ERP · FASE IA-4

MENGAPA MODUL INI ADA
---------------------
Di DA, kain datang sebagai ROLL (satuan Kg / Yard / Meter). Sebelum bisa dijahit,
roll harus dipotong jadi KAIN POLA ("potongan") per style + warna + size (satuan pcs).
Potongan inilah yang:
  · dihitung sebagai MATERIAL (bukan barang jadi) di gudang,
  · dipakai sebagai komponen BOM job produksi internal,
  · dikirim ke CMT lewat "Kirim Material CMT" / "Pengeluaran Material".
Sebelum modul ini, langkah tersebut tidak tercatat di sistem sehingga stok kain
tidak pernah berkurang dan potongan tidak pernah punya identitas stok.

KEPUTUSAN DESAIN (hasil pemetaan database — bukan tebakan)
----------------------------------------------------------
1. TIDAK membuat gudang/stok baru. Semua mutasi lewat SSOT `core.stock_service`
   (`issue()` untuk kain, `add()` untuk potongan) sehingga:
   `rahaza_material_stock` + `rahaza_stock_ledger` tetap satu-satunya kebenaran,
   dan seluruh laporan stok/valuasi lama otomatis ikut benar.
2. Output potongan = DOKUMEN BARU di `rahaza_materials` (master material) —
   sesuai keputusan owner. Ditandai `is_cut_panel: True`, `type: "fabric"`,
   `category: "POTONGAN"`, `unit: "pcs"`, plus `source_material_id` ke kain asalnya
   sehingga ketelusuran roll ➜ potongan tidak putus.
   Kode dibangkitkan deterministik: `CUT-<STYLE>-<WARNA>-<SIZE>`; bila sudah ada,
   dipakai ulang (idempoten) — mencegah duplikat master.
3. Roll fisik (`wh_fabric_rolls`) OPSIONAL. Bila dipilih, sisa roll (`remaining_kg`
   / `remaining_m`) ikut dikurangi + dicatat di `wh_fabric_roll_movements`, TANPA
   memotong stok material dua kali (potong stok material hanya sekali, di sini).
4. HPP: saat COMPLETE, harga satuan potongan dihitung
   = (qty kain terpakai × unit_cost kain) / qty potongan jadi, lalu ditulis ke
   `unit_cost` master potongan supaya jurnal persediaan & HPP hilir tetap benar.

STATE MACHINE
-------------
   draft ──start──▶ in_progress ──complete──▶ completed
     │                   │
     └───cancel──────────┘   (cancel hanya bila belum ada progres)

Koleksi baru (tidak bentrok dengan koleksi manapun yang sudah ada — sudah diverifikasi):
  · cutting_orders
  · cutting_progress
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Request

from auth import require_auth, serialize_doc, log_activity
from core import stock_service
from core import uom as _uom_core   # SSOT konversi satuan (operator boleh input per rol/kemasan)
from core import bom_uom as _bom_uom  # cakupan lebar: kemasan + global + kain (gsm & lebar)
from core.stock_service import InsufficientStock
from database import get_db
from utils.counters import gen_prefixed_number, resolve_master_code

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/cutting", tags=["cutting"])

ORDERS = "cutting_orders"
PROGRESS = "cutting_progress"

STATUS_DRAFT = "draft"
STATUS_IN_PROGRESS = "in_progress"
STATUS_COMPLETED = "completed"
STATUS_CANCELLED = "cancelled"

# Satuan kain yang wajar jadi INPUT cutting (roll).
INPUT_UNITS = {"kg", "gram", "m", "cm", "yard", "inch", "rol", "gulung", "bal"}
OUTPUT_UNIT = "pcs"
OUTPUT_CATEGORY = "POTONGAN"


async def ensure_cutting_indexes():
    """Indeks + PEMBUATAN koleksi cutting saat startup.

    Kenapa dipanggil di startup (bukan lazy saat order pertama dibuat):
    `mongodump` hanya menyalin koleksi yang SUDAH ADA. Kalau koleksi cutting baru
    lahir saat transaksi pertama, backup yang diambil sebelum itu tidak memuatnya
    dan proses restore akan menghapus jejak modul ini. Membuat indeks di startup
    memastikan `cutting_orders` & `cutting_progress` selalu ikut ter-backup.
    """
    db = get_db()
    await db[ORDERS].create_index("id", unique=True)
    await db[ORDERS].create_index("number", unique=True)
    await db[ORDERS].create_index("status")
    await db[ORDERS].create_index("input_material_id")
    await db[ORDERS].create_index("output_material_id")
    await db[PROGRESS].create_index("id", unique=True)
    await db[PROGRESS].create_index("cutting_order_id")
    log.info("Cutting indexes created (cutting_orders, cutting_progress)")


def _uid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _f(v, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _slug(v: str, maxlen: int = 14) -> str:
    out = "".join(ch for ch in (v or "").upper() if ch.isalnum() or ch in (" ", "-"))
    out = "-".join(p for p in out.replace(" ", "-").split("-") if p)
    return out[:maxlen] or "NA"


async def _require_cutting_user(request: Request) -> dict:
    """Cutting = pekerjaan gudang/produksi.

    2026-08-06: gerbang izin dipusatkan ke `routes.shared.require_perm`
    (model fallback aman) supaya owner bisa memberi/mencabut hak lewat layar
    "Peran & Hak Akses" tanpa mengubah kode.
    """
    from routes.shared import require_perm
    return await require_perm(
        request, "cutting.manage", "cutting.input", "warehouse.manage",
        legacy_roles=(
            "spv_cuting", "operator_cuting",
            "supervisor_produksi", "admin_produksi", "supervisor",
            "admin_gudang",
        ),
        message="Akses ditolak: butuh izin cutting (cutting.manage / cutting.input).",
    )


async def _actor(user: dict) -> dict:
    return {"id": user.get("id"), "name": user.get("name", "")}


async def _get_order(db, oid: str) -> dict:
    doc = await db[ORDERS].find_one({"id": oid}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Cutting order tidak ditemukan.")
    return doc


async def _stock_locations(db, material_id: str) -> list[dict]:
    """Daftar lokasi yang MEMANG punya stok untuk material ini, urut qty terbesar.

    Kenapa perlu: stok tidak disimpan global melainkan per (material, lokasi).
    Bug nyata yang ditemukan QA: cutting dibuat dengan lokasi bawaan sistem
    ("Gedung Produksi") padahal saldo kain berada di "Gudang Lantai 1/Area Gudang",
    sehingga validasi start LULUS (cek total lintas lokasi) tapi pemotongan stok
    GAGAL (cek per-lokasi). Sejak sekarang lokasi order selalu diarahkan ke lokasi
    yang benar-benar memegang stok.
    """
    from core.stock_schema import read_qty
    rows = await db.rahaza_material_stock.find({"material_id": material_id}, {"_id": 0}).to_list(500)
    out = []
    for r in rows:
        qty = float(read_qty(r) or 0)
        if qty <= 0:
            continue
        out.append({"location_id": r.get("location_id"), "qty": round(qty, 4)})
    if not out:
        return []
    ids = [o["location_id"] for o in out if o["location_id"]]
    names = {}
    async for loc in db.rahaza_locations.find({"id": {"$in": ids}}, {"_id": 0, "id": 1, "name": 1, "code": 1}):
        names[loc["id"]] = loc.get("name") or loc.get("code") or ""
    async for z in db.wh_zones.find({"id": {"$in": ids}}, {"_id": 0, "id": 1, "name": 1, "code": 1}):
        names.setdefault(z["id"], z.get("name") or z.get("code") or "")
    for o in out:
        o["location_name"] = names.get(o["location_id"], "Lokasi lain")
    out.sort(key=lambda x: -x["qty"])
    return out


async def _default_location(db, location_id: Optional[str] = None,
                            material_id: Optional[str] = None) -> tuple[str, str]:
    """Tentukan lokasi order cutting.

    Prioritas: (1) yang dipilih user, (2) lokasi dengan stok TERBANYAK untuk material
    tersebut, (3) lokasi bernama 'Gudang…', (4) lokasi aktif pertama.
    """
    if location_id:
        loc = await db.rahaza_locations.find_one({"id": location_id}, {"_id": 0})
        if loc:
            return loc["id"], loc.get("name") or loc.get("code") or ""
        z = await db.wh_zones.find_one({"id": location_id}, {"_id": 0})
        if z:
            return z["id"], z.get("name") or z.get("code") or ""
    if material_id:
        locs = await _stock_locations(db, material_id)
        if locs:
            return locs[0]["location_id"], locs[0]["location_name"]
    loc = await db.rahaza_locations.find_one(
        {"active": True, "name": {"$regex": "gudang", "$options": "i"}}, {"_id": 0}, sort=[("code", 1)])
    if not loc:
        loc = await db.rahaza_locations.find_one({"active": True}, {"_id": 0}, sort=[("code", 1)])
    if not loc:
        raise HTTPException(400, "Belum ada lokasi gudang (rahaza_locations). Buat lokasi dulu.")
    return loc["id"], loc.get("name") or loc.get("code") or ""


async def _enrich(db, o: dict) -> dict:
    o["progress_count"] = await db[PROGRESS].count_documents({"cutting_order_id": o["id"]})
    planned_in = _f(o.get("planned_input_qty"))
    consumed = _f(o.get("consumed_input_qty"))
    planned_out = _f(o.get("planned_output_qty"))
    produced = _f(o.get("produced_qty"))
    o["input_remaining"] = round(max(planned_in - consumed, 0), 4)
    o["output_remaining"] = round(max(planned_out - produced, 0), 4)
    o["progress_pct"] = round((produced / planned_out * 100), 1) if planned_out > 0 else 0.0
    o["yield_per_input"] = round(produced / consumed, 3) if consumed > 0 else 0.0
    return o


# ═════════════════════════════════════════════════════════════════════════════
# MASTER HELPERS — dipakai form frontend
# ═════════════════════════════════════════════════════════════════════════════
@router.get("/input-materials")
async def list_input_materials(request: Request, q: Optional[str] = None):
    """Master material yang layak jadi INPUT cutting (kain/benang, BUKAN potongan)."""
    await require_auth(request)
    db = get_db()
    query: dict = {
        "active": True,
        "type": {"$in": ["fabric", "yarn"]},
        "is_cut_panel": {"$ne": True},
    }
    if q:
        query["$or"] = [
            {"code": {"$regex": q, "$options": "i"}},
            {"name": {"$regex": q, "$options": "i"}},
            {"color": {"$regex": q, "$options": "i"}},
        ]
    mats = await db.rahaza_materials.find(query, {"_id": 0}).sort("name", 1).to_list(5000)
    ids = [m["id"] for m in mats]
    onhand = await stock_service.onhand_map(ids, db=db) if ids else {}
    rolls = {}
    if ids:
        cur = db.wh_fabric_rolls.aggregate([
            {"$match": {"material_id": {"$in": ids}, "status": {"$nin": ["fully_issued", "rejected"]}}},
            {"$group": {"_id": "$material_id", "n": {"$sum": 1}}},
        ])
        async for r in cur:
            rolls[r["_id"]] = r["n"]
    # Peta lokasi-berstok per material (1 query, bukan N query) — dipakai form agar
    # user langsung tahu stok kain ADA DI GUDANG MANA.
    loc_names = {}
    async for loc in db.rahaza_locations.find({}, {"_id": 0, "id": 1, "name": 1, "code": 1}):
        loc_names[loc["id"]] = loc.get("name") or loc.get("code") or ""
    from core.stock_schema import read_qty
    per_mat: dict[str, list] = {}
    if ids:
        async for r in db.rahaza_material_stock.find({"material_id": {"$in": ids}}, {"_id": 0}):
            q = float(read_qty(r) or 0)
            if q <= 0:
                continue
            per_mat.setdefault(r["material_id"], []).append({
                "location_id": r.get("location_id"),
                "location_name": loc_names.get(r.get("location_id"), "Lokasi lain"),
                "qty": round(q, 4),
            })
    for m in mats:
        locs = sorted(per_mat.get(m["id"], []), key=lambda x: -x["qty"])
        m["stock_qty"] = round(_f(onhand.get(m["id"])), 4)
        m["roll_count"] = rolls.get(m["id"], 0)
        m["stock_locations"] = locs
        m["best_location_id"] = locs[0]["location_id"] if locs else None
        m["best_location_name"] = locs[0]["location_name"] if locs else ""
    return serialize_doc(mats)


@router.get("/locations")
async def list_locations(request: Request):
    """Lokasi gudang untuk dropdown form cutting."""
    await require_auth(request)
    db = get_db()
    rows = await db.rahaza_locations.find({"active": True}, {"_id": 0}).sort("name", 1).to_list(500)
    return serialize_doc(rows)


@router.get("/rolls")
async def list_rolls(request: Request, material_id: str):
    """Roll fisik yang masih punya sisa untuk material tertentu (opsional dipilih)."""
    await require_auth(request)
    db = get_db()
    rows = await db.wh_fabric_rolls.find(
        {"material_id": material_id, "status": {"$nin": ["fully_issued", "rejected"]}},
        {"_id": 0},
    ).sort("roll_no", 1).to_list(500)
    return serialize_doc(rows)


@router.get("/output-materials")
async def list_output_materials(request: Request):
    """Semua master potongan yang pernah dihasilkan cutting."""
    await require_auth(request)
    db = get_db()
    mats = await db.rahaza_materials.find(
        {"is_cut_panel": True, "active": True}, {"_id": 0}
    ).sort("code", 1).to_list(2000)
    ids = [m["id"] for m in mats]
    onhand = await stock_service.onhand_map(ids, db=db) if ids else {}
    for m in mats:
        m["stock_qty"] = round(_f(onhand.get(m["id"])), 4)
    return serialize_doc(mats)


async def _ensure_output_material(db, o: dict, user: dict) -> dict:
    """Buat / pakai-ulang master material POTONGAN untuk order ini (idempoten)."""
    if o.get("output_material_id"):
        mat = await db.rahaza_materials.find_one({"id": o["output_material_id"]}, {"_id": 0})
        if mat:
            return mat
    code = (o.get("output_material_code") or "").strip().upper()
    if not code:
        default_code = "CUT-" + "-".join(
            x for x in [_slug(o.get("style_name") or o.get("style_sku") or "PANEL"),
                        _slug(o.get("output_color") or "", 10),
                        _slug(o.get("output_size") or "", 6)] if x and x != "NA"
        )
        code = await resolve_master_code(
            db, "rahaza_materials.cut_panel_code",
            {"STYLE": _slug(o.get("style_name") or o.get("style_sku") or "PANEL"),
             "WARNA": _slug(o.get("output_color") or "", 10),
             "SIZE": _slug(o.get("output_size") or "", 6)},
            default_code,
        )
    existing = await db.rahaza_materials.find_one({"code": code, "active": True}, {"_id": 0})
    if existing:
        return existing
    src = await db.rahaza_materials.find_one({"id": o.get("input_material_id")}, {"_id": 0}) or {}
    name_parts = [p for p in [o.get("style_name") or o.get("style_sku") or "Potongan",
                              o.get("output_color"), o.get("output_size")] if p]
    doc = {
        "id": _uid(),
        "code": code,
        "name": "Potongan " + " · ".join(name_parts),
        "type": "fabric",
        "unit": OUTPUT_UNIT,
        "category": OUTPUT_CATEGORY,
        "category_name": "Potongan / Kain Pola",
        "color": o.get("output_color") or "",
        "composition": src.get("composition") or "",
        "notes": f"Auto dari Cutting {o.get('number')} — sumber kain {src.get('code', '-')}",
        "min_stock": 0,
        "unit_cost": 0.0,
        # Potongan selalu dihitung per satuan dasar (pcs). Struktur UOM
        # dibuat eksplisit agar guardrail INV-UOM-3/4 hijau dan agar item ini
        # bisa diberi kemasan sendiri lewat Master Material bila diperlukan.
        "base_uom": "pcs",
        "uoms": [{"code": "pcs", "name": "PCS", "factor": 1.0, "is_base": True, "level": 0}],
        "purchase_uom": "pcs", "issue_uom": "pcs", "display_uom": "pcs",
        "pack_unit": "pack", "pack_size": 1, "display_in_packs": False,
        # penanda domain — dipakai filter Gudang & modul cutting
        "is_cut_panel": True,
        "source_material_id": o.get("input_material_id"),
        "source_material_code": src.get("code") or "",
        "style_sku": o.get("style_sku") or "",
        "style_name": o.get("style_name") or "",
        "size": o.get("output_size") or "",
        "active": True,
        "created_at": _now(), "updated_at": _now(),
    }
    await db.rahaza_materials.insert_one(dict(doc))
    await log_activity(user["id"], user.get("name", ""), "create", "cutting.output_material", code)
    return doc


# ═════════════════════════════════════════════════════════════════════════════
# CRUD ORDER
# ═════════════════════════════════════════════════════════════════════════════
@router.get("/orders")
async def list_orders(request: Request, status: Optional[str] = None,
                      q: Optional[str] = None, limit: int = 200, skip: int = 0):
    await require_auth(request)
    db = get_db()
    query: dict = {}
    if status:
        query["status"] = status
    if q:
        query["$or"] = [
            {"number": {"$regex": q, "$options": "i"}},
            {"style_name": {"$regex": q, "$options": "i"}},
            {"style_sku": {"$regex": q, "$options": "i"}},
            {"input_material_name": {"$regex": q, "$options": "i"}},
            {"output_material_code": {"$regex": q, "$options": "i"}},
        ]
    rows = await db[ORDERS].find(query, {"_id": 0}).sort("created_at", -1).skip(skip).limit(limit).to_list(500)
    for r in rows:
        await _enrich(db, r)
    return serialize_doc(rows)


@router.get("/dashboard")
async def dashboard(request: Request):
    await require_auth(request)
    db = get_db()
    by_status = {}
    cur = db[ORDERS].aggregate([{"$group": {"_id": "$status", "n": {"$sum": 1}}}])
    async for r in cur:
        by_status[r["_id"]] = r["n"]
    agg = await db[ORDERS].aggregate([
        {"$group": {
            "_id": None,
            "planned_output": {"$sum": "$planned_output_qty"},
            "produced": {"$sum": "$produced_qty"},
            "consumed": {"$sum": "$consumed_input_qty"},
            "waste": {"$sum": "$waste_qty"},
        }}
    ]).to_list(1)
    tot = agg[0] if agg else {}
    panels = await db.rahaza_materials.count_documents({"is_cut_panel": True, "active": True})
    recent = await db[ORDERS].find({}, {"_id": 0}).sort("created_at", -1).limit(5).to_list(5)
    consumed = _f(tot.get("consumed"))
    produced = _f(tot.get("produced"))
    return serialize_doc({
        "total_orders": sum(by_status.values()),
        "by_status": {
            "draft": by_status.get(STATUS_DRAFT, 0),
            "in_progress": by_status.get(STATUS_IN_PROGRESS, 0),
            "completed": by_status.get(STATUS_COMPLETED, 0),
            "cancelled": by_status.get(STATUS_CANCELLED, 0),
        },
        "planned_output_qty": round(_f(tot.get("planned_output")), 2),
        "produced_qty": round(produced, 2),
        "consumed_input_qty": round(consumed, 3),
        "waste_qty": round(_f(tot.get("waste")), 3),
        "avg_yield": round(produced / consumed, 3) if consumed > 0 else 0.0,
        "output_material_count": panels,
        "recent": recent,
    })


@router.get("/orders/{oid}")
async def get_order(oid: str, request: Request):
    await require_auth(request)
    db = get_db()
    o = await _get_order(db, oid)
    await _enrich(db, o)
    o["progress"] = await db[PROGRESS].find(
        {"cutting_order_id": oid}, {"_id": 0}
    ).sort("created_at", -1).to_list(500)
    if o.get("output_material_id"):
        om = await db.rahaza_materials.find_one({"id": o["output_material_id"]}, {"_id": 0})
        if om:
            o["output_material"] = om
            o["output_stock"] = round(_f(await stock_service.get_onhand(om["id"], db=db)), 4)
    if o.get("input_material_id"):
        o["input_stock"] = round(_f(await stock_service.get_onhand(o["input_material_id"], db=db)), 4)
    return serialize_doc(o)


@router.post("/orders")
async def create_order(request: Request):
    user = await _require_cutting_user(request)
    db = get_db()
    body = await request.json()

    input_material_id = (body.get("input_material_id") or "").strip()
    if not input_material_id:
        raise HTTPException(400, "Material kain (input) wajib dipilih.")
    mat = await db.rahaza_materials.find_one({"id": input_material_id, "active": True}, {"_id": 0})
    if not mat:
        raise HTTPException(404, "Material kain tidak ditemukan / tidak aktif.")
    if mat.get("is_cut_panel"):
        raise HTTPException(400, "Material yang dipilih adalah POTONGAN, bukan kain roll.")
    unit = (mat.get("unit") or "").lower()
    if unit not in INPUT_UNITS:
        raise HTTPException(
            400, f"Satuan material '{unit}' bukan satuan kain roll ({sorted(INPUT_UNITS)}).")

    planned_input = _f(body.get("planned_input_qty"))
    planned_output = _f(body.get("planned_output_qty"))
    if planned_input <= 0:
        raise HTTPException(400, "Rencana pemakaian kain harus > 0.")
    if planned_output <= 0:
        raise HTTPException(400, "Rencana hasil potongan (pcs) harus > 0.")

    style_name = (body.get("style_name") or "").strip()
    if not style_name:
        raise HTTPException(400, "Nama style/produk wajib diisi (dipakai untuk kode potongan).")

    loc_id, loc_name = await _default_location(db, body.get("location_id"), mat["id"])
    avail_here = _f(await stock_service.get_onhand(mat["id"], db=db))
    stock_here = next((x["qty"] for x in await _stock_locations(db, mat["id"])
                       if x["location_id"] == loc_id), 0.0)

    rolls_in = body.get("roll_ids") or []
    roll_docs = []
    if rolls_in:
        found = await db.wh_fabric_rolls.find({"id": {"$in": rolls_in}}, {"_id": 0}).to_list(200)
        for r in found:
            roll_docs.append({
                "roll_id": r["id"], "roll_no": r.get("roll_no", ""),
                "uom": r.get("uom", ""),
                "remaining": _f(r.get("remaining_kg") if (r.get("uom") == "kg") else r.get("remaining_m")),
                "consumed_qty": 0.0,
            })

    number = await gen_prefixed_number(db, ORDERS, "number", f"CUT-{_now():%Y}-", 4)
    doc = {
        "id": _uid(),
        "number": number,
        "status": STATUS_DRAFT,
        # input
        "input_material_id": mat["id"],
        "input_material_code": mat.get("code", ""),
        "input_material_name": mat.get("name", ""),
        "input_unit": unit,
        "input_color": mat.get("color", ""),
        "input_unit_cost": _f(mat.get("unit_cost")),
        "planned_input_qty": round(planned_input, 4),
        "consumed_input_qty": 0.0,
        "roll_ids": roll_docs,
        "location_id": loc_id,
        "location_name": loc_name,
        "stock_at_create": round(stock_here, 4),
        "stock_total_at_create": round(avail_here, 4),
        # output
        "style_sku": (body.get("style_sku") or "").strip(),
        "style_name": style_name,
        "output_color": (body.get("output_color") or mat.get("color") or "").strip(),
        "output_size": (body.get("output_size") or "").strip(),
        "output_unit": OUTPUT_UNIT,
        "output_material_id": None,
        "output_material_code": (body.get("output_material_code") or "").strip().upper(),
        "output_material_name": "",
        "planned_output_qty": round(planned_output, 4),
        "produced_qty": 0.0,
        "waste_qty": 0.0,
        "output_unit_cost": 0.0,
        # meta
        "target_date": body.get("target_date") or None,
        "notes": body.get("notes") or "",
        "created_by": user["id"], "created_by_name": user.get("name", ""),
        "created_at": _now(), "updated_at": _now(),
        "started_at": None, "completed_at": None,
    }
    await db[ORDERS].insert_one(dict(doc))
    await log_activity(user["id"], user.get("name", ""), "create", "cutting.order", number)
    await _enrich(db, doc)
    return serialize_doc(doc)


@router.put("/orders/{oid}")
async def update_order(oid: str, request: Request):
    user = await _require_cutting_user(request)
    db = get_db()
    o = await _get_order(db, oid)
    if o["status"] != STATUS_DRAFT:
        raise HTTPException(400, "Hanya cutting berstatus draft yang bisa diubah.")
    body = await request.json()
    patch: dict = {"updated_at": _now()}
    for k in ("style_sku", "style_name", "output_color", "output_size", "notes", "target_date"):
        if k in body:
            patch[k] = (body.get(k) or "") if isinstance(body.get(k), str) else body.get(k)
    if "planned_input_qty" in body:
        v = _f(body["planned_input_qty"])
        if v <= 0:
            raise HTTPException(400, "Rencana pemakaian kain harus > 0.")
        patch["planned_input_qty"] = round(v, 4)
    if "planned_output_qty" in body:
        v = _f(body["planned_output_qty"])
        if v <= 0:
            raise HTTPException(400, "Rencana hasil potongan harus > 0.")
        patch["planned_output_qty"] = round(v, 4)
    if "location_id" in body:
        lid, lname = await _default_location(db, body.get("location_id"), o.get("input_material_id"))
        patch["location_id"], patch["location_name"] = lid, lname
    await db[ORDERS].update_one({"id": oid}, {"$set": patch})
    await log_activity(user["id"], user.get("name", ""), "update", "cutting.order", o["number"])
    return serialize_doc(await _enrich(db, await _get_order(db, oid)))


@router.delete("/orders/{oid}")
async def delete_order(oid: str, request: Request):
    user = await _require_cutting_user(request)
    db = get_db()
    o = await _get_order(db, oid)
    if o["status"] != STATUS_DRAFT:
        raise HTTPException(400, "Hanya draft yang bisa dihapus. Gunakan Batalkan untuk yang lain.")
    await db[ORDERS].delete_one({"id": oid})
    await log_activity(user["id"], user.get("name", ""), "delete", "cutting.order", o["number"])
    return {"ok": True}


# ═════════════════════════════════════════════════════════════════════════════
# STATE TRANSITIONS
# ═════════════════════════════════════════════════════════════════════════════
@router.post("/orders/{oid}/start")
async def start_order(oid: str, request: Request):
    """draft ➜ in_progress. Sekalian membuat master material POTONGAN (output)."""
    user = await _require_cutting_user(request)
    db = get_db()
    o = await _get_order(db, oid)
    if o["status"] != STATUS_DRAFT:
        raise HTTPException(400, f"Status '{o['status']}' tidak bisa di-start.")

    # VALIDASI PER-LOKASI (perbaikan bug QA-1): stok disimpan per (material, lokasi),
    # sementara dulu di sini hanya dicek TOTAL lintas lokasi. Akibatnya order lolos
    # start tapi gagal saat progress ("tersedia 0.0") karena lokasi order ternyata
    # bukan lokasi yang memegang stok. Sekarang: kalau lokasi order kosong tapi ada
    # gudang lain yang punya stok, order otomatis diarahkan ke gudang tersebut.
    locs = await _stock_locations(db, o["input_material_id"])
    total = sum(x["qty"] for x in locs)
    if total <= 0:
        raise HTTPException(
            400, f"Stok kain {o['input_material_code']} kosong di semua gudang "
                 f"(0 {o['input_unit']}). Catat penerimaan barang di Gudang dulu.")
    here = next((x for x in locs if x["location_id"] == o.get("location_id")), None)
    moved_to = None
    if not here:
        best = locs[0]
        await db[ORDERS].update_one({"id": oid}, {"$set": {
            "location_id": best["location_id"],
            "location_name": best["location_name"],
        }})
        o["location_id"], o["location_name"] = best["location_id"], best["location_name"]
        moved_to = best["location_name"]

    out_mat = await _ensure_output_material(db, o, user)
    await db[ORDERS].update_one({"id": oid}, {"$set": {
        "status": STATUS_IN_PROGRESS,
        "output_material_id": out_mat["id"],
        "output_material_code": out_mat["code"],
        "output_material_name": out_mat["name"],
        "started_at": _now(), "updated_at": _now(),
    }})
    await log_activity(user["id"], user.get("name", ""), "start", "cutting.order", o["number"])
    out = await _enrich(db, await _get_order(db, oid))
    if moved_to:
        out["notice"] = f"Lokasi cutting dialihkan ke '{moved_to}' karena di sanalah stok kain berada."
    return serialize_doc(out)


@router.post("/orders/{oid}/progress")
async def add_progress(oid: str, request: Request):
    """Catat hasil potong sebagian: kain berkurang, potongan bertambah (SSOT stok)."""
    user = await _require_cutting_user(request)
    db = get_db()
    o = await _get_order(db, oid)
    if o["status"] != STATUS_IN_PROGRESS:
        raise HTTPException(400, "Progres hanya bisa diinput saat status 'in_progress'.")

    body = await request.json()
    input_used = _f(body.get("input_consumed"))
    output_qty = _f(body.get("output_qty"))
    waste = _f(body.get("waste_qty"))
    if input_used <= 0:
        raise HTTPException(400, "Kain terpakai harus > 0.")
    if output_qty <= 0:
        raise HTTPException(400, "Jumlah potongan jadi harus > 0.")

    # ── 2026-08-05 · SATUAN HITUNG OPERATOR (opsional, `input_uom`) ───────────
    # Kain dicatat di satuan order (`input_unit`, mis. "kg" atau "m"), tetapi
    # operator lantai sering menghitung dalam satuan lain (rol, gram, yard).
    # Bila `input_uom` dikirim, qty diterjemahkan DULU ke satuan order supaya
    # stok, sisa roll, dan akumulasi progres tetap satu bahasa.
    _op_uom = (body.get("input_uom") or "").strip().lower()
    _order_uom = (o.get("input_unit") or "").strip().lower()
    uom_applied = None
    if _op_uom and _op_uom != _order_uom:
        mat_in = await db.rahaza_materials.find_one({"id": o["input_material_id"]}, {"_id": 0})
        f_op, base_u, st_op, note_op = _bom_uom.line_factor(mat_in, _op_uom)
        if st_op not in ("base", "uom", "global", "fabric"):
            raise HTTPException(400, note_op or (
                f"Satuan '{_op_uom}' tidak bisa dikonversi ke '{_order_uom}'."))
        f_ord, _b, st_ord, _n = _bom_uom.line_factor(mat_in, _order_uom)
        if st_ord not in ("base", "uom", "global", "fabric") or not f_ord:
            f_ord = 1.0
        converted = round(float(input_used) * float(f_op) / float(f_ord), 4)
        if converted <= 0:
            raise HTTPException(400, "Hasil konversi kain terpakai harus > 0.")
        uom_applied = {"input_qty": input_used, "input_uom": _op_uom,
                       "qty_order_unit": converted, "order_unit": _order_uom,
                       "factor": float(f_op), "source": st_op}
        input_used = converted

    loc_id = o["location_id"]
    actor = await _actor(user)
    ref = {"type": "cutting", "id": o["id"], "no": o["number"]}

    # 1) Kurangi stok KAIN (guarded — tidak boleh minus)
    try:
        await stock_service.issue(o["input_material_id"], loc_id, input_used,
                                  ref=ref, actor=actor, db=db)
    except InsufficientStock as e:
        locs = await _stock_locations(db, o["input_material_id"])
        where = ", ".join(f"{x['location_name']}: {x['qty']}" for x in locs) or "tidak ada stok di gudang manapun"
        raise HTTPException(
            400, f"Stok kain tidak cukup di '{o.get('location_name')}': minta {e.requested}, "
                 f"tersedia {e.available} {o['input_unit']}. Sebaran stok — {where}.")

    # 2) Tambah stok POTONGAN
    out_mat_id = o.get("output_material_id")
    if not out_mat_id:
        out_mat = await _ensure_output_material(db, o, user)
        out_mat_id = out_mat["id"]
        await db[ORDERS].update_one({"id": oid}, {"$set": {
            "output_material_id": out_mat["id"],
            "output_material_code": out_mat["code"],
            "output_material_name": out_mat["name"],
        }})
    await stock_service.add(out_mat_id, loc_id, output_qty, ref=ref, actor=actor, db=db,
                            meta={"material_code": o.get("output_material_code"),
                                  "material_name": o.get("output_material_name"),
                                  "material_type": "fabric", "unit": OUTPUT_UNIT,
                                  "category": OUTPUT_CATEGORY})

    # 3) Roll fisik (opsional) — kurangi sisa roll + catat movement roll
    roll_id = (body.get("roll_id") or "").strip() or None
    if roll_id:
        roll = await db.wh_fabric_rolls.find_one({"id": roll_id}, {"_id": 0})
        if roll:
            field = "remaining_kg" if (roll.get("uom") == "kg") else "remaining_m"
            new_remaining = max(_f(roll.get(field)) - input_used, 0)
            status = "fully_issued" if new_remaining <= 0 else "partly_issued"
            await db.wh_fabric_rolls.update_one({"id": roll_id}, {"$set": {
                field: round(new_remaining, 3), "status": status,
                "updated_at": _now(), "updated_by": user.get("name", user["id"]),
            }})
            await db.wh_fabric_roll_movements.insert_one({
                "id": _uid(), "roll_id": roll_id, "roll_no": roll.get("roll_no", ""),
                "movement_type": "issue", "qty": round(input_used, 3),
                "unit": roll.get("uom", ""), "reference_type": "cutting",
                "reference_id": o["id"], "reference_no": o["number"],
                "notes": f"Cutting {o['number']}",
                "created_at": _now(), "created_by": user.get("name", ""),
            })
            await db[ORDERS].update_one(
                {"id": oid, "roll_ids.roll_id": roll_id},
                {"$inc": {"roll_ids.$.consumed_qty": round(input_used, 3)}},
            )

    prog = {
        "id": _uid(),
        "cutting_order_id": oid,
        "cutting_number": o["number"],
        "input_consumed": round(input_used, 4),
        "output_qty": round(output_qty, 4),
        "waste_qty": round(waste, 4),
        "roll_id": roll_id,
        "note": body.get("note") or "",
        "uom_applied": uom_applied,   # jejak konversi satuan operator (bila ada)
        "created_by": user["id"], "created_by_name": user.get("name", ""),
        "created_at": _now(),
    }
    await db[PROGRESS].insert_one(dict(prog))
    await db[ORDERS].update_one({"id": oid}, {
        "$inc": {"consumed_input_qty": round(input_used, 4),
                 "produced_qty": round(output_qty, 4),
                 "waste_qty": round(waste, 4)},
        "$set": {"updated_at": _now()},
    })
    await log_activity(user["id"], user.get("name", ""), "progress", "cutting.order", o["number"])
    return serialize_doc(await _enrich(db, await _get_order(db, oid)))


@router.post("/orders/{oid}/complete")
async def complete_order(oid: str, request: Request):
    """in_progress ➜ completed + hitung HPP potongan (biaya kain / pcs jadi)."""
    user = await _require_cutting_user(request)
    db = get_db()
    o = await _get_order(db, oid)
    if o["status"] != STATUS_IN_PROGRESS:
        raise HTTPException(400, f"Status '{o['status']}' tidak bisa di-complete.")
    produced = _f(o.get("produced_qty"))
    if produced <= 0:
        raise HTTPException(400, "Belum ada progres. Input hasil potong dulu sebelum menyelesaikan.")

    consumed = _f(o.get("consumed_input_qty"))
    unit_cost_in = _f(o.get("input_unit_cost"))
    if unit_cost_in <= 0:
        mat = await db.rahaza_materials.find_one({"id": o["input_material_id"]}, {"_id": 0}) or {}
        unit_cost_in = _f(mat.get("unit_cost"))
    total_cost = consumed * unit_cost_in
    out_unit_cost = round(total_cost / produced, 2) if produced > 0 else 0.0

    if o.get("output_material_id") and out_unit_cost > 0:
        await db.rahaza_materials.update_one(
            {"id": o["output_material_id"]},
            {"$set": {"unit_cost": out_unit_cost, "updated_at": _now()}},
        )
    await db[ORDERS].update_one({"id": oid}, {"$set": {
        "status": STATUS_COMPLETED,
        "output_unit_cost": out_unit_cost,
        "total_input_cost": round(total_cost, 2),
        "completed_at": _now(), "updated_at": _now(),
    }})
    await log_activity(user["id"], user.get("name", ""), "complete", "cutting.order", o["number"])
    out = await _enrich(db, await _get_order(db, oid))
    if unit_cost_in <= 0:
        out["notice"] = (
            f"HPP potongan = 0 karena harga satuan kain {o.get('input_material_code')} belum diisi "
            f"di Master Item Gudang. Isi kolom 'Harga Satuan' pada material kain agar HPP potongan "
            f"dan nilai persediaan terhitung.")
    return serialize_doc(out)


@router.post("/orders/{oid}/cancel")
async def cancel_order(oid: str, request: Request):
    user = await _require_cutting_user(request)
    db = get_db()
    o = await _get_order(db, oid)
    if o["status"] in (STATUS_COMPLETED, STATUS_CANCELLED):
        raise HTTPException(400, f"Status '{o['status']}' tidak bisa dibatalkan.")
    n = await db[PROGRESS].count_documents({"cutting_order_id": oid})
    if n > 0:
        raise HTTPException(
            400, "Sudah ada progres (stok sudah bergerak). Selesaikan cutting, "
                 "lalu koreksi lewat Penyesuaian Stok di Gudang bila perlu.")
    body = {}
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001 — BODY OPSIONAL: pembatalan boleh dikirim
        # tanpa body sama sekali (mis. tombol "Batalkan" tanpa alasan). Ini bukan
        # kegagalan, jadi memang tidak ada yang perlu dicatat — `reason` di bawah
        # akan menjadi string kosong. Sengaja dibiarkan tanpa log agar tidak
        # membanjiri log dengan kejadian normal.
        body = {}
    await db[ORDERS].update_one({"id": oid}, {"$set": {
        "status": STATUS_CANCELLED,
        "cancel_reason": (body or {}).get("reason") or "",
        "updated_at": _now(),
    }})
    await log_activity(user["id"], user.get("name", ""), "cancel", "cutting.order", o["number"])
    return serialize_doc(await _enrich(db, await _get_order(db, oid)))
