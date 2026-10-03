import asyncio, traceback, os
from dotenv import dotenv_values
os.environ.update({k: v for k, v in dotenv_values('/app/backend/.env').items() if v})
async def m():
    from assignments import _maybe_assemble
    from db import db
    pid = open('/app/memory/tmp/ptid').read().strip()
    kids = await db.tasks.find({"parent_id": pid}, {"_id":0,"status":1,"goal":1}).to_list(10)
    print("kids", [(k['goal'][:20], k['status']) for k in kids])
    try:
        await _maybe_assemble(pid)
    except Exception:
        traceback.print_exc()
    p = await db.tasks.find_one({"id": pid}, {"_id":0,"status":1,"final_output":1,"error":1})
    print(p['status'], len(p.get('final_output') or ''), p.get('error'))
asyncio.run(m())
