import json, requests, sys, asyncio, time
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
    start = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
    # 1. reminder with 2 offsets, chat mode
    r = requests.post(f"{API}/reminders", headers=H, json={"title": "Rapat uji", "start_at": start, "offsets": [30, 60], "mode": "chat"}).json()
    print("reminder:", r["mode"], r["offsets"], [a["minutes"] for a in r["alerts"]], r["remind_minutes"])
    # 2. event with reminders → linked reminder appears in /reminders with event_id; calendar shows event (not duplicate reminder)
    ev = requests.post(f"{API}/events", headers=H, json={"title": "Presentasi klien", "start_at": start, "notes": "Ruang A", "remind_mode": "call", "remind_offsets": [30, 60]}).json()
    print("event remind:", ev["remind"], "reminder_id:", bool(ev["reminder_id"]))
    lst = requests.get(f"{API}/reminders", headers=H).json()
    linked = [x for x in lst if x.get("event_id") == ev["id"]]
    print("linked reminder in /reminders:", len(linked) == 1, linked[0]["title"] if linked else None)
    s = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(); e = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
    cal = requests.get(f"{API}/calendar", headers=H, params={"start": s, "end": e}).json()
    kinds = [(c["kind"], c["title"], c.get("remind") and c["remind"]["mode"]) for c in cal if c["title"] in ("Rapat uji", "Presentasi klien")]
    print("calendar items:", kinds)
    # 3. delete event → linked reminder gone
    requests.delete(f"{API}/events/{ev['id']}", headers=H)
    print("reminder removed with event:", not any(x.get("event_id") == ev["id"] for x in requests.get(f"{API}/reminders", headers=H).json()))
    # 4. scheduler: chat-mode reminder due now → message posted to private chat
    due = await db.reminders.find_one({"id": r["id"]})
    past = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    await db.reminders.update_one({"id": r["id"]}, {"$set": {"alerts.0.remind_at": past}})
    await rem.scheduler_tick()
    after = await db.reminders.find_one({"id": r["id"]}, {"_id": 0})
    print("after tick: status", after["status"], "alerts", [(a["minutes"], a["status"]) for a in after["alerts"]])
    msg = await db.messages.find_one({"tool": "reminder", "reminder.id": r["id"]}, {"_id": 0})
    print("chat reminder msg:", bool(msg), (msg or {}).get("content", "")[:120].replace("\n", " "), "| minutes:", (msg or {}).get("reminder", {}).get("minutes"))
    # second alert (60) still scheduled → tick again should not fire it
    await rem.scheduler_tick()
    after2 = await db.reminders.find_one({"id": r["id"]}, {"_id": 0}); print("second tick unchanged:", [(a["minutes"], a["status"]) for a in after2["alerts"]] == [(a["minutes"], a["status"]) for a in after["alerts"]])
    # 5. call-mode reminder due → ringing + /incoming
    r2 = requests.post(f"{API}/reminders", headers=H, json={"title": "Telepon uji", "start_at": start, "offsets": [30], "mode": "call"}).json()
    await db.reminders.update_one({"id": r2["id"]}, {"$set": {"alerts.0.remind_at": past}})
    await rem.scheduler_tick()
    inc = requests.get(f"{API}/reminders/incoming", headers=H).json(); print("incoming ringing:", [i["title"] for i in inc])
    # 6. legacy reminder (no alerts) still fires
    await db.reminders.insert_one({"id": "legacy-test", "user_id": u["id"], "title": "Legacy", "start_at": start, "remind_minutes": 30, "remind_at": past, "status": "scheduled", "created_at": past})
    await rem.scheduler_tick()
    leg = await db.reminders.find_one({"id": "legacy-test"}, {"_id": 0, "status": 1}); print("legacy →", leg["status"])
    # cleanup
    for rid in (r["id"], r2["id"], "legacy-test"):
        requests.delete(f"{API}/reminders/{rid}", headers=H)
    await db.reminders.delete_one({"id": "legacy-test"})
    # 7. chat intercept: "catat ... ingatkan"
    p = requests.get(f"{API}/personas", headers=H).json()[0]
    cid = requests.post(f"{API}/conversations/direct", headers=H, json={"persona_id": p["id"]}).json()["id"]
    for text in ["Catat ya: rapat dengan Budi besok jam 10 pagi di kantor, ingatkan 30 menit dan 1 jam sebelum lewat chat.", "Ingatkan saya minggu depan untuk bayar listrik"]:
        final = None
        with requests.post(f"{API}/conversations/{cid}/send", headers=H, json={"content": text}, stream=True, timeout=120) as s:
            for line in s.iter_lines():
                if line and line.startswith(b"data: "):
                    try: ev = json.loads(line[6:])
                    except Exception: continue
                    if ev.get("final"): final = ev
        print("chat →", (final or {}).get("tool"), (final or {}).get("content", "")[:160].replace("\n", " "))
        if (final or {}).get("tool") == "calendar_event":
            evd = await db.events.find_one({"title": {"$regex": "Budi|Rapat", "$options": "i"}, "user_id": u["id"]}, sort=[("created_at", -1)])
            print("   event saved:", evd and (evd["title"], evd["start_at"], evd["remind"]))
            requests.delete(f"{API}/events/{evd['id']}", headers=H)
asyncio.run(main())
