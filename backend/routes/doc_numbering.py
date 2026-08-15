"""Penomoran Dokumen & SKU — konfigurasi format nomor oleh owner.

Layar: Portal Administrasi Sistem → Penomoran Dokumen.

Catatan arsitektur: modul ini TIDAK menghasilkan nomor sendiri. Ia hanya
menyimpan format; satu-satunya generator tetap
`utils.counters.gen_prefixed_number` yang membaca format ini.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from database import get_db
from data.doc_number_registry import (DOC_NUMBER_REGISTRY, REGISTRY_BY_KEY, GROUPS,
                                      target_of)
from utils.counters import (CONFIG_COLL, invalidate_format_cache, peek_counter,
                            render_format, validate_format)

router = APIRouter(prefix="/api/admin/doc-numbering", tags=["doc-numbering"])

ALLOWED_ROLES = {"superadmin", "owner", "admin"}


async def _require_admin(request: Request) -> dict:
    """2026-08-06 — gerbang izin terpusat (fallback aman): izin `docnum.manage`
    bisa diberikan ke role non-admin lewat layar "Peran & Hak Akses"."""
    from routes.shared import require_perm
    return await require_perm(
        request, "docnum.manage", "settings.manage",
        legacy_roles=tuple(ALLOWED_ROLES),
        message="Akses ditolak: butuh izin kelola penomoran dokumen (docnum.manage).",
    )


class FormatIn(BaseModel):
    key: str
    format: str = Field(..., min_length=1, max_length=120)
    active: bool = True


@router.get("")
async def list_formats(request: Request):
    """Katalog jenis dokumen + format aktif + nomor terakhir yang terpakai."""
    await _require_admin(request)
    db = get_db()
    saved = {c["key"]: c for c in await db[CONFIG_COLL].find({}, {"_id": 0}).to_list(500)}

    items = []
    for entry in DOC_NUMBER_REGISTRY:
        cfg = saved.get(entry["key"]) or {}
        fmt = cfg.get("format") or entry["default_format"]
        seqd = entry.get("sequenced", True)
        try:
            contoh = validate_format(fmt, entry.get("tokens"), require_seq=seqd)
            error = None
        except ValueError as e:
            contoh, error = None, str(e)
        collection, field = target_of(entry)
        terakhir = None
        if seqd and not error:
            prefix, _ = render_format(fmt, ctx={t: t[:3].upper() for t in entry.get("tokens", [])})
            terakhir = await peek_counter(db, f"autonum:{collection}:{field}:{prefix}")
        items.append({
            **entry,
            "collection": collection,
            "field": field,
            "format": fmt,
            "is_custom": bool(cfg.get("format")),
            "active": cfg.get("active", True),
            "contoh": contoh,
            "error": error,
            "nomor_terakhir": terakhir,
            "updated_at": cfg.get("updated_at"),
            "updated_by": cfg.get("updated_by"),
        })
    return {"groups": GROUPS, "items": items,
            "tokens_umum": ["YYYY", "YY", "MM", "DD", "SEQ:n"]}


@router.post("/preview")
async def preview(request: Request):
    """Validasi format & tampilkan contoh nomor — tanpa menyimpan apa pun."""
    await _require_admin(request)
    body = await request.json()
    entry = REGISTRY_BY_KEY.get(body.get("key") or "")
    try:
        return {"ok": True, "contoh": validate_format(
            body.get("format") or "", (entry or {}).get("tokens"),
            require_seq=(entry or {}).get("sequenced", True))}
    except ValueError as e:
        return {"ok": False, "error": str(e)}


@router.put("")
async def save_format(request: Request, data: FormatIn):
    user = await _require_admin(request)
    entry = REGISTRY_BY_KEY.get(data.key)
    if not entry:
        raise HTTPException(404, f"Jenis dokumen '{data.key}' tidak dikenal.")
    try:
        contoh = validate_format(data.format, entry.get("tokens"),
                                 require_seq=entry.get("sequenced", True))
    except ValueError as e:
        raise HTTPException(400, str(e))

    db = get_db()
    now = datetime.now(timezone.utc).isoformat()
    await db[CONFIG_COLL].update_one(
        {"key": data.key},
        {"$set": {"format": data.format.strip(), "active": data.active,
                  "label": entry["label"], "group": entry["group"],
                  "updated_at": now, "updated_by": user.get("email", user.get("id"))},
         "$setOnInsert": {"id": str(uuid.uuid4()), "key": data.key}},
        upsert=True,
    )
    invalidate_format_cache(data.key)
    return {"ok": True, "key": data.key, "format": data.format, "contoh": contoh}


@router.delete("/{key}")
async def reset_format(request: Request, key: str):
    """Kembalikan ke format bawaan kode."""
    await _require_admin(request)
    if key not in REGISTRY_BY_KEY:
        raise HTTPException(404, f"Jenis dokumen '{key}' tidak dikenal.")
    db = get_db()
    await db[CONFIG_COLL].delete_one({"key": key})
    invalidate_format_cache(key)
    return {"ok": True, "key": key, "format": REGISTRY_BY_KEY[key]["default_format"]}


class CounterIn(BaseModel):
    key: str
    start_from: int = Field(..., ge=0)
    prefix: Optional[str] = None


@router.post("/counter")
async def set_counter(request: Request, data: CounterIn):
    """Setel ulang titik awal nomor urut (mis. mulai dari 100 untuk tahun baru).

    Menurunkan angka bisa menimbulkan nomor ganda pada dokumen yang sudah ada —
    karena itu penurunan hanya diizinkan bila belum ada dokumen memakai prefix ini.
    """
    user = await _require_admin(request)
    entry = REGISTRY_BY_KEY.get(data.key)
    if not entry:
        raise HTTPException(404, f"Jenis dokumen '{data.key}' tidak dikenal.")
    if not entry.get("sequenced", True):
        raise HTTPException(400, f"'{entry['label']}' tidak memakai nomor urut.")
    db = get_db()
    collection, field = target_of(entry)
    cfg = await db[CONFIG_COLL].find_one({"key": data.key}, {"_id": 0, "format": 1})
    fmt = (cfg or {}).get("format") or entry["default_format"]
    try:
        prefix, _ = render_format(fmt, ctx={t: t[:3].upper() for t in entry.get("tokens", [])})
    except ValueError as e:
        raise HTTPException(400, str(e))
    prefix = data.prefix or prefix

    counter_key = f"autonum:{collection}:{field}:{prefix}"
    current = await peek_counter(db, counter_key) or 0
    if data.start_from < current:
        used = await db[collection].count_documents({field: {"$regex": f"^{prefix}"}})
        if used:
            raise HTTPException(400, f"Tidak bisa mundur: sudah ada {used} dokumen memakai awalan '{prefix}'.")
    await db.counters.update_one(
        {"_id": counter_key},
        {"$set": {"seq": data.start_from, "namespace": "autonum",
                  "updated_by": user.get("email"), "updated_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True,
    )
    return {"ok": True, "key": data.key, "prefix": prefix,
            "nomor_berikutnya": f"{prefix}{data.start_from + 1:0{4}d}"}
