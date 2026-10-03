import json
import asyncio
from typing import Dict, Set

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self):
        self.rooms: Dict[str, Set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, cid: str, ws: WebSocket):
        await ws.accept()
        async with self._lock:
            self.rooms.setdefault(cid, set()).add(ws)

    async def disconnect(self, cid: str, ws: WebSocket):
        async with self._lock:
            conns = self.rooms.get(cid)
            if conns and ws in conns:
                conns.discard(ws)
                if not conns:
                    self.rooms.pop(cid, None)

    async def broadcast(self, cid: str, payload: dict, exclude=None):
        conns = [w for w in self.rooms.get(cid, set()) if w is not exclude]
        dead = []
        for ws in conns:
            try:
                await ws.send_text(json.dumps(payload))
            except Exception:
                dead.append(ws)
        for ws in dead:
            await self.disconnect(cid, ws)


manager = ConnectionManager()


async def notify(cid: str, payload: dict):
    try:
        await manager.broadcast(cid, payload)
    except Exception:
        pass
