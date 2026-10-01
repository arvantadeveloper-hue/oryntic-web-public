import asyncio
from typing import Optional

import jwt
from fastapi import APIRouter, HTTPException, Header, Query
from fastapi.responses import Response

from auth import JWT_SECRET, JWT_ISSUER
from db import db
from storage import get_object

router = APIRouter(prefix="/api/files", tags=["files"])


def _verify(token: str) -> str:
    try:
        p = jwt.decode(token, JWT_SECRET, algorithms=["HS256"], issuer=JWT_ISSUER,
                       options={"require": ["sub", "exp", "iat", "iss"]})
    except jwt.InvalidTokenError:
        raise HTTPException(401, "Invalid or expired token")
    return p["sub"]


@router.get("/{path:path}")
async def serve_file(path: str, authorization: Optional[str] = Header(None), auth: Optional[str] = Query(None)):
    token = None
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1]
    elif auth:
        token = auth
    if not token:
        raise HTTPException(401, "Not authenticated")
    uid = _verify(token)
    # Files are namespaced by user id: aivora/videos/{user_id}/...
    parts = path.split("/")
    if len(parts) < 3 or parts[2] != uid:
        raise HTTPException(403, "Forbidden")
    try:
        data, content_type = await asyncio.to_thread(get_object, path)
    except Exception:
        raise HTTPException(404, "File not found")
    return Response(content=data, media_type=content_type)
