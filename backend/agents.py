import json
import asyncio
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from db import db, now_iso, new_id, clean
from auth import current_user
from llm import llm_text, llm_json, record_usage, text_credits

router = APIRouter(prefix="/api", tags=["agents"])

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


async def _orchestrate(task_id: str, user_id: str, goal: str):
    try:
        task = await db.tasks.find_one({"id": task_id})
        await db.tasks.update_one({"id": task_id}, {"$set": {"status": "running", "updated_at": now_iso()}})

        # 1. Coordinator plans
        plan_sys = (
            "You are Aivora, the coordinator of a team of AI agents. Break the user's goal into 2-4 concrete "
            "subtasks. For each subtask choose one role from: Research, Planning, Writing, Analyst, Coding. "
            'Respond JSON: {"plan_summary": str, "subtasks": [{"role": str, "title": str, "instruction": str}]}'
        )
        plan = await llm_json(plan_sys, f"Goal: {goal}")
        subtasks = plan.get("subtasks", [])[:4]
        if not subtasks:
            subtasks = [{"role": "Writing", "title": "Complete request", "instruction": goal}]
        credits_total = text_credits(goal, json.dumps(plan))

        steps = []
        for st in subtasks:
            steps.append({
                "id": new_id(), "role": st.get("role", "Writing"), "title": st.get("title", "Subtask"),
                "instruction": st.get("instruction", goal), "status": "pending", "output": "", "created_at": now_iso(),
            })
        await db.tasks.update_one({"id": task_id}, {"$set": {
            "steps": steps, "summary": plan.get("plan_summary", ""), "updated_at": now_iso()}})

        # 2. Run each subtask
        outputs = []
        for step in steps:
            step["status"] = "running"
            await db.tasks.update_one({"id": task_id}, {"$set": {"steps": steps, "updated_at": now_iso()}})
            role = step["role"] if step["role"] in ROLE_PROMPTS else "Writing"
            sys = ROLE_PROMPTS[role] + " Keep the output focused and useful."
            prompt = f"Overall goal: {goal}\n\nYour subtask: {step['title']}\nInstructions: {step['instruction']}"
            try:
                out = await llm_text(sys, prompt)
            except Exception:
                out = ""
            if not out:
                try:
                    out = await llm_text(sys, prompt)  # retry once
                except Exception:
                    out = "(This subtask could not be completed.)"
            step["output"] = out
            step["status"] = "completed"
            credits_total += text_credits(prompt, out)
            outputs.append(f"### {step['title']} ({role})\n{out}")
            await db.tasks.update_one({"id": task_id}, {"$set": {"steps": steps, "updated_at": now_iso()}})

        # 3. Coordinator + Reviewer merge
        merge_sys = (
            "You are Aivora the coordinator with a Reviewer. Combine the agents' outputs into a single, "
            "coherent, well-structured final deliverable in markdown. Remove redundancy, ensure consistency, "
            "and add a short executive summary at the top."
        )
        merge_prompt = f"Goal: {goal}\n\nAgent outputs:\n\n" + "\n\n".join(outputs)
        final = await llm_text(merge_sys, merge_prompt)
        credits_total += text_credits(merge_prompt, final)

        await record_usage(user_id, "multi_agent_task", credits_total, {"task_id": task_id})
        await db.tasks.update_one({"id": task_id}, {"$set": {
            "status": "completed", "final_output": final, "credits_used": credits_total,
            "updated_at": now_iso()}})
    except Exception as e:
        await db.tasks.update_one({"id": task_id}, {"$set": {
            "status": "failed", "error": str(e)[:200], "updated_at": now_iso()}})


@router.post("/tasks")
async def create_task(x: TaskIn, u: dict = Depends(current_user)):
    tid = new_id()
    doc = {
        "id": tid, "user_id": u["id"], "goal": x.goal, "persona_id": x.persona_id,
        "type": "multi_agent", "status": "queued", "steps": [], "summary": "",
        "final_output": "", "credits_used": 0, "created_at": now_iso(), "updated_at": now_iso(),
    }
    await db.tasks.insert_one(dict(doc))
    asyncio.create_task(_orchestrate(tid, u["id"], x.goal))
    return clean(doc)


@router.get("/tasks")
async def list_tasks(status: Optional[str] = None, q: Optional[str] = None, u: dict = Depends(current_user)):
    query = {"user_id": u["id"]}
    if status and status != "all":
        query["status"] = status
    if q:
        query["goal"] = {"$regex": q, "$options": "i"}
    return await db.tasks.find(query, {"_id": 0}).sort("created_at", -1).to_list(200)


@router.get("/tasks/{tid}")
async def get_task(tid: str, u: dict = Depends(current_user)):
    t = await db.tasks.find_one({"id": tid, "user_id": u["id"]}, {"_id": 0})
    if not t:
        raise HTTPException(404, "Task not found")
    return t


@router.post("/tasks/{tid}/cancel")
async def cancel_task(tid: str, u: dict = Depends(current_user)):
    t = await db.tasks.find_one({"id": tid, "user_id": u["id"]})
    if not t:
        raise HTTPException(404, "Task not found")
    if t["status"] in ("queued", "running"):
        await db.tasks.update_one({"id": tid}, {"$set": {"status": "cancelled", "updated_at": now_iso()}})
    return {"ok": True}


@router.delete("/tasks/{tid}")
async def delete_task(tid: str, u: dict = Depends(current_user)):
    await db.tasks.delete_one({"id": tid, "user_id": u["id"]})
    return {"ok": True}
