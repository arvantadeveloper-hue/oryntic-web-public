"""Probe GPT-Live over WebSocket (no browser): start a session, append a greeting instruction, stream silence, print events."""
import asyncio, base64, json, os, sys, time
import websockets
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
KEY = os.environ["OPENAI_API_KEY"]
MODE = sys.argv[1] if len(sys.argv) > 1 else "greet"


async def main():
    url = "wss://api.openai.com/v1/live/sessions"
    async with websockets.connect(url, additional_headers={"Authorization": f"Bearer {KEY}"}, max_size=None) as ws:
        session = {"model": "gpt-live-1", "instructions": "You are Oryntix, a friendly support assistant. Speak Indonesian. Keep turns short.",
                   "audio": {"output": {"voice": "marin"}, "format": {"type": "audio/pcm", "rate": 24000}},
                   "delegation": {"type": "responses", "responses": {"model": "gpt-6-luna", "instructions": "Answer briefly.", "tools": [{"type": "function", "name": "get_time", "description": "Current time in a city", "parameters": {"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]}}] + ([{"type": "file_search", "vector_store_ids": [os.environ["PROBE_VS"]], "max_num_results": 6}] if os.environ.get("PROBE_VS") else []), "tool_choice": "auto"}}}
        await ws.send(json.dumps({"type": "session.start", "session": session}))
        t0 = time.time(); started = False; sent = False; silence = base64.b64encode(b"\x00" * 4800).decode()
        out = ""
        while time.time() - t0 < 40:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=0.2)
            except asyncio.TimeoutError:
                if started:
                    await ws.send(json.dumps({"type": "session.input_audio.append", "audio": silence}))
                    if not sent and time.time() - t0 > 3:
                        sent = True
                        content = "Immediately say the following greeting now, in Indonesian, before the caller says anything: Halo, saya Oryntix. Ada yang bisa saya bantu? Then pause and listen." if MODE == "greet" else "The caller just asked: what time is it in Jakarta right now? Immediately delegate this to your backend (it has the get_time tool), then tell the caller the answer in Indonesian."
                        if MODE == "typed":
                            await ws.send(json.dumps({"type": "response.item.create", "event_id": "u1", "item": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": os.environ.get("PROBE_Q", "Jam berapa sekarang di Jakarta? Pakai tool get_time.")}]}}))
                            await ws.send(json.dumps({"type": "response.create", "event_id": "c0"}))
                        else:
                            await ws.send(json.dumps({"type": "session.instructions.append", "event_id": "t1", "delegation_id": None, "content": content}))
                continue
            ev = json.loads(raw)
            t = ev.get("type")
            if t == "session.started":
                started = True; print("started", ev.get("session", {}).get("id"))
            elif t == "session.output_audio.delta":
                n_audio = globals().get("n_audio", 0) + 1; globals()["n_audio"] = n_audio
                if n_audio in (1, 50, 200): print("AUDIO delta #", n_audio, "bytes", len(ev.get("delta") or ""))
                continue
            elif t == "session.output_transcript.delta":
                out += ev.get("delta", ""); print("OUT Δ", repr(ev.get("delta")), ev.get("start_ms"), ev.get("end_ms"))
            elif t == "response.event":
                e = ev["event"]; print("RESP", e.get("type"), json.dumps(e.get("item") or {})[:200] if e.get("type") == "response.output_item.done" else "")
                if e.get("type") == "response.output_item.done" and (e.get("item") or {}).get("type") == "function_call":
                    await ws.send(json.dumps({"type": "response.item.create", "event_id": "r1", "item": {"type": "function_call_output", "call_id": e["item"]["call_id"], "output": json.dumps({"time": "14:05 WIB"})}}))
                    await ws.send(json.dumps({"type": "response.create", "event_id": "c1"}))
            else:
                print("EV", t, json.dumps({k: v for k, v in ev.items() if k not in ("type", "event_id")})[:300])
        print("TRANSCRIPT:", out)
        await ws.send(json.dumps({"type": "session.close"}))
        try:
            while True:
                ev = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
                if ev.get("type") == "session.closed":
                    print("closed", ev.get("reason"), ev.get("usage")); break
        except Exception as exc:
            print("close wait:", exc)

asyncio.run(main())
