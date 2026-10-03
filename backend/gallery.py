import re
from typing import Optional

from fastapi import APIRouter, Depends, Query

from auth import current_user, workspace_id
from db import db
from workspace import task_access

router = APIRouter(prefix="/api/gallery", tags=["gallery"])
MEDIA_KINDS = ("image", "video")


def _ext(path: str) -> str:
    return (path or "").rsplit(".", 1)[-1].lower() if "." in (path or "") else ""


async def _media_items(u: dict, kinds: tuple, before: Optional[str], limit: int, q_text: str = "") -> list:
    conv_ids = [c["id"] async for c in db.conversations.find({"$or": [{"workspace_id": workspace_id(u)}, {"user_id": u["id"]}]}, {"_id": 0, "id": 1})]
    q = {"conversation_id": {"$in": conv_ids}, "media": {"$elemMatch": {"type": {"$in": list(kinds)}, "path": {"$exists": True}}}}
    if q_text:
        rx = {"$regex": re.escape(q_text), "$options": "i"}
        q["$or"] = [{"media.name": rx}, {"content": rx}]
    if before:
        q["created_at"] = {"$lt": before}
    out = []
    async for m in db.messages.find(q, {"_id": 0, "id": 1, "media": 1, "conversation_id": 1, "task_id": 1, "persona_name": 1, "created_at": 1}).sort("created_at", -1).limit(limit):
        for x in m.get("media") or []:
            if x.get("type") in kinds and x.get("path"):
                out.append({"id": f"{m['id']}:{x['path']}", "kind": x["type"], "name": x.get("name") or x["path"].rsplit("/", 1)[-1], "format": x.get("format") or _ext(x["path"]),
                            "path": x["path"], "conversation_id": m["conversation_id"], "task_id": m.get("task_id"), "persona_name": m.get("persona_name"), "created_at": m["created_at"]})
    return out


async def _document_items(u: dict, before: Optional[str], limit: int, with_video: bool, q_text: str = "") -> list:
    q = {**task_access(u), "status": "completed", "parent_id": {"$exists": False}}
    if q_text:
        rx = {"$regex": re.escape(q_text), "$options": "i"}
        q["$or"] = [{"goal": rx}, {"final_output": rx}]
    if before:
        q["created_at"] = {"$lt": before}
    out = []
    async for t in db.tasks.find(q, {"_id": 0, "id": 1, "goal": 1, "type": 1, "persona_name": 1, "version": 1, "created_at": 1, "video_path": 1, "final_output": 1, "team": 1}).sort("created_at", -1).limit(limit):
        if (t.get("final_output") or "").strip():
            out.append({"id": t["id"], "kind": "document", "name": t.get("goal") or "Dokumen", "format": "docx", "task_id": t["id"], "type": t.get("type"), "team": bool(t.get("team")),
                        "persona_name": t.get("persona_name"), "version": t.get("version") or 1, "created_at": t["created_at"], "link": f"/workspace/{t['id']}"})
        if with_video and t.get("video_path"):
            out.append({"id": f"{t['id']}:video", "kind": "video", "name": f"{t.get('goal') or 'Video'}.mp4", "format": "mp4", "path": t["video_path"], "task_id": t["id"],
                        "persona_name": t.get("persona_name"), "created_at": t["created_at"]})
    return out


@router.get("")
async def list_gallery(type: str = Query("all", pattern="^(all|image|video|document)$"), before: Optional[str] = None, q: Optional[str] = Query(None, max_length=120), limit: int = Query(24, ge=1, le=60), u: dict = Depends(current_user)):
    """Everything the assistants produced, newest first. Cursor = `before` (created_at of the last item). `q` searches titles and document contents."""
    items = []
    q_text = (q or "").strip()
    if type in ("all", "image", "video"):
        items += await _media_items(u, MEDIA_KINDS if type == "all" else (type,), before, limit + 1, q_text)
    if type in ("all", "document", "video"):
        items += await _document_items(u, before, limit + 1, with_video=type in ("all", "video"), q_text=q_text)
        if type == "video":
            items = [i for i in items if i["kind"] == "video"]
    items.sort(key=lambda i: i["created_at"], reverse=True)
    has_more = len(items) > limit
    items = items[:limit]
    return {"items": items, "has_more": has_more, "next_before": items[-1]["created_at"] if items and has_more else None}
