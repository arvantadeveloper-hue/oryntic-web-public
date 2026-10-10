"""Shared helpers for the platform back-office API (/api/platform/*)."""
from typing import Optional
from db import db, now_iso, new_id

ROLE_LABELS = {"super_admin": "Super Admin", "finance": "Finance"}


async def _audit(actor: dict, action: str, target: Optional[str] = None, meta: Optional[dict] = None) -> None:
    await db.platform_audit.insert_one({"id": new_id(), "actor_id": actor["id"], "actor_email": actor["email"], "action": action,
                                        "target": target, "meta": meta or {}, "created_at": now_iso()})


def _diff_summary(old: dict, new: dict) -> dict:
    """Compact who-changed-what for the audit log: scalar fields as [old, new], nested groups flagged 'diubah'."""
    changed = {}
    for k, nv in new.items():
        ov = old.get(k)
        if ov == nv:
            continue
        changed[k] = [ov, nv] if isinstance(nv, (int, float, str, bool)) or nv is None else "diubah"
    return changed
