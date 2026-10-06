import json
import asyncio
import math
from pricing import RATES
from typing import Optional
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from db import db, now_iso, new_id, clean
from auth import current_user, workspace_id, lang_rule
from workspace import task_access, get_task_for, task_view
from llm import llm_text, llm_json, record_usage, text_credits, DEFAULT_MODEL_KEY, MODEL_CATALOG

router = APIRouter(prefix="/api", tags=["agents"])

_MODEL_IDS = {m["id"] for m in MODEL_CATALOG}

# Recommended "best" model per task category. Some are specialized/not executable here.
TASK_MODEL_RECO = {
    "video": {"id": "seedance-2.5", "label": "Seedance 2.5", "reason": "Model terbaik untuk pembuatan video", "executable": False},
    "image": {"id": "gemini-pro", "label": "Gemini 3.1 Pro", "reason": "Kuat untuk tugas visual & multimodal", "executable": True},
    "code": {"id": "claude-sonnet", "label": "Claude Sonnet 5.5", "reason": "Unggul untuk coding & reasoning", "executable": True},
    "writing": {"id": "claude-sonnet", "label": "Claude Sonnet 5.5", "reason": "Penulisan panjang berkualitas tinggi", "executable": True},
    "research": {"id": "gemini-pro", "label": "Gemini 3.1 Pro", "reason": "Sintesis riset & reasoning kuat", "executable": True},
    "data": {"id": "gpt-astra", "label": "GPT Astra", "reason": "Analisis data kompleks & akurat", "executable": True},
}
_KW = {
    "video": ["video", "klip", "clip", "animasi", "reels", "footage", "seedance", "render video"],
    "image": ["gambar", "image", "foto", "ilustrasi", "poster", "logo", "desain visual"],
    "code": ["kode", "code", "program", "script", "api", "bug", "fungsi", "aplikasi", "software"],
    "writing": ["tulis", "artikel", "esai", "cerita", "naskah", "copywriting", "blog", "surat"],
    "research": ["riset", "research", "cari informasi", "bandingkan", "analisis pasar", "literatur"],
    "data": ["data", "spreadsheet", "statistik", "analisa angka", "dataset", "metrik", "excel"],
}


async def _emit_task(task_id: str):
    """Progress ping so open Workspace views update over the user WebSocket instead of polling."""
    from realtime import notify_user
    t = await db.tasks.find_one({"id": task_id}, {"_id": 0, "user_id": 1, "status": 1})
    if t and t.get("user_id"):
        await notify_user(t["user_id"], {"type": "task_update", "task_id": task_id, "status": t.get("status") or "running", "progress": True})


def _classify(goal: str):
    g = goal.lower()
    for cat, kws in _KW.items():
        if any(k in g for k in kws):
            return cat
    return None

ROLE_PROMPTS = {
    "Research": "You are the Research Agent. Gather and organize relevant information, facts, and context for the subtask. Be factual and cite assumptions. Do not fabricate sources.",
    "Planning": "You are the Planning Agent. Produce a clear, structured plan or outline for the subtask.",
    "Writing": "You are the Writing Agent. Produce polished, well-structured written content in markdown for the subtask.",
    "Analyst": "You are the Analyst Agent. Analyze information, compare options, and produce clear findings and recommendations.",
    "Coding": "You are the Coding Agent. Produce correct, well-commented code in fenced code blocks for the subtask.",
    "Reviewer": "You are the Reviewer Agent. Review quality, consistency, and completeness; note issues and improvements.",
}


class TaskIn(BaseModel):
    goal: str = Field(min_length=1, max_length=4000)
    persona_id: Optional[str] = None
    model: Optional[str] = None


async def _plan_steps(task_id: str, goal: str, model_key: str, rule: str):
    """Coordinator breaks the goal into 2-4 subtasks. Returns (steps, credits)."""
    plan_sys = (
        "You are the orchestration coordinator of a team of AI agents. Break the user's goal into 2-4 concrete "
        "subtasks. For each subtask choose one role from: Research, Planning, Writing, Analyst, Coding. "
        'Respond JSON: {"plan_summary": str, "subtasks": [{"role": str, "title": str, "instruction": str}]}\n' + rule +
        " (plan_summary, every title and every instruction must follow the language rule.)"
    )
    plan = await llm_json(plan_sys, f"Goal: {goal}", model_key)
    subtasks = plan.get("subtasks", [])[:4] or [{"role": "Writing", "title": "Complete request", "instruction": goal}]
    steps = [{"id": new_id(), "role": st.get("role", "Writing"), "title": st.get("title", "Subtask"),
              "instruction": st.get("instruction", goal), "status": "pending", "output": "", "created_at": now_iso()} for st in subtasks]
    await db.tasks.update_one({"id": task_id}, {"$set": {"steps": steps, "summary": plan.get("plan_summary", ""), "updated_at": now_iso()}}); await _emit_task(task_id)
    return steps, text_credits(goal, json.dumps(plan))


async def _run_step(task_id: str, goal: str, step: dict, steps: list, model_key: str, rule: str) -> int:
    """Execute one subtask (one retry), persist progress, return credits used."""
    step["status"] = "running"
    await db.tasks.update_one({"id": task_id}, {"$set": {"steps": steps, "updated_at": now_iso()}}); await _emit_task(task_id)
    role = step["role"] if step["role"] in ROLE_PROMPTS else "Writing"
    sys = ROLE_PROMPTS[role] + " Keep the output focused and useful.\n" + rule
    prompt = f"Overall goal: {goal}\n\nYour subtask: {step['title']}\nInstructions: {step['instruction']}\n\n(Reminder: {rule})"
    out = ""
    for _ in range(2):
        try:
            out = await llm_text(sys, prompt, model_key)
        except Exception:
            out = ""
        if out:
            break
    step["output"] = out or "(This subtask could not be completed.)"
    step["status"] = "completed"
    await db.tasks.update_one({"id": task_id}, {"$set": {"steps": steps, "updated_at": now_iso()}}); await _emit_task(task_id)
    return text_credits(prompt, step["output"])


async def _merge_outputs(goal: str, steps: list, model_key: str, rule: str):
    merge_sys = (
        "You are the orchestration coordinator with a Reviewer. Combine the agents' outputs into a single, "
        "coherent, well-structured final deliverable in markdown. Remove redundancy, ensure consistency, "
        "and add a short executive summary at the top.\n" + rule + " If any agent output is in the wrong language, translate it."
    )
    outputs = [f"### {s['title']} ({s['role']})\n{s['output']}" for s in steps]
    merge_prompt = f"Goal: {goal}\n\nAgent outputs:\n\n" + "\n\n".join(outputs) + f"\n\n(Reminder: {rule})"
    final = await llm_text(merge_sys, merge_prompt, model_key)
    return final, text_credits(merge_prompt, final)


async def _attach_video(task_id: str, user_id: str, goal: str, final: str):
    """Video tasks: render with Seedance (fal.ai) and persist to object storage. Returns (final, url, path, credits)."""
    await db.tasks.update_one({"id": task_id}, {"$set": {"status": "running", "summary": "Membuat video dengan Seedance...", "updated_at": now_iso()}}); await _emit_task(task_id)
    video_url, video_path, credits = None, None, 0
    try:
        from video_gen import generate_seedance_video
        from storage import store_remote_video
        video_url = await asyncio.to_thread(generate_seedance_video, goal)
        if video_url:
            credits = max(1, math.ceil(float(RATES.get("video_per_sec", 16)) * 5))  # 5-second Seedance clip at platform tariff
            await record_usage(user_id, "video_generation", credits, {"task_id": task_id})
            video_path = await asyncio.to_thread(store_remote_video, video_url, user_id, task_id)
            final += "\n\n## Video\nVideo berhasil dibuat dengan Seedance dan disimpan permanen."
        else:
            final += "\n\n> Catatan: eksekusi video tidak mengembalikan hasil."
    except Exception as ve:
        final += f"\n\n> Catatan: eksekusi video gagal ({str(ve)[:120]}). Rencana di atas tetap tersedia."
    return final, video_url, video_path, credits


async def _orchestrate(task_id: str, user_id: str, goal: str, model_key: str = None):
    try:
        await db.tasks.update_one({"id": task_id}, {"$set": {"status": "running", "updated_at": now_iso()}}); await _emit_task(task_id)
        rule = lang_rule(await db.users.find_one({"id": user_id}, {"_id": 0, "settings": 1}) or {})
        steps, credits_total = await _plan_steps(task_id, goal, model_key, rule)
        for step in steps:
            credits_total += await _run_step(task_id, goal, step, steps, model_key, rule)
        final, used = await _merge_outputs(goal, steps, model_key, rule)
        credits_total += used
        video_url = video_path = None
        if _classify(goal) == "video":
            final, video_url, video_path, used = await _attach_video(task_id, user_id, goal, final)
            credits_total += used
        await record_usage(user_id, "multi_agent_task", credits_total, {"task_id": task_id})
        await db.tasks.update_one({"id": task_id}, {"$set": {
            "status": "completed", "final_output": final, "credits_used": credits_total,
            "video_url": video_url, "video_path": video_path, "updated_at": now_iso()}})
    except Exception as e:
        await db.tasks.update_one({"id": task_id}, {"$set": {
            "status": "failed", "error": str(e)[:200], "updated_at": now_iso()}})


@router.post("/tasks/recommend")
async def recommend(x: TaskIn, u: dict = Depends(current_user)):
    cat = _classify(x.goal)
    reco = TASK_MODEL_RECO.get(cat)
    needs_choice = bool(reco) and reco["id"] != DEFAULT_MODEL_KEY
    return {"category": cat, "recommendation": reco, "needs_choice": needs_choice, "default": DEFAULT_MODEL_KEY}


@router.post("/tasks")
async def create_task(x: TaskIn, u: dict = Depends(current_user)):
    model_key = x.model if x.model in _MODEL_IDS else DEFAULT_MODEL_KEY
    tid = new_id()
    doc = {
        "id": tid, "user_id": u["id"], "workspace_id": workspace_id(u), "goal": x.goal, "persona_id": x.persona_id, "version": 1, "source": "workspace",
        "type": "multi_agent", "status": "queued", "steps": [], "summary": "",
        "model": model_key, "final_output": "", "credits_used": 0,
        "created_at": now_iso(), "updated_at": now_iso(),
    }
    await db.tasks.insert_one(dict(doc))
    asyncio.create_task(_orchestrate(tid, u["id"], x.goal, model_key))
    return clean(doc)


@router.get("/tasks")
async def list_tasks(status: Optional[str] = None, q: Optional[str] = None, u: dict = Depends(current_user)):
    query = task_access(u)
    if status and status != "all":
        query["status"] = status
    if q:
        query["goal"] = {"$regex": q, "$options": "i"}
    return await db.tasks.find(query, {"_id": 0, "versions": 0}).sort("created_at", -1).to_list(200)


@router.get("/tasks/{tid}")
async def get_task(tid: str, u: dict = Depends(current_user)):
    return task_view(await get_task_for(tid, u))


@router.post("/tasks/{tid}/cancel")
async def cancel_task(tid: str, u: dict = Depends(current_user)):
    t = await get_task_for(tid, u)
    if t["status"] in ("queued", "running"):
        await db.tasks.update_one({"id": tid}, {"$set": {"status": "cancelled", "updated_at": now_iso()}})
    return {"ok": True}


@router.delete("/tasks/{tid}")
async def delete_task(tid: str, u: dict = Depends(current_user)):
    await db.tasks.delete_one({"id": tid, **task_access(u)})
    return {"ok": True}
