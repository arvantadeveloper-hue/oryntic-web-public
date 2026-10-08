import asyncio, sys, requests
sys.path.insert(0, "/app/backend")
from dotenv import load_dotenv; load_dotenv("/app/backend/.env")
API = open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split("\n")[0].strip() + "/api"
async def main():
    from db import db, new_id, now_iso
    from auth import make_token
    from pending_files import hold_file
    demo = await db.users.find_one({"email": "demo@aivora.ai"})
    other = await db.users.find_one({"email": {"$ne": "demo@aivora.ai"}, "role": {"$exists": True}})
    f = await hold_file(demo["id"], 'weird "name"\r\n.png', "image/png", b"\x89PNG fake", {"source": "test"})
    print("held:", f["name"], f["kind"])
    # a message in a conversation the demo user does NOT own
    conv_id, msg_id = new_id(), new_id()
    await db.conversations.insert_one({"id": conv_id, "user_id": other["id"], "participants": [other["id"]], "type": "private", "created_at": now_iso()})
    await db.messages.insert_one({"id": msg_id, "conversation_id": conv_id, "role": "assistant", "content": "x", "media": [], "created_at": now_iso()})
    H = {"Authorization": f"Bearer {make_token(demo['id'], 'admin')}"}
    r = requests.post(f"{API}/pending-files/{f['id']}/save", headers=H, json={"message_id": msg_id, "target": "storage"})
    print("cross-user save →", r.status_code, r.json().get("detail"))
    m = await db.messages.find_one({"id": msg_id}); print("other's media untouched:", m["media"] == [])
    # own message: concurrent double save → one 200, one 409/404
    own_conv, own_msg = new_id(), new_id()
    await db.conversations.insert_one({"id": own_conv, "user_id": demo["id"], "participants": [demo["id"]], "type": "private", "created_at": now_iso()})
    await db.messages.insert_one({"id": own_msg, "conversation_id": own_conv, "role": "assistant", "content": "x", "media": [], "pending_files": [f], "created_at": now_iso()})
    pv = requests.get(f"{API}/pending-files/{f['id']}", headers=H); print("preview:", pv.status_code, pv.headers.get("content-disposition"))
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(2) as ex:
        rs = list(ex.map(lambda _: requests.post(f"{API}/pending-files/{f['id']}/save", headers=H, json={"message_id": own_msg, "target": "storage"}).status_code, range(2)))
    print("concurrent saves →", sorted(rs))
    m = await db.messages.find_one({"id": own_msg}); print("media count:", len(m["media"]), "pending left:", len(m.get("pending_files", [])))
    await db.conversations.delete_many({"id": {"$in": [conv_id, own_conv]}}); await db.messages.delete_many({"id": {"$in": [msg_id, own_msg]}})
asyncio.run(main())
