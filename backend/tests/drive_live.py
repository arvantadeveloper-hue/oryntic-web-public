"""Live Google Drive integration test on preview (requires a connected drive_credentials row). Run: python tests/drive_live.py"""
import asyncio
import json
import os
import sys

import httpx
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402
from auth import make_token  # noqa: E402

API = open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split("\n")[0].strip() + "/api"
db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
R = []


def ok(name, cond, info=""):
    R.append((name, bool(cond)))
    print(("PASS" if cond else "FAIL"), name, info)


async def sse(c, url, h, body):
    txt = ""
    async with c.stream("POST", url, headers=h, json=body, timeout=180) as r:
        async for line in r.aiter_lines():
            if line.startswith("data: ") and line[6:] != "[DONE]":
                try:
                    txt += json.dumps(json.loads(line[6:])) + "\n"
                except Exception:
                    pass
    return txt


async def main():
    cred = await db.drive_credentials.find_one({}, {"_id": 0})
    assert cred, "no drive connection"
    u = await db.users.find_one({"id": cred["user_id"]})
    h = {"Authorization": f"Bearer {make_token(u['id'], 'admin')}"}
    async with httpx.AsyncClient(timeout=120) as c:
        st = (await c.get(f"{API}/integrations/google/status", headers=h)).json()
        ok("status connected+picker", st.get("connected") and st.get("picker"), st)
        # save doc (markdown with table)
        md = "# Laporan Uji Oryntix\n\nIni dokumen uji otomatis.\n\n| Item | Qty |\n|---|---|\n| Apel | 3 |\n| Jeruk | 5 |\n"
        r = await c.post(f"{API}/integrations/google/save", headers=h, json={"title": "Uji Oryntix Doc", "kind": "doc", "content": md})
        ok("save doc", r.status_code == 200 and r.json().get("link"), r.text[:200])
        doc = r.json()
        r = await c.post(f"{API}/integrations/google/save", headers=h, json={"title": "Uji Oryntix Sheet", "kind": "sheet", "content": md})
        ok("save sheet", r.status_code == 200 and "spreadsheet" in (r.json().get("mime") or ""), r.text[:200])
        # files list shows app-created files
        r = await c.get(f"{API}/integrations/google/files", headers=h)
        names = [f["name"] for f in r.json().get("files", [])]
        ok("files list has created docs", "Uji Oryntix Doc" in names, names[:5])
        r = await c.get(f"{API}/integrations/google/files", headers=h, params={"q": "Uji Oryntix"})
        ok("files search", len(r.json().get("files", [])) >= 2, len(r.json().get("files", [])))
        # update by name
        r = await c.post(f"{API}/integrations/google/update", headers=h, json={"file": "Uji Oryntix Doc", "text": "Bagian tambahan: anggaran Rp 1.000.000", "mode": "append"})
        ok("update doc", r.status_code == 200, r.text[:200])
        # read content
        r = await c.get(f"{API}/integrations/google/content", headers=h, params={"file_id": doc["drive_id"]})
        ok("content read incl. update", r.status_code == 200 and "anggaran" in r.json().get("text", "") and "Apel" in r.json().get("text", ""), r.json().get("text", "")[:120])
        # link
        r = await c.post(f"{API}/integrations/google/link", headers=h, json={"file": "Uji Oryntix Doc", "share": False})
        ok("link", r.status_code == 200 and r.json().get("webViewLink"), r.text[:150])
        # persona for chat/knowledge
        p = await db.personas.find_one({"user_id": u["id"], "deleted": {"$ne": True}}, {"_id": 0})
        if not p:
            r = await c.post(f"{API}/personas", headers=h, json={"profile": {"identity": {"name": "Nova", "summary": "asisten uji"}, "system_instructions": "Asisten ringkas."}})
            p = r.json()
        # knowledge from drive
        r = await c.post(f"{API}/personas/{p['id']}/knowledge", headers=h, json={"title": "", "drive_id": doc["drive_id"]})
        ok("knowledge from drive", r.status_code == 200 and r.json().get("source") == "drive" and r.json().get("chunk_count", 0) >= 1, r.text[:200])
        kid = r.json().get("id")
        r = await c.post(f"{API}/personas/{p['id']}/knowledge/{kid}/refresh", headers=h)
        ok("knowledge refresh", r.status_code == 200, r.text[:120])
        r = await c.get(f"{API}/personas/{p['id']}/knowledge", headers=h)
        ok("knowledge list drive_link", any(d.get("drive_link") for d in r.json()), "")
        # chat attachment from drive
        conv = (await c.post(f"{API}/conversations/direct", headers=h, json={"persona_id": p["id"]})).json()
        out = await sse(c, f"{API}/conversations/{conv['id']}/send", h, {"content": "Berapa jumlah Jeruk dalam tabel lampiran? Jawab singkat.", "attachments": [{"type": "drive", "drive_id": doc["drive_id"], "name": doc["name"], "mime": doc["mime"], "link": doc["link"]}]})
        um = await db.messages.find_one({"conversation_id": conv["id"], "role": "user"}, sort=[("created_at", -1)])
        ok("drive attachment text injected", "Jeruk" in (um.get("attachment_text") or "") and um["attachments"][0].get("drive_id") == doc["drive_id"], (um.get("attachment_text") or "")[:80])
        ok("assistant answered using attachment", "5" in out, out[-300:])
        # chat drive_save tool
        out = await sse(c, f"{API}/conversations/{conv['id']}/send", h, {"content": "Simpan ke Google Drive sebagai dokumen berjudul 'Catatan Uji Chat' dengan isi: Rapat 6 Oktober membahas anggaran dan jadwal."})
        ok("chat drive_save", "drive_save" in out and "docs.google.com" in out, out[-300:])
        out = await sse(c, f"{API}/conversations/{conv['id']}/send", h, {"content": "Kirim link drive dokumen Catatan Uji Chat"})
        ok("chat drive_link", "drive_link" in out and "docs.google.com" in out, out[-200:])
        out = await sse(c, f"{API}/conversations/{conv['id']}/send", h, {"content": "Update dokumen Catatan Uji Chat di Google Drive, tambahkan kalimat: Tindak lanjut minggu depan."})
        ok("chat drive_update", "drive_update" in out, out[-200:])
        r = await c.get(f"{API}/integrations/google/content", headers=h, params={"file_id": (await db.drive_items.find_one({"name": "Catatan Uji Chat"}, {"_id": 0}))["drive_id"]})
        ok("updated content visible", "Tindak lanjut" in r.json().get("text", ""), r.json().get("text", "")[:100])
        # picker token
        r = await c.get(f"{API}/integrations/google/picker-token", headers=h)
        ok("picker-token", r.status_code == 200 and r.json().get("api_key") and r.json().get("app_id"), r.status_code)
        # access control: another user cannot read via drive (no connection)
        other = await db.users.find_one({"email": "budi@aivora.ai"})
        h2 = {"Authorization": f"Bearer {make_token(other['id'], 'user')}"}
        r = await c.get(f"{API}/integrations/google/files", headers=h2)
        ok("not-connected user gets 400", r.status_code == 400, r.text[:100])
    print(f"\n{sum(1 for _, v in R if v)}/{len(R)} passed")


asyncio.run(main())
