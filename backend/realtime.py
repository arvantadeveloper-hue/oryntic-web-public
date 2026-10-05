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


class UserManager:
    """One channel per signed-in user (any tab): in-app realtime events (reminder_due, incoming_call, task_update, message_new) replace polling."""

    def __init__(self):
        self.users: Dict[str, Set[WebSocket]] = {}

    async def connect(self, uid: str, ws: WebSocket):
        await ws.accept()
        self.users.setdefault(uid, set()).add(ws)

    def disconnect(self, uid: str, ws: WebSocket):
        conns = self.users.get(uid)
        if conns:
            conns.discard(ws)
            if not conns:
                self.users.pop(uid, None)

    def online(self, uid: str) -> bool:
        return bool(self.users.get(uid))

    async def send(self, uid: str, payload: dict):
        text = json.dumps(payload)
        for ws in list(self.users.get(uid, set())):
            try:
                await ws.send_text(text)
            except Exception:
                self.disconnect(uid, ws)


user_manager = UserManager()


async def notify_user(uid: str, payload: dict):
    try:
        await user_manager.send(uid, payload)
    except Exception:
        pass


async def notify_users(uids, payload: dict):
    for uid in set(u for u in uids if u):
        await notify_user(uid, payload)


async def notify(cid: str, payload: dict):
    try:
        await manager.broadcast(cid, payload)
    except Exception:
        pass
