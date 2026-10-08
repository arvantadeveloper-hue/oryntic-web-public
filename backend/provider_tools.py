"""Provider-hosted tools (OpenAI Responses API, Gemini googleSearch/codeExecution, Anthropic web_search/code_execution).
Uses the platform's own provider keys from .env (BYOK); the model decides when to call an enabled tool."""
import asyncio
import base64
import os
from typing import Optional

from db import new_id
from llm import resolve_model, provider_key
from pricing import TOOL_BY_ID, tool_credits, get_pricing
from storage import put_object


def persona_tools(persona: dict, model_key: Optional[str]) -> list:
    """Enabled tool ids that belong to the provider of the model answering this turn (and whose key is configured)."""
    provider, _ = resolve_model(model_key)
    env = {"openai": "OPENAI_API_KEY", "anthropic": "ANTHROPIC_API_KEY", "gemini": "GEMINI_API_KEY"}[provider]
    if not os.environ.get(env, "").strip():
        return []
    return [t for t in (persona.get("tools") or []) if t in TOOL_BY_ID and TOOL_BY_ID[t]["provider"] == provider]


def tools_prompt(tool_ids: list) -> str:
    labels = ", ".join(TOOL_BY_ID[t]["label"] for t in tool_ids)
    return (f"\n\nENABLED TOOLS: {labels}. Use them whenever they make the answer more accurate or current (fresh facts → search; "
            "calculations/data → run code; the user asks for a picture → image tool). Cite sources briefly when you searched. Never claim you cannot access the web or run code.")


async def _save_image(uid: str, b64: str, prompt: str) -> dict:
    raw = base64.b64decode(b64)
    path = f"aivora/images/{uid}/{new_id()}.png"
    from integrations import assert_quota, add_storage
    await assert_quota(uid, len(raw))
    await asyncio.to_thread(put_object, path, raw, "image/png")
    await add_storage(uid, len(raw))
    return {"type": "image", "path": path, "name": "gambar.png", "prompt": prompt[:400]}


async def _run_openai(system: str, prompt: str, model: str, tool_ids: list, uid: str) -> dict:
    from openai import AsyncOpenAI
    spec = {"openai:web_search": {"type": "web_search"}, "openai:code_interpreter": {"type": "code_interpreter", "container": {"type": "auto"}},
            "openai:image_generation": {"type": "image_generation"}}
    client = AsyncOpenAI(api_key=provider_key("openai"))
    r = await client.responses.create(model=model, instructions=system, input=prompt, tools=[spec[t] for t in tool_ids])
    counts, citations, media = {}, [], []
    for o in r.output:
        if o.type == "web_search_call":
            counts["openai:web_search"] = counts.get("openai:web_search", 0) + 1
        elif o.type == "code_interpreter_call":
            counts["openai:code_interpreter"] = counts.get("openai:code_interpreter", 0) + 1
        elif o.type == "image_generation_call" and getattr(o, "result", None):
            counts["openai:image_generation"] = counts.get("openai:image_generation", 0) + 1
            media.append(await _save_image(uid, o.result, getattr(o, "revised_prompt", None) or prompt))
        elif o.type == "message":
            for part in o.content:
                for a in getattr(part, "annotations", None) or []:
                    if getattr(a, "type", "") == "url_citation" and getattr(a, "url", None):
                        citations.append({"url": a.url, "title": getattr(a, "title", None) or a.url})
    return {"text": (r.output_text or "").strip(), "counts": counts, "citations": citations, "media": media}


async def _run_litellm(system: str, prompt: str, provider: str, model: str, tool_ids: list) -> dict:
    from emergentintegrations.llm.chat import LlmChat, UserMessage
    spec = {"gemini:google_search": {"googleSearch": {}}, "gemini:code_execution": {"codeExecution": {}},
            "anthropic:web_search": {"type": "web_search_20250305", "name": "web_search", "max_uses": 5},
            "anthropic:code_execution": {"type": "code_execution_20250825", "name": "code_execution"}}
    chat = LlmChat(api_key=provider_key(provider), session_id=new_id(), system_message=system).with_model(provider, model).with_tools([spec[t] for t in tool_ids])
    resp = await chat.send_message_with_tools(UserMessage(text=prompt))
    raw, msg = resp.raw, resp.raw.choices[0].message
    counts, citations = {}, []
    for a in getattr(msg, "annotations", None) or []:
        a = a if isinstance(a, dict) else a.model_dump()
        uc = a.get("url_citation") or {}
        if uc.get("url"):
            citations.append({"url": uc["url"], "title": uc.get("title") or uc["url"]})
    psf = getattr(msg, "provider_specific_fields", None) or {}
    for group in (psf.get("citations") or []) if isinstance(psf, dict) else []:
        for c in group or []:
            if c.get("url") and c["url"] not in {x["url"] for x in citations}:
                citations.append({"url": c["url"], "title": c.get("title") or c["url"]})
    if provider == "anthropic":
        stu = getattr(getattr(raw, "usage", None), "server_tool_use", None)
        n = int(getattr(stu, "web_search_requests", 0) or 0)
        if n and "anthropic:web_search" in tool_ids:
            counts["anthropic:web_search"] = n
        if "anthropic:code_execution" in tool_ids:
            counts["anthropic:code_execution"] = 1  # container usage is not reported per call → billed per request with the tool on
    else:
        grounded = bool(citations) or bool(getattr(raw, "vertex_ai_grounding_metadata", None))
        if grounded and "gemini:google_search" in tool_ids:
            counts["gemini:google_search"] = 1
    return {"text": (resp.content or "").strip(), "counts": counts, "citations": citations, "media": []}


WEB_SEARCH_TOOLS = {"openai": "openai:web_search", "gemini": "gemini:google_search", "anthropic": "anthropic:web_search"}


def web_search_tool(persona: dict) -> Optional[str]:
    """The web-search tool enabled for this persona's model provider (used by voice calls), else None."""
    ids = persona_tools(persona, persona.get("model"))
    tid = WEB_SEARCH_TOOLS[resolve_model(persona.get("model"))[0]]
    return tid if tid in ids else None


async def voice_web_search(persona: dict, lang_name: str, query: str, uid: str) -> dict:
    """Voice-call helper: search the live web with the persona's provider tool → short spoken-style answer + sources."""
    tid = web_search_tool(persona)
    if not tid:
        raise ValueError("web search not enabled")
    system = (f"You are {persona.get('name')}'s research helper. Search the web and answer the question in {lang_name} in at most 3 short spoken sentences "
              "(no markdown, no bullet lists, no URLs in the text). Name the source site briefly in words (e.g. 'menurut Kompas'). Facts must come from the search results.")
    return await run_with_tools(system, query, persona.get("model"), [tid], uid)


async def run_with_tools(system: str, prompt: str, model_key: Optional[str], tool_ids: list, uid: str) -> dict:
    """→ {text, tools_used:[{id,label,count,credits}], tool_credits, citations, media}. Raises on provider failure (caller falls back)."""
    provider, model = resolve_model(model_key)
    system = system + tools_prompt(tool_ids)
    out = await (_run_openai(system, prompt, model, tool_ids, uid) if provider == "openai" else _run_litellm(system, prompt, provider, model, tool_ids))
    p = await get_pricing()
    used = []
    for tid, n in out["counts"].items():
        per = tool_credits(p, tid)
        used.append({"id": tid, "label": TOOL_BY_ID[tid]["label"], "count": n, "credits": per * n})
    out["tools_used"] = used
    out["tool_credits"] = sum(x["credits"] for x in used)
    out["citations"] = out["citations"][:8]
    return out
