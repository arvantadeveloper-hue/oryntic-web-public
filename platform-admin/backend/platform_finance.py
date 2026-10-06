import csv
import io
from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from db import db
from auth import require_platform_staff
from platform_admin import _audit

# Finance reports (roles: super_admin, finance): revenue / top-ups / adjustments / consumption per period, CSV export.
router = APIRouter(prefix="/api/platform/finance", tags=["platform-finance"])


def _range(date_from: Optional[str], date_to: Optional[str]) -> tuple:
    now = datetime.now(timezone.utc)
    try:
        start = datetime.fromisoformat(date_from).replace(tzinfo=timezone.utc) if date_from else (now - timedelta(days=30)).replace(hour=0, minute=0, second=0, microsecond=0)
        end = (datetime.fromisoformat(date_to).replace(tzinfo=timezone.utc) + timedelta(days=1)) if date_to else now + timedelta(seconds=1)
    except ValueError as exc:
        raise HTTPException(400, "Format tanggal harus YYYY-MM-DD") from exc
    if end <= start or (end - start).days > 366:
        raise HTTPException(400, "Rentang maksimal 366 hari")
    return start.isoformat(), end.isoformat()


def _bucket(iso: str, group: str) -> str:
    return iso[:7] if group == "month" else iso[:10]


async def finance_rows(date_from: Optional[str], date_to: Optional[str], group: str) -> dict:
    start, end = _range(date_from, date_to)
    rows, packages, users = {}, {}, set()

    def row(k):
        return rows.setdefault(k, {"period": k, "topups": 0, "credits_sold": 0, "revenue_idr": 0, "adjustments": 0, "credits_adjusted": 0, "credits_consumed": 0, "buyers": set()})

    async for t in db.credit_transactions.find({"created_at": {"$gte": start, "$lt": end}, "type": {"$in": ["topup", "adjustment"]}}, {"_id": 0, "type": 1, "amount": 1, "meta": 1, "created_at": 1, "user_id": 1}):
        r = row(_bucket(t["created_at"], group))
        if t["type"] == "topup":
            price = int((t.get("meta") or {}).get("price_idr") or 0)
            r["topups"] += 1; r["credits_sold"] += int(t.get("amount") or 0); r["revenue_idr"] += price; r["buyers"].add(t.get("user_id")); users.add(t.get("user_id"))
            pk = (t.get("meta") or {}).get("package") or "-"
            p = packages.setdefault(pk, {"package": pk, "count": 0, "credits": 0, "revenue_idr": 0}); p["count"] += 1; p["credits"] += int(t.get("amount") or 0); p["revenue_idr"] += price
        else:
            r["adjustments"] += 1; r["credits_adjusted"] += int(t.get("amount") or 0)
    async for e in db.usage_events.find({"created_at": {"$gte": start, "$lt": end}}, {"_id": 0, "credits": 1, "created_at": 1}):
        row(_bucket(e["created_at"], group))["credits_consumed"] += int(e.get("credits") or 0)
    out = sorted(rows.values(), key=lambda r: r["period"])
    for r in out:
        r["buyers"] = len(r["buyers"])
    total = {k: sum(r[k] for r in out) for k in ("topups", "credits_sold", "revenue_idr", "adjustments", "credits_adjusted", "credits_consumed")}
    total["buyers"] = len(users)
    return {"from": start[:10], "to": (datetime.fromisoformat(end) - timedelta(seconds=1)).date().isoformat(), "group": group, "rows": out, "total": total,
            "packages": sorted(packages.values(), key=lambda p: -p["revenue_idr"])}


@router.get("")
async def finance_report(date_from: Optional[str] = None, date_to: Optional[str] = None, group: str = "day", u: dict = Depends(require_platform_staff)):
    if group not in ("day", "month"):
        raise HTTPException(400, "group harus day atau month")
    return await finance_rows(date_from, date_to, group)


@router.get("/export.csv")
async def finance_csv(date_from: Optional[str] = None, date_to: Optional[str] = None, group: str = "day", u: dict = Depends(require_platform_staff)):
    data = await finance_rows(date_from, date_to, group if group in ("day", "month") else "day")
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["periode", "top_up", "pembeli", "kredit_terjual", "pendapatan_idr", "penyesuaian", "kredit_penyesuaian", "kredit_terpakai"])
    for r in data["rows"]:
        w.writerow([r["period"], r["topups"], r["buyers"], r["credits_sold"], r["revenue_idr"], r["adjustments"], r["credits_adjusted"], r["credits_consumed"]])
    t = data["total"]
    w.writerow(["TOTAL", t["topups"], t["buyers"], t["credits_sold"], t["revenue_idr"], t["adjustments"], t["credits_adjusted"], t["credits_consumed"]])
    w.writerow([]); w.writerow(["paket", "jumlah", "kredit", "pendapatan_idr"])
    for p in data["packages"]:
        w.writerow([p["package"], p["count"], p["credits"], p["revenue_idr"]])
    await _audit(u, "finance.export", f"{data['from']}..{data['to']}", {"group": data["group"]})
    name = f"oryntix-keuangan-{data['from']}-{data['to']}.csv"
    return StreamingResponse(iter(["\ufeff" + buf.getvalue()]), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="{name}"'})
