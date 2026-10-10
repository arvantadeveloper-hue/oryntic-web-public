"""Platform operating expenses (pengeluaran) with optional e-faktur attachment and PPN 11% split.
Access: super_admin + finance. Amount entered = total paid (already incl. PPN when taxable)."""
import io
import os
import re
import calendar
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, BackgroundTasks
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse, Response
from pydantic import BaseModel, Field

from db import db, now_iso, new_id
from platform_api.csvsafe import SafeWriter
from auth import require_platform_staff
from platform_api.common import _audit
from mailer import send_email, budget_alert_email
import storage
import uuid

router = APIRouter(prefix="/api/platform/expenses", tags=["platform-expenses"])

PPN_RATE = 0.11
CATEGORY_LIST = [
    {"id": "ai_provider", "label": "AI Model Provider"},
    {"id": "hosting_prod", "label": "Hosting Production"},
    {"id": "hosting_dev", "label": "Hosting Development"},
    {"id": "database", "label": "Database"},
    {"id": "domain", "label": "Domain/DNS"},
    {"id": "tools", "label": "Tools/SaaS"},
    {"id": "other", "label": "Lainnya"},
]
CATEGORIES = {c["id"] for c in CATEGORY_LIST}
CATEGORY_LABELS = {c["id"]: c["label"] for c in CATEGORY_LIST}
ALLOWED_EXT = {"pdf", "jpg", "jpeg", "png"}
MAX_BYTES = 10 * 1024 * 1024


def split_ppn(amount: int, taxable: bool) -> tuple[int, int]:
    """Amount already includes PPN when taxable → DPP = amount / 1.11, PPN = amount - DPP."""
    if taxable:
        dpp = round(amount / (1 + PPN_RATE))
        return dpp, amount - dpp
    return amount, 0


async def _upload_efaktur(ext: str, data: bytes, content_type: str) -> tuple[str, int]:
    """Store the e-faktur file in the shared Emergent object storage (same bucket as the main app)."""
    res = await run_in_threadpool(storage.put_object, f"oryntix-admin/efaktur/{uuid.uuid4()}.{ext}", data, content_type)
    return res["path"], int(res.get("size") or len(data))


def _truthy(v: str) -> bool:
    return str(v).strip().lower() in ("true", "1", "on", "ya", "yes")


def _filter(q: Optional[str], category: Optional[str], start: Optional[str], end: Optional[str]) -> dict:
    f = {"is_deleted": False}
    if q:
        f["$or"] = [{"vendor": {"$regex": re.escape(q.strip()), "$options": "i"}}, {"description": {"$regex": re.escape(q.strip()), "$options": "i"}}]
    if category:
        if category not in CATEGORIES:
            raise HTTPException(400, "Kategori tidak valid")
        f["category"] = category
    cr = {}
    try:
        if start:
            cr["$gte"] = datetime.strptime(start, "%Y-%m-%d").date().isoformat()
        if end:
            cr["$lte"] = datetime.strptime(end, "%Y-%m-%d").date().isoformat()
    except ValueError as exc:
        raise HTTPException(400, "Format tanggal harus YYYY-MM-DD") from exc
    if cr:
        f["date"] = cr
    return f


@router.get("")
async def list_expenses(q: Optional[str] = None, category: Optional[str] = None, start: Optional[str] = None, end: Optional[str] = None, limit: int = 300, u: dict = Depends(require_platform_staff)):
    f = _filter(q, category, start, end)
    items = await db.platform_expenses.find(f, {"_id": 0}).sort("date", -1).to_list(max(1, min(limit, 1000)))
    total = {
        "count": len(items),
        "amount": sum(i.get("amount_idr", 0) for i in items),
        "dpp": sum(i.get("dpp_idr", 0) for i in items),
        "ppn": sum(i.get("ppn_idr", 0) for i in items),
    }
    return {"items": items, "total": total, "categories": CATEGORY_LIST}


async def _pending_efaktur_list() -> list:
    """Taxable expenses still missing their e-faktur (typically auto-generated from subscriptions)."""
    return await db.platform_expenses.find({"is_deleted": False, "needs_efaktur": True, "attachment": None}, {"_id": 0}).sort("date", 1).to_list(500)


@router.get("/pending-efaktur")
async def pending_efaktur(u: dict = Depends(require_platform_staff)):
    items = await _pending_efaktur_list()
    return {"count": len(items), "items": items, "ppn_total": sum(int(e.get("ppn_idr") or 0) for e in items)}


@router.post("")
async def create_expense(
    background: BackgroundTasks,
    date: str = Form(...),
    category: str = Form(...),
    vendor: str = Form(...),
    amount_idr: int = Form(...),
    description: str = Form(""),
    taxable: str = Form("false"),
    efaktur_no: str = Form(""),
    file: Optional[UploadFile] = File(None),
    u: dict = Depends(require_platform_staff),
):
    try:
        datetime.strptime(date, "%Y-%m-%d")
    except ValueError as exc:
        raise HTTPException(400, "Tanggal harus YYYY-MM-DD") from exc
    if category not in CATEGORIES:
        raise HTTPException(400, "Kategori tidak valid")
    if not vendor.strip():
        raise HTTPException(400, "Vendor wajib diisi")
    if amount_idr <= 0:
        raise HTTPException(400, "Jumlah harus lebih dari 0")
    is_taxable = _truthy(taxable)
    if is_taxable and (file is None or not getattr(file, "filename", "")):
        raise HTTPException(400, "Lampiran e-faktur wajib untuk pengeluaran kena PPN")

    attachment = None
    if file is not None and getattr(file, "filename", ""):
        ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
        if ext not in ALLOWED_EXT:
            raise HTTPException(400, "Format lampiran harus PDF, JPG, atau PNG")
        data = await file.read()
        if len(data) > MAX_BYTES:
            raise HTTPException(400, "Ukuran lampiran maksimal 10 MB")
        try:
            path, size = await _upload_efaktur(ext, data, file.content_type or "application/octet-stream")
        except Exception as exc:
            raise HTTPException(502, "Gagal mengunggah lampiran e-faktur") from exc
        attachment = {"storage_path": path, "original_filename": file.filename, "content_type": file.content_type, "size": size}

    dpp, ppn = split_ppn(amount_idr, is_taxable)
    doc = {
        "id": new_id(), "date": date, "category": category, "vendor": vendor.strip(), "description": description.strip(),
        "amount_idr": amount_idr, "taxable": is_taxable, "dpp_idr": dpp, "ppn_idr": ppn,
        "efaktur_no": efaktur_no.strip(), "attachment": attachment,
        "created_by": u["email"], "created_at": now_iso(), "is_deleted": False,
    }
    await db.platform_expenses.insert_one(dict(doc))
    await _audit(u, "expense.create", vendor.strip(), {"category": category, "amount_idr": amount_idr, "taxable": is_taxable, "ppn_idr": ppn})
    background.add_task(_check_budget_alerts)
    return doc


@router.delete("/{eid}")
async def delete_expense(eid: str, u: dict = Depends(require_platform_staff)):
    e = await db.platform_expenses.find_one({"id": eid, "is_deleted": False}, {"_id": 0})
    if not e:
        raise HTTPException(404, "Pengeluaran tidak ditemukan")
    await db.platform_expenses.update_one({"id": eid}, {"$set": {"is_deleted": True, "updated_at": now_iso()}})
    await _audit(u, "expense.delete", e.get("vendor"), {"category": e.get("category"), "amount_idr": e.get("amount_idr")})
    return {"ok": True}


@router.get("/export.csv")
async def export_csv(q: Optional[str] = None, category: Optional[str] = None, start: Optional[str] = None, end: Optional[str] = None, u: dict = Depends(require_platform_staff)):
    f = _filter(q, category, start, end)
    items = await db.platform_expenses.find(f, {"_id": 0}).sort("date", -1).to_list(5000)
    buf = io.StringIO()
    w = SafeWriter(buf, delimiter=";")
    w.writerow(["tanggal", "kategori", "vendor", "keterangan", "total_idr", "kena_ppn", "dpp_idr", "ppn_idr", "no_efaktur", "lampiran"])
    for e in items:
        w.writerow([e["date"], CATEGORY_LABELS.get(e["category"], e["category"]), e["vendor"], e.get("description", ""), e["amount_idr"],
                    "ya" if e.get("taxable") else "tidak", e.get("dpp_idr", 0), e.get("ppn_idr", 0), e.get("efaktur_no", ""), (e.get("attachment") or {}).get("original_filename", "")])
    tot_amount = sum(e.get("amount_idr", 0) for e in items)
    tot_dpp = sum(e.get("dpp_idr", 0) for e in items)
    tot_ppn = sum(e.get("ppn_idr", 0) for e in items)
    w.writerow(["TOTAL", "", "", "", tot_amount, "", tot_dpp, tot_ppn, "", ""])
    await _audit(u, "expense.export", f"{start or 'awal'}..{end or 'kini'}", {"count": len(items)})
    name = f"oryntix-pengeluaran-{start or 'awal'}-{end or 'kini'}.csv"
    return StreamingResponse(iter(["\ufeff" + buf.getvalue()]), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="{name}"'})


def _month_str(dt: Optional[datetime] = None) -> str:
    return (dt or datetime.now(timezone.utc)).strftime("%Y-%m")


async def generate_recurring(for_month: str, actor_email: str = "system") -> dict:
    """Create one expense per active subscription template for `for_month` (YYYY-MM). Idempotent via last_generated."""
    y, m = int(for_month[:4]), int(for_month[5:7])
    last_day = calendar.monthrange(y, m)[1]
    created = 0
    async for tpl in db.platform_recurring_expenses.find({"active": True, "is_deleted": False}):
        if tpl.get("last_generated") == for_month:
            continue
        day = min(int(tpl.get("day_of_month") or 1), last_day)
        amount = int(tpl.get("amount_idr") or 0)
        taxable = bool(tpl.get("taxable"))
        dpp, ppn = split_ppn(amount, taxable)
        doc = {
            "id": new_id(), "date": f"{y:04d}-{m:02d}-{day:02d}", "category": tpl["category"], "vendor": tpl["vendor"],
            "description": tpl.get("description", ""), "amount_idr": amount, "taxable": taxable, "dpp_idr": dpp, "ppn_idr": ppn,
            "efaktur_no": "", "attachment": None, "from_recurring": tpl["id"], "needs_efaktur": taxable,
            "created_by": actor_email, "created_at": now_iso(), "is_deleted": False,
        }
        await db.platform_expenses.insert_one(dict(doc))
        await db.platform_recurring_expenses.update_one({"id": tpl["id"]}, {"$set": {"last_generated": for_month, "updated_at": now_iso()}})
        created += 1
    return {"month": for_month, "created": created}


class RecurringIn(BaseModel):
    category: str
    vendor: str = Field(min_length=1, max_length=120)
    amount_idr: int = Field(gt=0)
    taxable: bool = False
    description: str = Field(default="", max_length=300)
    day_of_month: int = Field(default=1, ge=1, le=28)
    active: bool = True


@router.get("/recurring")
async def list_recurring(u: dict = Depends(require_platform_staff)):
    items = await db.platform_recurring_expenses.find({"is_deleted": False}, {"_id": 0}).sort("created_at", -1).to_list(500)
    return {"items": items, "categories": CATEGORY_LIST}


@router.post("/recurring")
async def create_recurring(x: RecurringIn, u: dict = Depends(require_platform_staff)):
    if x.category not in CATEGORIES:
        raise HTTPException(400, "Kategori tidak valid")
    doc = {"id": new_id(), **x.model_dump(), "vendor": x.vendor.strip(), "last_generated": None, "created_by": u["email"], "created_at": now_iso(), "is_deleted": False}
    await db.platform_recurring_expenses.insert_one(dict(doc))
    await _audit(u, "recurring.create", x.vendor.strip(), {"category": x.category, "amount_idr": x.amount_idr, "taxable": x.taxable})
    return doc


@router.put("/recurring/{rid}")
async def update_recurring(rid: str, x: RecurringIn, u: dict = Depends(require_platform_staff)):
    if x.category not in CATEGORIES:
        raise HTTPException(400, "Kategori tidak valid")
    r = await db.platform_recurring_expenses.find_one({"id": rid, "is_deleted": False}, {"_id": 0})
    if not r:
        raise HTTPException(404, "Langganan tidak ditemukan")
    await db.platform_recurring_expenses.update_one({"id": rid}, {"$set": {**x.model_dump(), "vendor": x.vendor.strip(), "updated_at": now_iso()}})
    await _audit(u, "recurring.update", x.vendor.strip(), {"active": x.active})
    return {"ok": True}


@router.delete("/recurring/{rid}")
async def delete_recurring(rid: str, u: dict = Depends(require_platform_staff)):
    r = await db.platform_recurring_expenses.find_one({"id": rid, "is_deleted": False}, {"_id": 0})
    if not r:
        raise HTTPException(404, "Langganan tidak ditemukan")
    await db.platform_recurring_expenses.update_one({"id": rid}, {"$set": {"is_deleted": True, "updated_at": now_iso()}})
    await _audit(u, "recurring.delete", r.get("vendor"), {})
    return {"ok": True}


@router.post("/recurring/run")
async def run_recurring(background: BackgroundTasks, u: dict = Depends(require_platform_staff)):
    res = await generate_recurring(_month_str(), u["email"])
    await _audit(u, "recurring.run", res["month"], {"created": res["created"]})
    background.add_task(_check_budget_alerts)
    return res


@router.put("/{eid}/efaktur")
async def attach_efaktur(eid: str, efaktur_no: str = Form(""), file: UploadFile = File(...), u: dict = Depends(require_platform_staff)):
    e = await db.platform_expenses.find_one({"id": eid, "is_deleted": False}, {"_id": 0})
    if not e:
        raise HTTPException(404, "Pengeluaran tidak ditemukan")
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in ALLOWED_EXT:
        raise HTTPException(400, "Format lampiran harus PDF, JPG, atau PNG")
    data = await file.read()
    if len(data) > MAX_BYTES:
        raise HTTPException(400, "Ukuran lampiran maksimal 10 MB")
    try:
        path, size = await _upload_efaktur(ext, data, file.content_type or "application/octet-stream")
    except Exception as exc:
        raise HTTPException(502, "Gagal mengunggah lampiran e-faktur") from exc
    att = {"storage_path": path, "original_filename": file.filename, "content_type": file.content_type, "size": size}
    upd = {"attachment": att, "needs_efaktur": False, "updated_at": now_iso()}
    if efaktur_no.strip():
        upd["efaktur_no"] = efaktur_no.strip()
    await db.platform_expenses.update_one({"id": eid}, {"$set": upd})
    await _audit(u, "expense.efaktur", e.get("vendor"), {})
    return {"ok": True, "attachment": att}


async def _month_spend():
    month = _month_str()
    overall = 0
    by_cat = {}
    async for x in db.platform_expenses.find({"is_deleted": False, "date": {"$gte": month + "-01", "$lte": month + "-31"}}, {"_id": 0, "amount_idr": 1, "category": 1}):
        a = int(x.get("amount_idr") or 0)
        overall += a
        by_cat[x["category"]] = by_cat.get(x["category"], 0) + a
    return month, overall, by_cat


@router.get("/budget")
async def get_budget(u: dict = Depends(require_platform_staff)):
    cfg = await db.platform_config.find_one({"id": "expense_budget"}, {"_id": 0}) or {}
    monthly = int(cfg.get("monthly_idr") or 0)
    cat_budgets = cfg.get("categories") or {}
    month, spent, by_cat = await _month_spend()
    cats = [{
        "category": c["id"], "label": c["label"], "budget_idr": int(cat_budgets.get(c["id"]) or 0),
        "spent_idr": by_cat.get(c["id"], 0),
        "pct": round(by_cat.get(c["id"], 0) / int(cat_budgets[c["id"]]) * 100) if cat_budgets.get(c["id"]) else 0,
        "over": bool(cat_budgets.get(c["id"])) and by_cat.get(c["id"], 0) > int(cat_budgets.get(c["id"]) or 0),
    } for c in CATEGORY_LIST]
    return {"month": month, "monthly_idr": monthly, "spent_idr": spent, "remaining_idr": max(0, monthly - spent),
            "pct": round(spent / monthly * 100) if monthly else 0, "over": monthly > 0 and spent > monthly, "categories": cats}


class BudgetIn(BaseModel):
    monthly_idr: int = Field(ge=0)
    categories: dict[str, int] = {}


@router.put("/budget")
async def set_budget(x: BudgetIn, background: BackgroundTasks, u: dict = Depends(require_platform_staff)):
    cats = {}
    for k, v in (x.categories or {}).items():
        if k not in CATEGORIES:
            raise HTTPException(400, f"Kategori tidak valid: {k}")
        if int(v) < 0:
            raise HTTPException(400, "Anggaran tidak boleh negatif")
        if int(v) > 0:
            cats[k] = int(v)
    # reset this month's alert flags so a fresh breach re-triggers after a budget change
    await db.platform_config.update_one({"id": "expense_budget"}, {"$set": {"id": "expense_budget", "monthly_idr": x.monthly_idr, "categories": cats, "alerts": {}, "updated_at": now_iso(), "updated_by": u["email"]}}, upsert=True)
    await _audit(u, "budget.set", "anggaran bulanan", {"monthly_idr": x.monthly_idr, "categories": len(cats)})
    background.add_task(_check_budget_alerts)
    return {"ok": True}


async def _check_budget_alerts():
    """Email finance once per month per scope when current-month spend passes a budget threshold."""
    cfg = await db.platform_config.find_one({"id": "expense_budget"}, {"_id": 0})
    if not cfg:
        return
    month, overall, by_cat = await _month_spend()
    alerts = cfg.get("alerts") or {}
    breaches = []  # (label, budget, spent)
    ob = int(cfg.get("monthly_idr") or 0)
    if ob > 0 and overall > ob and not alerts.get(f"{month}:overall"):
        alerts[f"{month}:overall"] = True
        breaches.append(("Total pengeluaran", ob, overall))
    for cat, amt in (cfg.get("categories") or {}).items():
        b = int(amt or 0)
        if b > 0 and by_cat.get(cat, 0) > b and not alerts.get(f"{month}:{cat}"):
            alerts[f"{month}:{cat}"] = True
            breaches.append((CATEGORY_LABELS.get(cat, cat), b, by_cat.get(cat, 0)))
    if not breaches:
        return
    await db.platform_config.update_one({"id": "expense_budget"}, {"$set": {"alerts": alerts}}, upsert=True)
    recipients = [usr["email"] async for usr in db.users.find({"platform_role": "finance", "disabled": {"$ne": True}}, {"_id": 0, "email": 1})]
    if not recipients:
        return
    link = (os.environ.get("PLATFORM_URL") or "").rstrip("/") + "/expenses"
    subject, html, text = budget_alert_email(month, breaches, link)
    for to in recipients:
        await send_email(to, subject, html, text)


@router.get("/{eid}/file")
async def get_file(eid: str, u: dict = Depends(require_platform_staff)):
    e = await db.platform_expenses.find_one({"id": eid, "is_deleted": False}, {"_id": 0})
    if not e or not e.get("attachment"):
        raise HTTPException(404, "Lampiran tidak ditemukan")
    att = e["attachment"]
    try:
        data, ct = await run_in_threadpool(storage.get_object, att["storage_path"])
    except Exception as exc:
        raise HTTPException(502, "Gagal mengambil lampiran") from exc
    return Response(content=data, media_type=att.get("content_type") or ct,
                    headers={"Content-Disposition": f'inline; filename="{att.get("original_filename", "efaktur")}"'})
