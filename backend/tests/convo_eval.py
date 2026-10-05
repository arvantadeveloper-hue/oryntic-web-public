"""Conversational-behaviour test against the REAL Realtime model using the same session instructions the app builds
(text in → text out, so it runs headless). Usage: python tests/convo_eval.py"""
import asyncio
import json
import os
import sys
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

SCENARIOS = [
    ("casual", ["Halo Rio, lagi ngapain?"]),
    ("hmm", ["Hmm..."]),
    ("iya", ["Oke, ngerti."]),
    ("statement", ["Capek banget hari ini."]),
    ("joke", ["Kayaknya aku butuh asisten buat ngingetin aku pakai asisten, haha."]),
    ("context+yang tadi", ["Aku lagi bikin avatar 2.5D buat asisten di aplikasiku.", "Menurutmu worth it nggak?", "Yang tadi gimana?"]),
    ("topic change", ["Tadi kita ngomongin React ya.", "Oh iya, eh ngomong-ngomong Putin pernah jadi KGB nggak?"]),
    ("bukan itu", ["Aku mau nanya soal harga.", "Bukan itu maksudku, maksudku harga token Realtime per menit kira-kira berapa."]),
    ("technical", ["Jelasin dong bedanya WebRTC sama WebSocket buat streaming audio realtime, dan kapan sebaiknya pakai yang mana."]),
    ("unfinished", ["Aku sebenarnya mau..."]),
]
BAD = ["ada yang bisa saya bantu", "tentu", ", demo", "\n- ", "baik, saya mengerti", "terima kasih atas informasinya", "dengan senang hati", "berikut adalah",
       "sebagai ai", "saya memahami", "apakah ada hal lain", "berpindah topik", "menganalisis pertanyaan anda"]


async def main():
    import websockets
    from db import db
    from realtime_voice import _session_instructions
    u = await db.users.find_one({"email": "demo@aivora.ai"}, {"_id": 0})
    p = await db.personas.find_one({"id": "e93a66a6-59b1-4a12-8c16-0c9dba6c3348"}, {"_id": 0})
    instr = await _session_instructions(p, u, [p["name"]], "", None, "solo")
    url = f"wss://api.openai.com/v1/realtime?model={os.environ.get('OPENAI_REALTIME_MODEL', 'gpt-realtime')}"
    hdr = {"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"}
    report = []
    for name, turns in SCENARIOS:
        async with websockets.connect(url, additional_headers=hdr, max_size=2**23) as ws:
            await ws.send(json.dumps({"type": "session.update", "session": {"type": "realtime", "instructions": instr, "output_modalities": ["text"], "audio": {"input": {"turn_detection": None}}}}))
            lines = []
            for t in turns:
                await ws.send(json.dumps({"type": "conversation.item.create", "item": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": t}]}}))
                await ws.send(json.dumps({"type": "response.create"}))
                out = ""
                while True:
                    ev = json.loads(await asyncio.wait_for(ws.recv(), 60))
                    if ev["type"] == "response.output_text.delta":
                        out += ev["delta"]
                    elif ev["type"] == "response.done":
                        break
                    elif ev["type"] == "error":
                        out += f"[ERROR {ev.get('error')}]"; break
                flags = [b for b in BAD if b in out.lower()]
                lines.append((t, out.strip(), len(out.split()), flags))
            report.append((name, lines))
    for name, lines in report:
        print(f"\n=== {name} ===")
        for t, out, words, flags in lines:
            print(f"USER: {t}\nRIO : {out}  ({words} kata){'  ⚠ ' + ', '.join(flags) if flags else ''}")

asyncio.run(main())
