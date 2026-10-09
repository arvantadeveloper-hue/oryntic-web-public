import asyncio, sys, json
from playwright.async_api import async_playwright
import sys as _sys; _sys.path.insert(0, '/app/backend/tests')  # noqa: E702
from creds import DEMO_PASSWORD, ADMIN_PASSWORD, BUDI_PASSWORD  # noqa: E402,F401

URL = "https://ai-companion-test-5.preview.emergentagent.com"
CID = sys.argv[1] if len(sys.argv) > 1 else "403c8205-7477-48af-af44-0b6bf83258e5"
BTN = sys.argv[2] if len(sys.argv) > 2 else "call-mode-btn"
WAIT = int(sys.argv[3]) if len(sys.argv) > 3 else 25


async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(args=["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream", "--autoplay-policy=no-user-gesture-required"])
        ctx = await b.new_context(permissions=["microphone"], viewport={"width": 1400, "height": 800})
        page = await ctx.new_page()
        logs = []
        page.on("console", lambda m: logs.append(f"{m.type}: {m.text[:300]}"))
        await page.add_init_script("localStorage.setItem('oryntix_tour_done','1')")
        await page.goto(URL, wait_until="networkidle")
        await page.fill("input[type=email]", "demo@aivora.ai")
        await page.fill("input[type=password]", DEMO_PASSWORD)
        await page.click("[data-testid=auth-submit-btn]")
        await page.wait_for_timeout(3000)
        # tap the data channel traffic so we can see raw GPT-Live events
        await page.add_init_script("""
          (() => { const o = RTCPeerConnection.prototype.createDataChannel; RTCPeerConnection.prototype.createDataChannel = function(...a) { const dc = o.apply(this, a); window.__dcs = (window.__dcs||[]); window.__dcs.push(dc); window.__dc = window.__dcs[0]; dc.addEventListener('message', (e) => { try { const ev = JSON.parse(e.data); window.__liveEvents = (window.__liveEvents||[]); window.__liveEvents.push(ev.type + (ev.type==='error' ? ' ' + JSON.stringify(ev.error) : ev.type==='session.closed' ? ' ' + ev.reason : ev.delta ? ' ' + ev.delta : '')); } catch (x) {} }); const s = dc.send.bind(dc); dc.send = (d) => { try { const ev = JSON.parse(d); (window.__liveOut = window.__liveOut||[]).push(ev.type + ' ' + (ev.content||'').slice(0,80)); } catch (x) {} return s(d); }; return dc; }; })();
        """)
        await page.goto(f"{URL}/chat/{CID}", wait_until="networkidle")
        await page.wait_for_timeout(2500)
        await page.click(f"[data-testid={BTN}]")
        for i in range(WAIT):
            await page.wait_for_timeout(1000)
            if i == 7:
                await page.evaluate("window.__dc && window.__dc.send(JSON.stringify({type:'session.instructions.append', event_id:'t1', delegation_id:null, content:'Immediately say the following greeting now, in Indonesian, before the caller says anything: Halo, saya Oryntix. Ada yang bisa saya bantu? Then pause and listen.'}))")
            if i in (6, 9, 10, 11, 12, 14, WAIT - 1):
                ph = await page.locator("[data-testid=rt-phase], [data-testid=rtm-status], [data-testid=rtm-phase]").all_inner_texts()
                print(f"t={i+1}s phase={ph}")
        await page.screenshot(path="/tmp/live_call.png", quality=30, type="jpeg")
        ev = await page.evaluate("window.__liveEvents || []")
        out = await page.evaluate("window.__liveOut || []")
        print("IN :", json.dumps(ev[:60], ensure_ascii=False))
        print("OUT:", json.dumps(out[:30], ensure_ascii=False))
        # hang up
        hang = page.locator("[data-testid=rt-end], [data-testid=rtm-leave], button:has-text('Akhiri')").first
        try:
            await hang.click(timeout=3000)
        except Exception as e:
            print("hangup click failed", e)
        await page.wait_for_timeout(2500)
        print("DC states:", await page.evaluate("(window.__dcs||[]).map(d=>d.readyState)"), "overlay:", await page.locator("[data-testid=realtime-call], [data-testid=rtm-phase]").count())
        ev2 = await page.evaluate("window.__liveEvents || []")
        print("AFTER HANGUP:", json.dumps(ev2[len(ev):], ensure_ascii=False), "OUT2:", json.dumps((await page.evaluate("window.__liveOut || []"))[len(out):], ensure_ascii=False))
        print("ERRORS:", [l for l in logs if l.startswith("error")][:10])
        await b.close()

asyncio.run(main())
