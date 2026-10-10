"""Platform cron webhook endpoints (.emergent/crons.yml). Auth: Bearer WEBHOOK_CRON_SECRET. Ack 2xx fast, do work in background."""
import os
import hmac
from fastapi import APIRouter, Request, BackgroundTasks, Header, HTTPException

from db import db
from mailer import send_email, efaktur_reminder_email
from platform_api.expenses import generate_recurring, _month_str, _pending_efaktur_list, _check_budget_alerts

router = APIRouter(prefix="/api/platform/cron", tags=["platform-cron"])
SECRET = os.environ.get("WEBHOOK_CRON_SECRET")


def _check(authorization: str):
    token = (authorization or "").removeprefix("Bearer ").strip()
    if not SECRET or not token or not hmac.compare_digest(token, SECRET):
        raise HTTPException(401, "Unauthorized")


async def _run_recurring():
    try:
        await generate_recurring(_month_str(), "cron")
        await _check_budget_alerts()
    except Exception:
        pass


async def _run_efaktur_reminder():
    try:
        items = await _pending_efaktur_list()
        if not items:
            return
        recipients = [u["email"] async for u in db.users.find({"platform_role": "finance", "disabled": {"$ne": True}}, {"_id": 0, "email": 1})]
        if not recipients:
            return
        total_ppn = sum(int(e.get("ppn_idr") or 0) for e in items)
        link = (os.environ.get("PLATFORM_URL") or "").rstrip("/") + "/expenses"
        subject, html, text = efaktur_reminder_email(len(items), total_ppn, items, link)
        for to in recipients:
            await send_email(to, subject, html, text)
    except Exception:
        pass


@router.post("/recurring-expenses")
async def cron_recurring_expenses(request: Request, background: BackgroundTasks, authorization: str = Header(None)):
    # Cron endpoints must ack 2xx immediately; enqueue/background the actual work.
    _check(authorization)
    try:
        await request.json()
    except Exception:
        pass
    background.add_task(_run_recurring)
    return {"ok": True, "queued": True}


@router.post("/efaktur-reminder")
async def cron_efaktur_reminder(request: Request, background: BackgroundTasks, authorization: str = Header(None)):
    # Cron endpoints must ack 2xx immediately; enqueue/background the actual work.
    _check(authorization)
    try:
        await request.json()
    except Exception:
        pass
    background.add_task(_run_efaktur_reminder)
    return {"ok": True, "queued": True}
