import requests, sys, asyncio
from datetime import datetime, timezone, timedelta
API = open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split("\n")[0].strip() + "/api"
sys.path.insert(0, "/app/backend")
from dotenv import load_dotenv; load_dotenv("/app/backend/.env")


async def main():
    from db import db
    from auth import make_token
    import reminders as rem
    u = await db.users.find_one({"email": "demo@aivora.ai"})
    H = {"Authorization": f"Bearer {make_token(u['id'], 'admin')}"}
    now = datetime.now(timezone.utc)
    # call-mode reminder ringing → snooze 10 → status snoozed, extra alert, incoming empty
    r = requests.post(f"{API}/reminders", headers=H, json={"title": "Snooze uji", "start_at": (now + timedelta(minutes=40)).isoformat(), "offsets": [30], "mode": "call"}).json()
    await db.reminders.update_one({"id": r["id"]}, {"$set": {"alerts.0.remind_at": (now - timedelta(minutes=1)).isoformat()}})
    await rem.scheduler_tick()
    print("ringing:", [i["title"] for i in requests.get(f"{API}/reminders/incoming", headers=H).json()])
    sn = requests.post(f"{API}/reminders/{r['id']}/snooze", headers=H, json={"minutes": 10}).json(); print("snooze →", sn["status"], sn["minutes"])
    d = await db.reminders.find_one({"id": r["id"]}, {"_id": 0}); print("alerts:", [(a["minutes"], a["status"], a.get("snoozed", False)) for a in d["alerts"]], "incoming now:", len(requests.get(f"{API}/reminders/incoming", headers=H).json()))
    # fast-forward snooze → rings again with snoozed flag
    await db.reminders.update_one({"id": r["id"]}, {"$set": {"alerts.1.remind_at": (now - timedelta(seconds=5)).isoformat()}})
    await rem.scheduler_tick()
    d = await db.reminders.find_one({"id": r["id"]}, {"_id": 0}); print("after snooze due → status", d["status"], "ringing_snoozed", d.get("ringing_snoozed"))
    # chat-mode: snooze from message → new chat message with reminder.snoozed True
    r2 = requests.post(f"{API}/reminders", headers=H, json={"title": "Chat snooze uji", "start_at": (now + timedelta(minutes=40)).isoformat(), "offsets": [30], "mode": "chat"}).json()
    requests.post(f"{API}/reminders/{r2['id']}/snooze", headers=H, json={"minutes": 10})
    await db.reminders.update_one({"id": r2["id"]}, {"$set": {"alerts.$[a].remind_at": (now - timedelta(seconds=5)).isoformat()}}, array_filters=[{"a.snoozed": True}])
    await rem.scheduler_tick()
    m = await db.messages.find_one({"tool": "reminder", "reminder.id": r2["id"]}, {"_id": 0}, sort=[("created_at", -1)])
    print("chat snoozed msg:", bool(m), m and m["reminder"].get("snoozed"), (m or {}).get("content", "")[:100].replace("\n", " "))
    # purge must not delete a past reminder that still has a future snooze
    r3 = requests.post(f"{API}/reminders", headers=H, json={"title": "Past+snooze", "start_at": (now + timedelta(hours=1)).isoformat(), "offsets": [30], "mode": "chat"}).json()
    await db.reminders.update_one({"id": r3["id"]}, {"$set": {"start_at": (now - timedelta(hours=2)).isoformat(), "status": "sent", "alerts.0.status": "fired"}})
    requests.post(f"{API}/reminders/{r3['id']}/snooze", headers=H, json={"minutes": 10})
    await rem.scheduler_tick()
    print("past reminder with future snooze kept:", bool(await db.reminders.find_one({"id": r3["id"]})))
    for x in (r, r2, r3):
        requests.delete(f"{API}/reminders/{x['id']}", headers=H)
    requests.post(f"{API}/reminders/{r['id']}/snooze", headers=H, json={"minutes": 10}).status_code == 404 and print("snooze on deleted → 404")
asyncio.run(main())
