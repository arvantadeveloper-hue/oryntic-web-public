import json, requests, sys, asyncio
from datetime import datetime, timezone, timedelta
API = open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split("\n")[0].strip() + "/api"
sys.path.insert(0, "/app/backend")
from dotenv import load_dotenv; load_dotenv("/app/backend/.env")


async def main():
    from db import db
    from auth import make_token
    import reminders as rem
    from reminders import next_occurrence, _parse
    # pure function
    jan31 = datetime(2026, 1, 31, 9, 0, tzinfo=timezone.utc)
    print("monthly from 31 Jan →", next_occurrence(jan31, "monthly", jan31).date(), "→", next_occurrence(jan31, "monthly", datetime(2026, 2, 28, 10, tzinfo=timezone.utc)).date())
    print("weekly →", next_occurrence(jan31, "weekly", jan31).date(), "daily →", next_occurrence(jan31, "daily", datetime(2026, 2, 3, 10, tzinfo=timezone.utc)))
    u = await db.users.find_one({"email": "demo@aivora.ai"})
    H = {"Authorization": f"Bearer {make_token(u['id'], 'admin')}"}
    now = datetime.now(timezone.utc)
    # 1. daily reminder created with a start in the past → first occurrence rolled to the future
    past = (now - timedelta(days=3)).replace(second=0, microsecond=0)
    r = requests.post(f"{API}/reminders", headers=H, json={"title": "Minum obat", "start_at": past.isoformat(), "offsets": [10], "mode": "chat", "repeat": "daily"}).json()
    st = _parse(r["start_at"]); print("daily created: repeat", r["repeat"], "start future:", st > now, "same clock:", st.time() == past.time(), "occ", r["occurrence"])
    # 2. event with weekly reminder → event.remind.repeat
    ev = requests.post(f"{API}/events", headers=H, json={"title": "Standup tim", "start_at": (now + timedelta(hours=1)).isoformat(), "remind_mode": "call", "remind_offsets": [10], "repeat": "weekly"}).json()
    print("event remind:", ev["remind"])
    # 3. simulate: alert fired & start passed → scheduler rolls to next week, event start synced, status scheduled
    old_start = _parse(ev["start_at"])
    await db.reminders.update_one({"id": ev["reminder_id"]}, {"$set": {"start_at": (now - timedelta(minutes=5)).isoformat(), "status": "answered", "alerts.0.status": "fired"}})
    await db.events.update_one({"id": ev["id"]}, {"$set": {"start_at": (now - timedelta(minutes=5)).isoformat()}})
    await rem.scheduler_tick()
    rr = await db.reminders.find_one({"id": ev["reminder_id"]}, {"_id": 0}); e2 = await db.events.find_one({"id": ev["id"]}, {"_id": 0})
    nxt = _parse(rr["start_at"])
    print("rolled: status", rr["status"], "occ", rr["occurrence"], "next in ~7d:", 6.9 < (nxt - now).total_seconds() / 86400 < 7.1, "alerts", [(a["minutes"], a["status"]) for a in rr["alerts"]], "event synced:", e2["start_at"] == rr["start_at"])
    # 4. ringing repeating reminder is NOT rolled
    await db.reminders.update_one({"id": ev["reminder_id"]}, {"$set": {"start_at": (now - timedelta(minutes=5)).isoformat(), "status": "ringing"}})
    await rem.scheduler_tick()
    rr2 = await db.reminders.find_one({"id": ev["reminder_id"]}, {"_id": 0}); print("ringing kept:", rr2["status"] == "ringing" and rr2["occurrence"] == rr["occurrence"])
    # 5. repeating reminder far in the past is rolled, not 'missed'
    await db.reminders.update_one({"id": ev["reminder_id"]}, {"$set": {"start_at": (now - timedelta(days=20)).isoformat(), "status": "scheduled", "alerts.0.remind_at": (now - timedelta(days=21)).isoformat(), "alerts.0.status": "scheduled"}})
    await rem.scheduler_tick()
    rr3 = await db.reminders.find_one({"id": ev["reminder_id"]}, {"_id": 0}); print("stale repeating → status", rr3["status"], "future:", _parse(rr3["start_at"]) > now)
    # 6. PUT repeat change syncs event
    requests.put(f"{API}/reminders/{ev['reminder_id']}", headers=H, json={"repeat": "monthly"})
    e3 = await db.events.find_one({"id": ev["id"]}, {"_id": 0, "remind": 1}); print("event repeat after PUT:", e3["remind"]["repeat"])
    # 6b. purge: non-repeating reminders with start ≥1h in the past are deleted (sent/answered/declined/missed/scheduled), ringing kept, repeating kept, event kept
    ids = {}
    for st in ("sent", "answered", "declined", "missed", "scheduled", "ringing"):
        d = requests.post(f"{API}/reminders", headers=H, json={"title": f"old-{st}", "start_at": (now + timedelta(hours=2)).isoformat(), "offsets": [30]}).json()
        await db.reminders.update_one({"id": d["id"]}, {"$set": {"status": st, "start_at": (now - timedelta(hours=2)).isoformat(), "alerts.0.status": "fired"}})
        ids[st] = d["id"]
    recent = requests.post(f"{API}/reminders", headers=H, json={"title": "recent-sent", "start_at": (now + timedelta(hours=2)).isoformat(), "offsets": [30]}).json()
    await db.reminders.update_one({"id": recent["id"]}, {"$set": {"status": "sent", "start_at": (now - timedelta(minutes=20)).isoformat()}})
    await rem.scheduler_tick()
    left = {x["title"] for x in await db.reminders.find({"user_id": u["id"], "title": {"$regex": "^old-|^recent-"}}, {"_id": 0, "title": 1}).to_list(50)}
    print("purge → left:", sorted(left), "| repeating kept:", bool(await db.reminders.find_one({"id": ev["reminder_id"]})), "| event kept:", bool(await db.events.find_one({"id": ev["id"]})))
    await db.reminders.delete_many({"user_id": u["id"], "title": {"$regex": "^old-|^recent-"}})
    # cleanup
    requests.delete(f"{API}/reminders/{r['id']}", headers=H); requests.delete(f"{API}/events/{ev['id']}", headers=H)
    # 7. chat: "setiap hari"
    p = requests.get(f"{API}/personas", headers=H).json()[0]
    cid = requests.post(f"{API}/conversations/direct", headers=H, json={"persona_id": p["id"]}).json()["id"]
    final = None
    with requests.post(f"{API}/conversations/{cid}/send", headers=H, json={"content": "Ingatkan saya setiap hari jam 7 pagi untuk olahraga, lewat chat 10 menit sebelum."}, stream=True, timeout=120) as s:
        for line in s.iter_lines():
            if line and line.startswith(b"data: "):
                try: evt = json.loads(line[6:])
                except Exception: continue
                if evt.get("final"): final = evt
    print("chat →", (final or {}).get("tool"), (final or {}).get("content", "")[:200].replace("\n", " "))
    evd = await db.events.find_one({"user_id": u["id"], "title": {"$regex": "olahraga", "$options": "i"}}, sort=[("created_at", -1)])
    print("   event:", evd and evd["remind"])
    if evd: requests.delete(f"{API}/events/{evd['id']}", headers=H)
asyncio.run(main())
