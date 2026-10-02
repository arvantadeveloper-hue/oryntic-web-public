import asyncio
from typing import Optional

import jwt
from fastapi import APIRouter, HTTPException, Header, Query
from fastapi.responses import Response

from auth import JWT_SECRET, JWT_ISSUER
from storage import get_object
from db import db

router = APIRouter(prefix="/api/files", tags=["files"])


async def _same_workspace(uid: str, owner_uid: str) -> bool:
    users = await db.users.find({"id": {"$in": [uid, owner_uid]}}, {"_id": 0, "id": 1, "owner_id": 1}).to_list(2)
    ws = {x["id"]: (x.get("owner_id") or x["id"]) for x in users}
    return len(ws) == 2 and ws[uid] == ws[owner_uid]


def _verify(token: str) -> str:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"], issuer=JWT_ISSUER,
                             options={"require": ["sub", "exp", "iat", "iss"]})
        return payload["sub"]
    except jwt.InvalidTokenError as exc:
        raise HTTPException(401, "Invalid or expired token") from exc


def _bearer(authorization: Optional[str], auth: Optional[str]) -> str:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization.split(" ", 1)[1]
    if auth:
        return auth
    raise HTTPException(401, "Not authenticated")


def _path_parts(path: str) -> list:
    """Files are namespaced by owner user id: aivora/{kind}/{user_id}/..."""
    parts = path.split("/")
    if any(seg in ("", ".", "..") for seg in parts) or "\\" in path or len(parts) < 4 or parts[0] != "aivora":
        raise HTTPException(403, "Forbidden")
    return parts


@router.get("/{path:path}")
async def serve_file(path: str, authorization: Optional[str] = Header(None), auth: Optional[str] = Query(None)):
    uid = _verify(_bearer(authorization, auth))
    parts = _path_parts(path)
    if parts[2] != uid and not await _same_workspace(uid, parts[2]):
        raise HTTPException(403, "Forbidden")
    try:
        data, content_type = await asyncio.to_thread(get_object, path)
    except Exception as exc:
        raise HTTPException(404, "File not found") from exc
    return Response(content=data, media_type=content_type)
