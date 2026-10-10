import io
from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse, Response
from db import db
from platform_api.csvsafe import SafeWriter
from auth import require_platform_staff
from platform_api.common import _audit

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
    from_date = start[:10]
    to_date = (datetime.fromisoformat(end) - timedelta(seconds=1)).date().isoformat()
    rows, packages, users = {}, {}, set()

    def row(k):
        return rows.setdefault(k, {"period": k, "topups": 0, "credits_sold": 0, "revenue_idr": 0, "adjustments": 0, "credits_adjusted": 0, "credits_consumed": 0, "buyers": set(),
                                   "expenses_idr": 0, "expense_dpp": 0, "ppn_in": 0})

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
    async for x in db.platform_expenses.find({"is_deleted": False, "date": {"$gte": from_date, "$lte": to_date}}, {"_id": 0, "date": 1, "amount_idr": 1, "dpp_idr": 1, "ppn_idr": 1}):
        r = row(_bucket(x["date"], group))
        r["expenses_idr"] += int(x.get("amount_idr") or 0); r["expense_dpp"] += int(x.get("dpp_idr") or 0); r["ppn_in"] += int(x.get("ppn_idr") or 0)

    out = sorted(rows.values(), key=lambda r: r["period"])
    for r in out:
        r["buyers"] = len(r["buyers"])
        # revenue is paid in full (incl. PPN keluaran 11%) → split DPP + PPN
        r["dpp_out"] = round(r["revenue_idr"] / 1.11)
        r["ppn_out"] = r["revenue_idr"] - r["dpp_out"]
        r["ppn_net"] = r["ppn_out"] - r["ppn_in"]  # PPN disetor = keluaran - masukan
        r["profit"] = r["dpp_out"] - r["expense_dpp"]  # laba bersih (basis DPP)
    keys = ("topups", "credits_sold", "revenue_idr", "adjustments", "credits_adjusted", "credits_consumed", "expenses_idr", "expense_dpp", "ppn_in", "dpp_out", "ppn_out", "ppn_net", "profit")
    total = {k: sum(r[k] for r in out) for k in keys}
    total["buyers"] = len(users)
    return {"from": from_date, "to": to_date, "group": group, "rows": out, "total": total,
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
    w = SafeWriter(buf, delimiter=";")
    w.writerow(["periode", "top_up", "pembeli", "kredit_terjual", "pendapatan_idr", "dpp_pendapatan", "ppn_keluaran", "pengeluaran_idr", "dpp_pengeluaran", "ppn_masukan", "ppn_disetor", "laba_bersih", "penyesuaian", "kredit_penyesuaian", "kredit_terpakai"])
    for r in data["rows"]:
        w.writerow([r["period"], r["topups"], r["buyers"], r["credits_sold"], r["revenue_idr"], r["dpp_out"], r["ppn_out"], r["expenses_idr"], r["expense_dpp"], r["ppn_in"], r["ppn_net"], r["profit"], r["adjustments"], r["credits_adjusted"], r["credits_consumed"]])
    t = data["total"]
    w.writerow(["TOTAL", t["topups"], t["buyers"], t["credits_sold"], t["revenue_idr"], t["dpp_out"], t["ppn_out"], t["expenses_idr"], t["expense_dpp"], t["ppn_in"], t["ppn_net"], t["profit"], t["adjustments"], t["credits_adjusted"], t["credits_consumed"]])
    w.writerow([]); w.writerow(["paket", "jumlah", "kredit", "pendapatan_idr"])
    for p in data["packages"]:
        w.writerow([p["package"], p["count"], p["credits"], p["revenue_idr"]])
    await _audit(u, "finance.export", f"{data['from']}..{data['to']}", {"group": data["group"]})
    name = f"oryntix-keuangan-{data['from']}-{data['to']}.csv"
    return StreamingResponse(iter(["\ufeff" + buf.getvalue()]), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="{name}"'})


async def _ppn_months(year: int) -> dict:
    """Monthly input/output VAT (SPT PPN) for a calendar year. Revenue is incl. PPN keluaran; expenses carry PPN masukan."""
    if year < 2000 or year > 2100:
        raise HTTPException(400, "Tahun tidak valid")
    months = [{"month": f"{year:04d}-{m:02d}", "revenue_idr": 0, "expenses_idr": 0, "ppn_out": 0, "ppn_in": 0, "dpp_out": 0, "expense_dpp": 0} for m in range(1, 13)]
    idx = {row["month"]: row for row in months}
    start, end = f"{year:04d}-01-01", f"{year + 1:04d}-01-01"
    async for t in db.credit_transactions.find({"type": "topup", "created_at": {"$gte": start, "$lt": end}}, {"_id": 0, "meta": 1, "created_at": 1}):
        key = t["created_at"][:7]
        if key in idx:
            idx[key]["revenue_idr"] += int((t.get("meta") or {}).get("price_idr") or 0)
    async for x in db.platform_expenses.find({"is_deleted": False, "date": {"$gte": f"{year:04d}-01-01", "$lte": f"{year:04d}-12-31"}}, {"_id": 0, "date": 1, "amount_idr": 1, "ppn_idr": 1, "dpp_idr": 1}):
        key = x["date"][:7]
        if key in idx:
            idx[key]["expenses_idr"] += int(x.get("amount_idr") or 0)
            idx[key]["ppn_in"] += int(x.get("ppn_idr") or 0)
            idx[key]["expense_dpp"] += int(x.get("dpp_idr") or 0)
    for r in months:
        r["dpp_out"] = round(r["revenue_idr"] / 1.11)
        r["ppn_out"] = r["revenue_idr"] - r["dpp_out"]
        r["ppn_net"] = r["ppn_out"] - r["ppn_in"]  # >0 kurang bayar, <0 lebih bayar
        r["profit"] = r["dpp_out"] - r["expense_dpp"]  # laba bersih basis DPP
    keys = ("revenue_idr", "expenses_idr", "ppn_out", "ppn_in", "ppn_net", "dpp_out", "expense_dpp", "profit")
    total = {k: sum(r[k] for r in months) for k in keys}
    return {"year": year, "months": months, "total": total}


@router.get("/ppn")
async def ppn_report(year: int, u: dict = Depends(require_platform_staff)):
    return await _ppn_months(year)


@router.get("/ppn/export.csv")
async def ppn_csv(year: int, u: dict = Depends(require_platform_staff)):
    data = await _ppn_months(year)
    buf = io.StringIO()
    w = SafeWriter(buf, delimiter=";")
    w.writerow(["bulan", "pendapatan_idr", "dpp_pendapatan", "ppn_keluaran", "pengeluaran_idr", "ppn_masukan", "ppn_disetor", "status"])
    for r in data["months"]:
        status = "lebih bayar" if r["ppn_net"] < 0 else ("kurang bayar" if r["ppn_net"] > 0 else "nihil")
        w.writerow([r["month"], r["revenue_idr"], r["dpp_out"], r["ppn_out"], r["expenses_idr"], r["ppn_in"], r["ppn_net"], status])
    t = data["total"]
    w.writerow(["TOTAL", t["revenue_idr"], t["dpp_out"], t["ppn_out"], t["expenses_idr"], t["ppn_in"], t["ppn_net"], ""])
    await _audit(u, "ppn.export", str(data["year"]), {})
    name = f"oryntix-spt-ppn-{data['year']}.csv"
    return StreamingResponse(iter(["\ufeff" + buf.getvalue()]), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="{name}"'})


# ---------- Profit & Loss (laba rugi) monthly export ----------
MONTH_ID = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]


def _rpid(n) -> str:
    return "Rp " + f"{int(n or 0):,}".replace(",", ".")


@router.get("/pnl")
async def pnl_report(year: int, u: dict = Depends(require_platform_staff)):
    return await _ppn_months(year)


@router.get("/pnl/export.csv")
async def pnl_csv(year: int, u: dict = Depends(require_platform_staff)):
    data = await _ppn_months(year)
    buf = io.StringIO()
    w = SafeWriter(buf, delimiter=";")
    w.writerow(["bulan", "pendapatan_idr", "dpp_pendapatan", "ppn_keluaran", "pengeluaran_idr", "dpp_pengeluaran", "ppn_masukan", "laba_bersih"])
    for r in data["months"]:
        w.writerow([r["month"], r["revenue_idr"], r["dpp_out"], r["ppn_out"], r["expenses_idr"], r["expense_dpp"], r["ppn_in"], r["profit"]])
    t = data["total"]
    w.writerow(["TOTAL", t["revenue_idr"], t["dpp_out"], t["ppn_out"], t["expenses_idr"], t["expense_dpp"], t["ppn_in"], t["profit"]])
    await _audit(u, "pnl.export", f"{year} csv", {})
    name = f"oryntix-laba-rugi-{year}.csv"
    return StreamingResponse(iter(["\ufeff" + buf.getvalue()]), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="{name}"'})


# ---------- Profit & Loss for a custom date range (day/month buckets) ----------
async def _pnl_range(date_from: Optional[str], date_to: Optional[str], group: str) -> dict:
    g = group if group in ("day", "month") else "month"
    return await finance_rows(date_from, date_to, g)


@router.get("/pnl/range")
async def pnl_range(date_from: Optional[str] = None, date_to: Optional[str] = None, group: str = "month", u: dict = Depends(require_platform_staff)):
    return await _pnl_range(date_from, date_to, group)


@router.get("/pnl/range/export.csv")
async def pnl_range_csv(date_from: Optional[str] = None, date_to: Optional[str] = None, group: str = "month", u: dict = Depends(require_platform_staff)):
    data = await _pnl_range(date_from, date_to, group)
    buf = io.StringIO()
    w = SafeWriter(buf, delimiter=";")
    w.writerow(["periode", "pendapatan_idr", "dpp_pendapatan", "ppn_keluaran", "pengeluaran_idr", "dpp_pengeluaran", "ppn_masukan", "laba_bersih"])
    for r in data["rows"]:
        w.writerow([r["period"], r["revenue_idr"], r["dpp_out"], r["ppn_out"], r["expenses_idr"], r["expense_dpp"], r["ppn_in"], r["profit"]])
    t = data["total"]
    w.writerow(["TOTAL", t["revenue_idr"], t["dpp_out"], t["ppn_out"], t["expenses_idr"], t["expense_dpp"], t["ppn_in"], t["profit"]])
    await _audit(u, "pnl.export", f"{data['from']}..{data['to']} csv", {"group": data["group"]})
    name = f"oryntix-laba-rugi-{data['from']}-{data['to']}.csv"
    return StreamingResponse(iter(["\ufeff" + buf.getvalue()]), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.get("/pnl/range/export.pdf")
async def pnl_range_pdf(date_from: Optional[str] = None, date_to: Optional[str] = None, group: str = "month", u: dict = Depends(require_platform_staff)):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet

    data = await _pnl_range(date_from, date_to, group)
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), topMargin=18 * mm, bottomMargin=16 * mm, leftMargin=14 * mm, rightMargin=14 * mm, title=f"Laba Rugi {data['from']}..{data['to']}")
    styles = getSampleStyleSheet()
    glabel = "per bulan" if data["group"] == "month" else "per hari"
    title = Paragraph("<b>Oryntix — Laporan Laba Rugi</b>", styles["Title"])
    sub = Paragraph(f"Periode {data['from']} s/d {data['to']} ({glabel}) · Dibuat {datetime.now(timezone.utc).strftime('%d %b %Y %H:%M UTC')} · PPN 11% (pendapatan sudah termasuk PPN)", styles["Normal"])
    header = ["Periode", "Pendapatan", "DPP Pend.", "PPN Keluaran", "Pengeluaran", "DPP Peng.", "PPN Masukan", "Laba Bersih"]
    rows = [header]
    for r in data["rows"]:
        rows.append([r["period"], _rpid(r["revenue_idr"]), _rpid(r["dpp_out"]), _rpid(r["ppn_out"]), _rpid(r["expenses_idr"]), _rpid(r["expense_dpp"]), _rpid(r["ppn_in"]), _rpid(r["profit"])])
    t = data["total"]
    rows.append(["TOTAL", _rpid(t["revenue_idr"]), _rpid(t["dpp_out"]), _rpid(t["ppn_out"]), _rpid(t["expenses_idr"]), _rpid(t["expense_dpp"]), _rpid(t["ppn_in"]), _rpid(t["profit"])])
    table = Table(rows, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0B132B")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#EEF3FF")),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, colors.HexColor("#F7F9FC")]),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#D8E0EC")),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    doc.build([title, sub, Spacer(1, 10), table])
    buf.seek(0)
    await _audit(u, "pnl.export", f"{data['from']}..{data['to']} pdf", {"group": data["group"]})
    return Response(content=buf.getvalue(), media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="oryntix-laba-rugi-{data["from"]}-{data["to"]}.pdf"'})


@router.get("/pnl/export.pdf")
async def pnl_pdf(year: int, u: dict = Depends(require_platform_staff)):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet

    data = await _ppn_months(year)
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), topMargin=18 * mm, bottomMargin=16 * mm, leftMargin=14 * mm, rightMargin=14 * mm, title=f"Laba Rugi {year}")
    styles = getSampleStyleSheet()
    title = Paragraph(f"<b>Oryntix — Laporan Laba Rugi {year}</b>", styles["Title"])
    sub = Paragraph(f"Dibuat {datetime.now(timezone.utc).strftime('%d %b %Y %H:%M UTC')} · PPN 11% (pendapatan sudah termasuk PPN)", styles["Normal"])
    header = ["Bulan", "Pendapatan", "DPP Pend.", "PPN Keluaran", "Pengeluaran", "DPP Peng.", "PPN Masukan", "Laba Bersih"]
    rows = [header]
    for i, r in enumerate(data["months"]):
        rows.append([MONTH_ID[i], _rpid(r["revenue_idr"]), _rpid(r["dpp_out"]), _rpid(r["ppn_out"]), _rpid(r["expenses_idr"]), _rpid(r["expense_dpp"]), _rpid(r["ppn_in"]), _rpid(r["profit"])])
    t = data["total"]
    rows.append(["TOTAL", _rpid(t["revenue_idr"]), _rpid(t["dpp_out"]), _rpid(t["ppn_out"]), _rpid(t["expenses_idr"]), _rpid(t["expense_dpp"]), _rpid(t["ppn_in"]), _rpid(t["profit"])])
    table = Table(rows, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0B132B")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#EEF3FF")),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, colors.HexColor("#F7F9FC")]),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#D8E0EC")),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    doc.build([title, sub, Spacer(1, 10), table])
    buf.seek(0)
    await _audit(u, "pnl.export", f"{year} pdf", {})
    return Response(content=buf.getvalue(), media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="oryntix-laba-rugi-{year}.pdf"'})
