import logging
import math
import os
import json
import re
import httpx
from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field, field_validator

from db import db, now_iso, new_id
from auth import current_user, require_platform_admin, workspace_id
from llm import record_usage, quota_exceeded, quota_message
from chat import _can_access, _persona_system, _history_text
from realtime import notify
from ratelimit import rate_limit, get_limits, set_limits
from pricing import usd_to_credits, realtime_usage_usd, get_pricing as platform_pricing, set_pricing as platform_set_pricing, compute_rates, REALTIME_MODELS, DEFAULT_REALTIME_MODEL, realtime_credits_per_min, realtime_model_prices
from tools import get_routing, TASK_CONTEXT
from behaviour import get_behaviour, turn_detection
from llm import MODEL_CATALOG, model_label

router = APIRouter(prefix="/api", tags=["realtime-voice"])

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
REALTIME_MODEL = os.environ.get("OPENAI_REALTIME_MODEL", "gpt-realtime")  # fallback only; each persona chooses its voice_model
# Session instructions are always Oryntix's own (assistant_persona.py) — dashboard-stored prompts are not used.

# TTS voice (persona.voice) -> Realtime voice
VOICE_MAP = {"alloy": "alloy", "echo": "echo", "shimmer": "shimmer", "nova": "coral", "onyx": "ash", "fable": "ballad",
             "ash": "ash", "coral": "coral", "sage": "sage", "verse": "verse", "marin": "marin", "cedar": "cedar", "ballad": "ballad"}
MODERATOR_OPENING = ("You are the Moderator of this meeting with participants {roster} (topic: {title}). The user opens the conversation — "
                     "do NOT greet or introduce the meeting on your own; wait for the user to speak, then answer or route the question to the right "
                     "participant. Hand the floor to another assistant only when their role fits better.")
SPEAKING_STYLE = ("CALL CONTEXT: this is a live phone-style call. The user's name is known to you; address them naturally, not in every sentence. "
                  "Keep greetings to one short sentence. Everything else about HOW you talk is defined by the conversation style above.")
NO_REPEAT = ("Listen to what the other participants already said. NEVER repeat or paraphrase a point someone else has made; "
             "if you agree, say so in a few words and ADD something new (a different angle, risk, example, or decision). "
             "If you have nothing new, say briefly that you have nothing to add.")

async def get_pricing() -> dict:
    return await platform_pricing()


def credits_per_min(p: dict) -> int:
    return compute_rates(p)["realtime_per_min"]


def enabled() -> bool:
    return bool(OPENAI_API_KEY)


@router.get("/realtime/status")
async def status(u: dict = Depends(current_user)):
    p = await get_pricing()
    return {"enabled": enabled(), "model": DEFAULT_REALTIME_MODEL, "credits_per_min": realtime_credits_per_min(p, DEFAULT_REALTIME_MODEL), "prompt_id": None, "prompt_version": None,
            "models": [{"id": k, **{kk: v[kk] for kk in ("label", "tagline")}, "credits_per_min": realtime_credits_per_min(p, k), "default": k == DEFAULT_REALTIME_MODEL} for k, v in REALTIME_MODELS.items()]}


class PricingIn(BaseModel):
    provider_usd_per_min: float = Field(gt=0)
    margin_pct: float = Field(ge=0, le=500)
    tax_pct: float = Field(ge=0, le=100)
    usd_to_idr: float = Field(gt=0)
    idr_per_credit: float = Field(gt=0)


@router.get("/admin/realtime-pricing")
async def admin_pricing(_: dict = Depends(require_platform_admin)):
    p = await get_pricing()
    return {**p, "credits_per_min": credits_per_min(p), "model": REALTIME_MODEL, "enabled": enabled()}


@router.put("/admin/realtime-pricing")
async def admin_set_pricing(x: PricingIn, _: dict = Depends(require_platform_admin)):
    doc = await platform_set_pricing(x.model_dump())
    return {**doc, "credits_per_min": credits_per_min(doc)}


class LimitsIn(BaseModel):
    chat_per_min: int = Field(ge=1, le=1000)
    chat_per_hour: int = Field(default=300, ge=1, le=100_000)
    chat_min_interval_ms: int = Field(default=1500, ge=0, le=60_000)
    chat_max_inflight: int = Field(default=4, ge=1, le=50)
    chat_dup_per_30s: int = Field(default=3, ge=1, le=100)
    voice_per_min: int = Field(ge=1, le=1000)
    calls_per_hour: int = Field(ge=1, le=1000)
    max_call_minutes: int = Field(ge=1, le=600)
    generation_per_hour: int = Field(ge=1, le=1000)
    storage_quota_mb: int = Field(default=50, ge=1, le=100_000)


@router.get("/admin/rate-limits")
async def admin_limits(_: dict = Depends(require_platform_admin)):
    return await get_limits()


@router.put("/admin/rate-limits")
async def admin_set_limits(x: LimitsIn, _: dict = Depends(require_platform_admin)):
    return await set_limits(x.model_dump())


MODERATOR_STYLE = ("You are the MODERATOR of a LIVE SPOKEN MEETING between the user and these AI assistants:\n{panel}\n"
                   "You are the one who talks with the user: listen, answer directly and naturally, and keep the meeting moving. "
                   "The other assistants speak ONLY when the user asks them by name or when you hand them the floor. Hand over "
                   "(call the `delegate` tool) ONLY when the topic clearly matches another assistant's specialty — e.g. IT/coding "
                   "questions go to the IT expert. When you delegate: say ONE short handover sentence (e.g. \"Let me ask {{name}} to "
                   "explain this\"), then call the tool; never answer on their behalf. After they finish, their words come back as the "
                   "tool result: complement or agree in 1-2 short sentences, then hand back to the user. What the other assistants "
                   "say otherwise arrives as text prefixed with their name in brackets. Keep each turn to 1-4 short spoken sentences.")
PANELIST_STYLE = ("You are a PARTICIPANT in a LIVE SPOKEN MEETING with the user, the moderator {moderator} and other assistants: {others}. "
                  "You do NOT hear audio: everything the user and the others say reaches you as text prefixed with the speaker's name in "
                  "brackets. Speak ONLY when a response is requested from you (the moderator handed you the floor or the user asked you by "
                  "name). Answer the actual question in 2-5 short spoken sentences, no greetings, do not repeat what others said, "
                  "never speak for the others, and end by handing back to the moderator or the user.")
PROVIDER_HINT = {"anthropic": "IT, coding, writing & deep analysis", "gemini": "research, multimodal & long documents", "openai": "general, creative & everyday tasks"}


def delegate_tool(names: list) -> dict:
    return {"type": "function", "name": "delegate",
            "description": "Hand the floor to another assistant whose specialty matches the user's current question. Say one short handover sentence before calling.",
            "parameters": {"type": "object", "properties": {
                "assistant": {"type": "string", "enum": names, "description": "Name of the assistant who should answer"},
                "brief": {"type": "string", "description": "One sentence: what the user wants them to explain"}},
                "required": ["assistant", "brief"]}}


ASSIGN_TOOL = {"type": "function", "name": "assign_task",
               "description": "Record a piece of work the user delegates to you (a deliverable such as a document, plan, analysis or research) into the Workspace, to be done now or at a given time. Use when the user asks you to prepare something substantial rather than answer right away. Confirm verbally after the result.",
               "parameters": {"type": "object", "properties": {
                   "title": {"type": "string", "description": "Short title of the task (Indonesian, max 10 words)"},
                   "brief": {"type": "string", "description": "What exactly must be produced, 1-3 sentences"},
                   "scheduled_at": {"type": "string", "description": "ISO-8601 datetime with timezone offset if the user named a time (e.g. 'besok jam 9'), else omit"},
                   "team": {"type": "boolean", "description": "true when the user wants the work split among the other assistants (delegate sub-tasks); offer this for big tasks when there are several assistants"},
                   "assignments": {"type": "array", "description": "Only when the user explicitly names who handles which part (e.g. 'bagian keuangan minta Nova'): one entry per named part", "items": {"type": "object", "properties": {
                       "assistant": {"type": "string", "description": "Exact assistant name as the user said it"},
                       "part": {"type": "string", "description": "Which part of the task they should handle"}}, "required": ["assistant", "part"]}},
                   "model": {"type": "string", "description": "Model id the user CONFIRMED for this task after you asked (see MODEL CONFIRMATION in your instructions). Omit when the user wants your own model."}},
                   "required": ["title", "brief"]}}
ARCHIVE_SEARCH_TOOL = {"type": "function", "name": "search_archive",
                       "description": "Search the user's archived (old, summarized) conversations by keywords. Use when the user asks about an old chat or wants to find/restore an archive. Results are posted to the chat panel; read the titles back briefly.",
                       "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}
ARCHIVE_RESTORE_TOOL = {"type": "function", "name": "restore_archive",
                        "description": "Restore an archived conversation (from search_archive results) back into this chat. You MUST first ask the user to confirm (name the archive title) and only call this with confirmed=true after the user clearly agrees.",
                        "parameters": {"type": "object", "properties": {"archive_id": {"type": "string"}, "confirmed": {"type": "boolean", "description": "true only after the user explicitly confirmed"}}, "required": ["archive_id", "confirmed"]}}
WEB_SEARCH_TOOL = {"type": "function", "name": "web_search",
                   "description": "Search the LIVE web for current facts (news, prices, rates, scores, who/what/when questions about recent events, anything you are unsure is up to date). "
                                  "Returns a short answer plus sources. Then answer the user in 1-3 spoken sentences and SAY the source name aloud (e.g. 'menurut Kompas'); the clickable links are posted to the chat panel automatically. Never claim you cannot access the internet.",
                   "parameters": {"type": "object", "properties": {"query": {"type": "string", "description": "What to search for, in the user's words"}}, "required": ["query"]}}
RUN_CODE_TOOL = {"type": "function", "name": "run_code",
                 "description": "Run Python to compute something precisely: arithmetic, percentages, loan/installment math, unit or currency conversion, statistics over numbers the user gives, date differences, etc. "
                                "Use it instead of estimating whenever a number must be exact. Returns the computed result in plain words; read it back naturally (round long decimals when speaking) and mention briefly that you calculated it. Never say you cannot run code.",
                 "parameters": {"type": "object", "properties": {"task": {"type": "string", "description": "The calculation to perform, with all numbers and assumptions, in the user's words"}}, "required": ["task"]}}
CALENDAR_TOOL = {"type": "function", "name": "add_calendar_event",
                 "description": "Record an activity, meeting, appointment, deadline or reminder the user mentions into their calendar. Use whenever the user asks you to note/schedule/remind them about something at a time. "
                                "If the date or time is missing, ASK first. Confirm verbally afterwards (title, when, how they will be reminded).",
                 "parameters": {"type": "object", "properties": {
                     "title": {"type": "string", "description": "Short Indonesian title (max 8 words)"},
                     "start_at": {"type": "string", "description": "ISO-8601 datetime WITH timezone offset, resolved from the user's words (e.g. 'besok jam 10' → tomorrow 10:00 +07:00)"},
                     "notes": {"type": "string", "description": "Place, people, agenda or other details; empty if none"},
                     "remind_mode": {"type": "string", "enum": ["call", "chat", "none"], "description": "How to remind: call = the assistant phones them, chat = sends a chat message, none = no reminder. Default 'call' when unspecified"},
                     "remind_offsets": {"type": "array", "items": {"type": "integer"}, "description": "Minutes before start to remind, e.g. [30] or [30, 60] when the user asks for 30 minutes AND 1 hour. Default [30]"}},
                     "required": ["title", "start_at"]}}
SEARCH_TOOL = {"type": "function", "name": "search_workspace",
               "description": "Search the user's Workspace (saved task results, documents, meeting minutes) by keywords and drop clickable links into the chat panel. Use when the user asks to find or look up existing material.",
               "parameters": {"type": "object", "properties": {"query": {"type": "string", "description": "Keywords to search for"}}, "required": ["query"]}}
DRIVE_TOOLS = [
    {"type": "function", "name": "drive_save", "description": "Save content to the user's Google Drive as a Google Doc (or Sheet for tables). Use when the user asks to save/store a document, result or table to Drive.",
     "parameters": {"type": "object", "properties": {"title": {"type": "string"}, "content": {"type": "string", "description": "markdown content to save; omit to save the task under discussion"}, "kind": {"type": "string", "enum": ["doc", "sheet"]}}, "required": ["title"]}},
    {"type": "function", "name": "drive_update", "description": "Append or replace text in an existing Google Doc on the user's Drive.",
     "parameters": {"type": "object", "properties": {"file": {"type": "string", "description": "document name"}, "text": {"type": "string"}, "mode": {"type": "string", "enum": ["append", "replace"]}}, "required": ["file", "text"]}},
    {"type": "function", "name": "drive_link", "description": "Get the Google Drive link of a document by name (optionally make it viewable by anyone with the link).",
     "parameters": {"type": "object", "properties": {"file": {"type": "string"}, "share": {"type": "boolean"}}, "required": ["file"]}},
]
GITHUB_TOOLS = [
    {"type": "function", "name": "github_repos", "description": "List the user's GitHub repositories (optionally filtered). Links are posted to the chat panel.",
     "parameters": {"type": "object", "properties": {"query": {"type": "string"}}}},
    {"type": "function", "name": "github_read", "description": "Read a GitHub repo: file tree (path empty), a folder listing, or a file's content. Use before discussing or changing code.",
     "parameters": {"type": "object", "properties": {"repo": {"type": "string", "description": "owner/repo"}, "path": {"type": "string"}}, "required": ["repo"]}},
    {"type": "function", "name": "github_issues", "description": "List issues / pull requests of a GitHub repo.",
     "parameters": {"type": "object", "properties": {"repo": {"type": "string"}, "state": {"type": "string", "enum": ["open", "closed", "all"]}}, "required": ["repo"]}},
    {"type": "function", "name": "github_pr", "description": "Create a branch, commit the given full file contents and open a pull request on the user's GitHub repo. Only after the user explicitly asked for a PR; read the files first and pass complete new contents.",
     "parameters": {"type": "object", "properties": {"repo": {"type": "string"}, "title": {"type": "string"}, "body": {"type": "string", "description": "markdown summary of the changes"},
                                                     "changes": {"type": "array", "items": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}, "delete": {"type": "boolean"}}, "required": ["path"]}}}, "required": ["repo", "title", "changes"]}},
]
GITHUB_TOOLS.append({"type": "function", "name": "github_review", "description": "Fetch a pull request's diff (latest open PR when number omitted) so you can review it: summarize, point out risks and suggest fixes. The full written review is posted to the chat panel.",
                     "parameters": {"type": "object", "properties": {"repo": {"type": "string"}, "number": {"type": "integer"}}, "required": ["repo"]}})
SOCIAL_TOOL = {"type": "function", "name": "social_publish", "description": "Publish the latest image/video of this conversation (or a text-only post) to the user's connected social accounts. Only after the user confirmed the caption and the target networks.",
               "parameters": {"type": "object", "properties": {"providers": {"type": "array", "items": {"type": "string", "enum": ["linkedin", "meta", "youtube"]}}, "caption": {"type": "string"}, "kind": {"type": "string", "enum": ["text", "image", "video"]}}, "required": ["providers", "caption"]}}
GITLAB_TOOLS = [{**t, "name": t["name"].replace("github_", "gitlab_"), "description": t["description"].replace("GitHub", "GitLab").replace("pull request", "merge request")} for t in GITHUB_TOOLS]
IMAGE_TOOL = {"type": "function", "name": "generate_image",
              "description": "Create a picture (photo, photorealistic render, illustration, logo, poster, wallpaper) and show it in the chat panel. Also edits the latest generated image when edit_previous is true (restyle, change background, add/remove something). Call it whenever the user asks for any image — never say you cannot make images.",
              "parameters": {"type": "object", "properties": {"prompt": {"type": "string", "description": "Detailed English prompt for the image model"}, "edit_previous": {"type": "boolean", "description": "true when the user wants the previously generated image changed"}, "request": {"type": "string", "description": "The user's request in their own words"}}, "required": ["prompt"]}}
VIDEO_TOOL = {"type": "function", "name": "generate_video",
              "description": "Offer a short AI video clip (Seedance). Posts a card to the chat panel where the user picks Seedance 2.0 or 2.5 (prices in credits/second come from the platform); rendering starts after they tap. Call it whenever the user asks for a video/clip/animation — never say you cannot make videos. Set from_image when they want the latest generated image animated.",
              "parameters": {"type": "object", "properties": {"prompt": {"type": "string", "description": "Detailed English prompt: scene, motion, camera, mood"}, "duration": {"type": "integer", "description": "Seconds 4-30 (default 5)"}, "aspect_ratio": {"type": "string", "enum": ["16:9", "9:16", "1:1", "21:9"], "description": "9:16 for Reels/Shorts/portrait, 1:1 square, else 16:9"}, "resolution": {"type": "string", "enum": ["480p", "720p", "1080p"], "description": "480p cheap, 1080p sharp, default 720p"}, "real_person": {"type": "boolean", "description": "real-person mode (only with from_image)"}, "with_audio": {"type": "boolean", "description": "generate sound/ambience with the clip"}, "from_image": {"type": "boolean"}, "request": {"type": "string", "description": "The user's request in their own words"}}, "required": ["prompt"]}}
UPDATE_TOOL = {"type": "function", "name": "update_task",
               "description": "Apply a revision the user asked for to the Workspace result currently being presented/discussed. Pass the full revision instruction. The result is saved as a new version.",
               "parameters": {"type": "object", "properties": {"instruction": {"type": "string", "description": "What to change, in detail"}}, "required": ["instruction"]}}
PRESENT_STYLE = ("\n\nYOU ARE PRESENTING the Workspace result above as if sharing your screen: open by presenting it section by section in short spoken "
                 "chunks (2-4 sentences each), pausing to invite questions. When the user asks for changes, call the `update_task` tool with a precise "
                 "instruction, then confirm what changed.")


def _specialty(p: dict, routing: dict) -> str:
    m = next((x for x in MODEL_CATALOG if x["id"] == p.get("model")), MODEL_CATALOG[0])
    hints = []
    if p.get("model") == routing.get("it_model"):
        hints.append("THE IT/CODING EXPERT")
    if p.get("model") == routing.get("research_model"):
        hints.append("THE RESEARCH EXPERT")
    hints.append(PROVIDER_HINT.get(m["provider"], ""))
    desc = ((p.get("profile") or {}).get("system_instructions") or "").strip().replace("\n", " ")[:160]
    return f"- {p['name']} — model {m['label']} ({'; '.join(h for h in hints if h)}). Profile: {desc}"


async def _voice_context(cid: str) -> str:
    """Compact context for the voice session: task under discussion + short memory summary + last 6 messages (keeps cached prefix small)."""
    conv = await db.conversations.find_one({"id": cid}, {"_id": 0, "memory_summary": 1, "task_id": 1}) or {}
    parts = []
    if conv.get("task_id"):
        t = await db.tasks.find_one({"id": conv["task_id"]}, {"_id": 0, "goal": 1, "status": 1, "version": 1, "final_output": 1}) or {}
        if t:
            parts.append(TASK_CONTEXT.format(tid=conv["task_id"], ver=t.get("version") or 1, status=t.get("status"), goal=t.get("goal"), body=(t.get("final_output") or "(belum ada hasil)")[:5000]) + PRESENT_STYLE)
    if conv.get("memory_summary"):
        parts.append(f"[Summary of earlier conversation]: {conv['memory_summary'][:600]}")
    recent = (await _history_text(cid, limit=6, with_summary=False)).strip()
    if recent:
        parts.append(recent[-1000:])
    return "\n".join(parts)


class CallIn(BaseModel):
    conversation_id: str
    opening: Optional[str] = Field(default=None, max_length=1500)  # e.g. reminder the assistant must deliver first
    call_session_id: Optional[str] = Field(default=None, max_length=64)  # friend-call session (from /call/presence) for the cost report


async def _call_personas(conv: dict, u: dict) -> list:
    pids = conv.get("persona_ids") or ([conv["persona_id"]] if conv.get("persona_id") else [])
    personas = [p async for p in db.personas.find({"id": {"$in": pids}, "user_id": workspace_id(u), "deleted": {"$ne": True}}, {"_id": 0})]
    personas.sort(key=lambda p: pids.index(p["id"]))
    if not personas:
        raise HTTPException(400, "Percakapan ini tidak memiliki persona")
    return personas


async def _ensure_affordable(u: dict, n_sessions: int, cpm: int):
    over = await quota_exceeded(u)
    if over:
        raise HTTPException(402, quota_message(over))
    owner = await db.users.find_one({"id": workspace_id(u)}, {"_id": 0, "credits": 1}) or {}
    if (owner.get("credits") or 0) < cpm * n_sessions:
        raise HTTPException(402, "Kredit workspace tidak cukup untuk memulai panggilan")


async def _close_stale_calls(user_id: str):
    """Calls left open by a dropped tab (>2 min old); no extra charge beyond what ticks already billed."""
    stale_before = (datetime.now(timezone.utc) - timedelta(minutes=2)).isoformat()
    await db.realtime_calls.update_many({"user_id": user_id, "status": {"$in": ["created", "active"]}, "created_at": {"$lt": stale_before}},
                                        {"$set": {"status": "ended", "ended_at": now_iso(), "stale": True}})


async def _session_instructions(persona: dict, u: dict, roster: list, history: str, opening, role: str, title: str = "", panel: str = "") -> str:
    """Static persona/style first (cacheable prefix), per-call context last."""
    text = await _persona_system(persona, u, None, voice_mode=True) + "\n\n" + SPEAKING_STYLE
    rt = await get_routing()
    text += (f"\n\nMODEL CONFIRMATION: your own model is '{model_label(persona.get('model'))}' (id {persona.get('model')}). Before you call assign_task for coding/IT work "
             f"(recommended: {model_label(rt['it_model'])}, id {rt['it_model']}) or heavy research (recommended: {model_label(rt['research_model'])}, id {rt['research_model']}), "
             "ASK the user in one short sentence whether to use the recommended model or your own, WAIT for the answer, then call assign_task with `model` set to the confirmed id "
             "(omit it for your own model). Never switch models without asking. This does NOT apply to images or videos — keep using generate_image/generate_video as before.")
    text += ("\n\nMEDIA TOOLS: use generate_image for any picture request and generate_video for any video/clip request — they appear in the chat panel next to the call. "
             "Say briefly that you are making it (or, for video, that the model picker is in the chat panel); never claim you cannot create images or videos.")
    uname = u.get("name") or "the user"
    if role == "moderator":
        text += "\n\n" + MODERATOR_STYLE.format(panel=panel) + "\n" + NO_REPEAT
    elif role == "panelist":
        others = [n for n in roster if n not in (persona["name"], roster[0])]
        text += "\n\n" + PANELIST_STYLE.format(moderator=roster[0], others=", ".join(others) or "none") + "\n" + NO_REPEAT
    if history.strip():
        text += f"\n\nRecent conversation with the user (for context):\n{history}"
    if role == "solo" and opening:
        text += (f"\n\nYOU ARE CALLING THE USER. Open the call immediately by delivering this reminder warmly in 2-3 short "
                 f"spoken sentences, greeting {uname} by name, then ask if they need anything: {opening}")
    elif role == "moderator":
        text += "\n\n" + MODERATOR_OPENING.format(uname=uname, roster=", ".join(roster), title=title or "meeting")
    elif role == "solo":
        text += f"\n\n{uname} opens the conversation. Do NOT greet or speak first — wait for them, then respond to what they actually say."
    return text


def _order_personas(personas: list, conv: dict) -> list:
    mod_id = conv.get("moderator_persona_id")
    idx = next((i for i, p in enumerate(personas) if p["id"] == mod_id), 0)
    return [personas[idx]] + [p for i, p in enumerate(personas) if i != idx]


@router.post("/realtime/calls")
async def create_call(x: CallIn, u: dict = Depends(current_user)):
    if not enabled():
        raise HTTPException(503, "Mode Realtime belum diaktifkan (OPENAI_API_KEY belum diatur)")
    conv = await db.conversations.find_one({"id": x.conversation_id}, {"_id": 0})
    if not _can_access(conv, u):
        raise HTTPException(404, "Conversation not found")
    await rate_limit(u, "calls")
    personas = _order_personas(await _call_personas(conv, u), conv)
    p = await get_pricing()
    await _ensure_affordable(u, len(personas), max(realtime_credits_per_min(p, pp.get("voice_model")) for pp in personas))
    await _close_stale_calls(u["id"])

    history = await _voice_context(conv["id"])
    roster = [q["name"] for q in personas]
    multi = len(personas) > 1
    routing = await get_routing()
    panel = "\n".join(_specialty(p, routing) for p in personas[1:]) if multi else ""
    group_id = new_id()
    sessions = []
    for i, persona in enumerate(personas):
        role = "solo" if not multi else ("moderator" if i == 0 else "panelist")
        vm = persona.get("voice_model") if persona.get("voice_model") in REALTIME_MODELS else DEFAULT_REALTIME_MODEL
        cpm = realtime_credits_per_min(p, vm)
        call = {"id": new_id(), "group_id": group_id, "conversation_id": conv["id"], "user_id": u["id"], "persona_id": persona["id"], "model": vm,
                "persona_name": persona["name"], "call_session_id": x.call_session_id or group_id,
                "voice": VOICE_MAP.get(persona.get("voice", "alloy"), "marin"), "role": role, "roster": roster,
                "instructions": await _session_instructions(persona, u, roster, history, x.opening, role, conv.get("title", ""), panel),
                "multi": multi, "primary": i == 0, "status": "created", "billed_minutes": 0, "credits": 0, "credits_per_min": cpm,
                "created_at": now_iso(), "started_at": None, "ended_at": None, "seconds": 0}
        await db.realtime_calls.insert_one(dict(call))
        sessions.append({"call_id": call["id"], "voice": call["voice"], "primary": i == 0, "role": role, "model": vm, "credits_per_min": cpm,
                         "persona": {"id": persona["id"], "name": persona["name"], "portrait": persona.get("portrait")}})
    first = sessions[0]
    return {"call_id": first["call_id"], "voice": first["voice"], "persona": first["persona"], "model": first["model"],
            "credits_per_min": first["credits_per_min"], "credits_per_min_total": sum(s_["credits_per_min"] for s_ in sessions), "multi": multi, "group_id": group_id,
            "moderator_persona_id": personas[0]["id"],
            "sessions": sessions, "language": ((u.get("settings") or {}).get("conversation_language") or "id")}


class ModeratorIn(BaseModel):
    persona_id: str


@router.patch("/conversations/{cid}/moderator")
async def set_moderator(cid: str, x: ModeratorIn, u: dict = Depends(current_user)):
    conv = await db.conversations.find_one({"id": cid}, {"_id": 0})
    if not _can_access(conv, u):
        raise HTTPException(404, "Conversation not found")
    if x.persona_id not in (conv.get("persona_ids") or []):
        raise HTTPException(400, "Persona bukan peserta panggilan ini")
    await db.conversations.update_one({"id": cid}, {"$set": {"moderator_persona_id": x.persona_id, "updated_at": now_iso()}})
    return {"ok": True, "moderator_persona_id": x.persona_id}


async def _own_call(call_id: str, u: dict) -> dict:
    call = await db.realtime_calls.find_one({"id": call_id, "user_id": u["id"]}, {"_id": 0})
    if not call:
        raise HTTPException(404, "Call not found")
    return call


async def vad_config(sensitivity: str, multi: bool) -> dict:
    """Turn-taking from the platform-wide Conversation Behaviour config (back-office); default semantic_vad + eagerness=low."""
    return turn_detection(await get_behaviour(), multi)


@router.get("/realtime/behaviour")
async def realtime_behaviour(_: dict = Depends(current_user)):
    return await get_behaviour()


@router.post("/realtime/calls/{call_id}/negotiate", response_class=PlainTextResponse)
async def negotiate(call_id: str, request: Request, u: dict = Depends(current_user)):
    call = await _own_call(call_id, u)
    if call["status"] == "ended":
        raise HTTPException(400, "Call already ended")
    sdp_offer = (await request.body()).decode()
    settings = u.get("settings") or {}
    lang = settings.get("conversation_language") or "id"
    multi = bool(call.get("multi"))
    role = call.get("role") or ("moderator" if multi and call.get("primary") else "panelist" if multi else "solo")
    if role == "panelist":
        audio_in = {"turn_detection": None}  # no mic audio: the user's words arrive as text (saves audio input tokens)
    else:
        audio_in = {"turn_detection": await vad_config(request.query_params.get("sensitivity") or settings.get("mic_sensitivity"), multi),
                    "transcription": {"model": "gpt-4o-mini-transcribe", "language": lang}}
    session = {
        "type": "realtime",
        "model": call.get("model") or DEFAULT_REALTIME_MODEL,
        "output_modalities": ["audio"],
        "audio": {"input": audio_in, "output": {"voice": call["voice"]}},
        "instructions": call["instructions"],
    }
    if role in ("moderator", "solo"):
        conv = await db.conversations.find_one({"id": call["conversation_id"]}, {"_id": 0, "task_id": 1}) or {}
        drive_on = bool(await db.drive_credentials.find_one({"user_id": u["id"]}, {"_id": 1}))
        gh_on = bool(await db.github_credentials.find_one({"user_id": u["id"]}, {"_id": 1}))
        gl_on = bool(await db.gitlab_credentials.find_one({"user_id": u["id"]}, {"_id": 1}))
        social_on = bool(await db.social_accounts.find_one({"user_id": u["id"]}, {"_id": 1}))
        from provider_tools import web_search_tool, code_tool
        call_persona = await db.personas.find_one({"id": call["persona_id"]}, {"_id": 0, "model": 1, "tools": 1}) or {}
        web_on, code_on = bool(web_search_tool(call_persona)), bool(code_tool(call_persona))
        tools = [ASSIGN_TOOL, SEARCH_TOOL, CALENDAR_TOOL, ARCHIVE_SEARCH_TOOL, ARCHIVE_RESTORE_TOOL, IMAGE_TOOL, VIDEO_TOOL] + ([WEB_SEARCH_TOOL] if web_on else []) + ([RUN_CODE_TOOL] if code_on else []) + (DRIVE_TOOLS if drive_on else []) + (GITHUB_TOOLS if gh_on else []) + (GITLAB_TOOLS if gl_on else []) + ([SOCIAL_TOOL] if social_on else []) + ([UPDATE_TOOL] if conv.get("task_id") else []) + ([delegate_tool([n for n in call.get("roster", [])[1:]])] if role == "moderator" else [])
        session["tools"] = tools
        session["tool_choice"] = "auto"
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post("https://api.openai.com/v1/realtime/calls",
                              headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
                              files={"sdp": (None, sdp_offer), "session": (None, json.dumps(session))})
    if r.status_code >= 300:
        logging.getLogger("realtime").error("Realtime negotiate failed %s: %s", r.status_code, r.text[:500])
        raise HTTPException(502, "Negosiasi Realtime gagal, coba lagi")
    await db.realtime_calls.update_one({"id": call_id}, {"$set": {"status": "active", "started_at": now_iso(),
                                                                  "openai_call_id": r.headers.get("Location", "").rsplit("/", 1)[-1]}})
    return PlainTextResponse(r.text, media_type="application/sdp")


class TranscriptIn(BaseModel):
    role: str = Field(pattern="^(user|assistant)$")
    content: str = Field(min_length=1, max_length=8000)
    via: str = Field(default="realtime", pattern="^(realtime|meeting_chat)$")  # meeting_chat = text card (links, tool results) posted into the call chat panel


@router.post("/realtime/calls/{call_id}/transcript")
async def transcript(call_id: str, x: TranscriptIn, u: dict = Depends(current_user)):
    call = await _own_call(call_id, u)
    cid = call["conversation_id"]
    if x.role == "user":
        msg = {"id": new_id(), "conversation_id": cid, "role": "user", "content": x.content, "attachments": [],
               "sender_user_id": u["id"], "sender_name": u.get("name") or "User", "via": x.via, "created_at": now_iso()}
    else:
        persona = await db.personas.find_one({"id": call["persona_id"]}, {"_id": 0}) or {}
        msg = {"id": new_id(), "conversation_id": cid, "role": "assistant", "content": x.content,
               "persona_id": call["persona_id"], "persona_name": persona.get("name") or "Asisten",
               "portrait": persona.get("portrait"), "credits": 0, "via": x.via, "created_at": now_iso()}
    await db.messages.insert_one(dict(msg))
    await db.conversations.update_one({"id": cid}, {"$set": {"updated_at": now_iso(), "last_message": x.content[:120]}})
    await notify(cid, {"type": "message", "role": x.role})
    return {"ok": True, "message_id": msg["id"]}


class WebSearchIn(BaseModel):
    query: str = Field(min_length=2, max_length=400)


class RunCodeIn(BaseModel):
    task: str = Field(min_length=2, max_length=1500)


async def _voice_provider_tool(call_id: str, u: dict, runner, text: str, tool: str, card_title: str, not_enabled: str, failed: str, via: str) -> dict:
    """Shared voice-tool flow: run the persona's provider tool, bill tool + text credits, post a card to the chat panel, return the spoken answer."""
    from auth import _lang_name
    from chat import _save_ai_msg
    from llm import text_credits
    call = await _own_call(call_id, u)
    persona = await db.personas.find_one({"id": call["persona_id"]}, {"_id": 0}) or {}
    over = await quota_exceeded(u)
    if over:
        raise HTTPException(402, quota_message(over))
    try:
        out = await runner(persona, _lang_name(u), text, u["id"])
    except ValueError:
        raise HTTPException(400, not_enabled)
    except Exception as exc:
        logging.getLogger(__name__).warning("voice tool %s failed: %s", tool, str(exc)[:200])
        raise HTTPException(502, failed) from exc
    credits = text_credits(text, out["text"], persona.get("model"))
    for t in out["tools_used"]:
        if t["credits"]:
            await record_usage(u["id"], f"tool:{t['id']}", t["credits"], {"conversation_id": call["conversation_id"], "persona_id": persona.get("id"), "count": t["count"], "via": "realtime"})
    await record_usage(u["id"], "chat", credits, {"conversation_id": call["conversation_id"], "persona_id": persona.get("id"), "model": persona.get("model"), "via": via})
    credits += out["tool_credits"]
    sources = out["citations"]
    spoken = re.sub(r"\s*\(\[[^\]]*\]\([^)]*\)\)", "", out["text"])  # drop inline "([site](url))" so the voice model doesn't read URLs aloud
    spoken = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", spoken).strip()
    md = f"{card_title} «{text}»\n\n{out['text']}"
    await _save_ai_msg(call["conversation_id"], persona, md, credits, "meeting_chat", {"tool": tool, "tools_used": out["tools_used"], "citations": sources, **({"media": out["media"]} if out.get("media") else {}), **({"pending_files": out["pending_files"]} if out.get("pending_files") else {})})
    await notify(call["conversation_id"], {"type": "message", "role": "assistant"})
    return {"answer": spoken, "sources": [{"title": s["title"], "url": s["url"]} for s in sources[:5]], "credits": credits, "files": [f["name"] for f in out.get("pending_files") or []]}


@router.post("/realtime/calls/{call_id}/web-search")
async def call_web_search(call_id: str, x: WebSearchIn, u: dict = Depends(current_user)):
    """Voice tool: live web search via the persona's provider tool; the spoken answer goes back to the model, the sources are posted to the chat panel."""
    from provider_tools import voice_web_search
    return await _voice_provider_tool(call_id, u, voice_web_search, x.query, "web_search", "🔎 **Pencarian web:**",
                                      "Pencarian web tidak diaktifkan untuk asisten ini.", "Pencarian web gagal, coba lagi.", "realtime_web_search")


@router.post("/realtime/calls/{call_id}/run-code")
async def call_run_code(call_id: str, x: RunCodeIn, u: dict = Depends(current_user)):
    """Voice tool: solve a calculation/data task by running Python via the persona's provider code tool; result is spoken + posted to the chat panel."""
    from provider_tools import voice_run_code
    return await _voice_provider_tool(call_id, u, voice_run_code, x.task, "run_code", "🧮 **Perhitungan (Python):**",
                                      "Eksekusi kode tidak diaktifkan untuk asisten ini.", "Perhitungan gagal, coba lagi.", "realtime_run_code")



class TickIn(BaseModel):
    elapsed_seconds: int = Field(ge=0, le=6 * 3600)


class UsageIn(BaseModel):
    usage: dict  # OpenAI `response.done` → response.usage

    @field_validator("usage")
    @classmethod
    def _sane(cls, v: dict) -> dict:
        def walk(d):
            for k, x in (d or {}).items():
                if isinstance(x, dict):
                    walk(x)
                elif isinstance(x, (int, float)) and not (0 <= x <= 5_000_000):
                    raise ValueError(f"usage.{k} di luar batas")
        walk(v)
        return v


def _server_elapsed(call: dict, client_elapsed: int) -> int:
    """Billable seconds come from the server clock (started_at), never from the client-reported value alone."""
    st = call.get("started_at")
    if not st:
        return client_elapsed
    srv = int((datetime.now(timezone.utc) - datetime.fromisoformat(st)).total_seconds())
    return max(0, max(srv, client_elapsed))


@router.post("/realtime/calls/{call_id}/usage")
async def report_usage(call_id: str, x: UsageIn, u: dict = Depends(current_user)):
    """Bill one Realtime response from its real token usage (audio in/out, text, cached) × margin."""
    call = await _own_call(call_id, u)
    p = await get_pricing()
    usd = realtime_usage_usd(p, x.usage or {}, call.get("model"))
    exact = usd_to_credits(p, usd, "realtime_call")
    acc = float(call.get("usage_credits_exact") or 0) + exact
    charged = int(acc) - int(call.get("usage_credits_billed") or 0)
    if charged > 0:
        await record_usage(u["id"], "realtime_call", charged, {"call_id": call["id"], "conversation_id": call["conversation_id"], "usd": round(usd, 6)})
    await db.realtime_calls.update_one({"id": call["id"]}, {"$set": {"usage_credits_exact": acc, "usage_credits_billed": int(acc)},
                                                            "$inc": {"credits": charged, "usage_usd": usd}})
    return {"charged_now": charged, "credits_total": int(call.get("credits") or 0) + charged, "usd": round(usd, 6)}


@router.get("/realtime/vision-rate")
async def vision_rate(u: dict = Depends(current_user)):
    return {"credits": compute_rates(await get_pricing())["vision"]}


@router.post("/realtime/calls/{call_id}/snapshot")
async def snapshot(call_id: str, u: dict = Depends(current_user)):
    """Bill ONE screen snapshot shown to the assistant (the image itself goes browser → OpenAI directly; nothing is uploaded here)."""
    call = await _own_call(call_id, u)
    if call["status"] == "ended":
        raise HTTPException(400, "Call already ended")
    over = await quota_exceeded(u)
    if over:
        raise HTTPException(402, quota_message(over))
    credits = compute_rates(await get_pricing())["vision"]
    await record_usage(u["id"], "screen_snapshot", credits, {"call_id": call["id"], "conversation_id": call["conversation_id"], "call_session_id": call.get("call_session_id") or call.get("group_id")})
    await db.realtime_calls.update_one({"id": call["id"]}, {"$inc": {"snapshots": 1, "snapshot_credits": credits}})
    return {"credits": credits, "snapshots": int(call.get("snapshots") or 0) + 1}


async def _bill(call: dict, elapsed: int, u: dict) -> dict:
    minutes = max(1, math.ceil(elapsed / 60)) if elapsed > 0 else 0
    delta = minutes - int(call.get("billed_minutes") or 0)
    charged = 0
    if delta > 0:
        charged = delta * int(call["credits_per_min"])
        await record_usage(u["id"], "realtime_call", charged, {"call_id": call["id"], "conversation_id": call["conversation_id"], "minutes": delta})
    await db.realtime_calls.update_one({"id": call["id"]}, {"$set": {"billed_minutes": minutes, "seconds": elapsed},
                                                            "$inc": {"credits": charged}})
    return {"billed_minutes": minutes, "credits_total": int(call.get("credits") or 0) + charged, "charged_now": charged}


@router.post("/realtime/calls/{call_id}/tick")
async def tick(call_id: str, x: TickIn, u: dict = Depends(current_user)):
    call = await _own_call(call_id, u)
    if call["status"] == "ended":
        raise HTTPException(400, "Call already ended")
    elapsed = _server_elapsed(call, x.elapsed_seconds)
    out = await _bill(call, elapsed, u)
    lim = await get_limits()
    if elapsed >= lim["max_call_minutes"] * 60:
        await db.realtime_calls.update_one({"id": call_id}, {"$set": {"status": "ended", "ended_at": now_iso(), "reason": "max_duration"}})
        raise HTTPException(402, f"Durasi maksimal panggilan ({lim['max_call_minutes']} menit) tercapai")
    over = await quota_exceeded(u)
    owner = await db.users.find_one({"id": workspace_id(u)}, {"_id": 0, "credits": 1}) or {}
    if over or (owner.get("credits") or 0) <= 0:
        raise HTTPException(402, "Kuota/kredit habis — panggilan diakhiri")
    return out


@router.post("/realtime/calls/{call_id}/end")
async def end_call(call_id: str, x: TickIn, u: dict = Depends(current_user)):
    call = await _own_call(call_id, u)
    if call["status"] == "ended":
        return {"ok": True, "credits_total": call.get("credits", 0), "seconds": call.get("seconds", 0)}
    elapsed = _server_elapsed(call, x.elapsed_seconds)
    out = await _bill(call, elapsed, u)
    await db.realtime_calls.update_one({"id": call_id}, {"$set": {"status": "ended", "ended_at": now_iso()}})
    return {"ok": True, **out, "seconds": elapsed}
