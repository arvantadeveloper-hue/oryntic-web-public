"""Provider-hosted tools (OpenAI Responses API, Gemini googleSearch/codeExecution, Anthropic web_search/code_execution).
Uses the platform's own provider keys from .env (BYOK); the model decides when to call an enabled tool."""
import base64
import os
import re
from typing import Optional

from db import new_id
from llm import resolve_model, provider_key
from pricing import TOOL_BY_ID, tool_credits, get_pricing


def persona_tools(persona: dict, model_key: Optional[str]) -> list:
    """Enabled tool ids that belong to the provider of the model answering this turn (and whose key is configured)."""
    provider, _ = resolve_model(model_key)
    env = {"openai": "OPENAI_API_KEY", "anthropic": "ANTHROPIC_API_KEY", "gemini": "GEMINI_API_KEY"}[provider]
    if not os.environ.get(env, "").strip():
        return []
    ids = [t for t in (persona.get("tools") or []) if t in TOOL_BY_ID and TOOL_BY_ID[t]["provider"] == provider]
    if not persona.get("vector_store_id"):  # file_search needs at least one synced knowledge document
        ids = [t for t in ids if t != "openai:file_search"]
    return ids


def uses_file_search(persona: dict, model_key: Optional[str]) -> bool:
    return "openai:file_search" in persona_tools(persona, model_key)


def tools_prompt(tool_ids: list) -> str:
    labels = ", ".join(TOOL_BY_ID[t]["label"] for t in tool_ids)
    return (f"\n\nENABLED TOOLS: {labels}. Use them whenever they make the answer more accurate or current (fresh facts → search; "
            "calculations/data → run code; the user asks for a picture → image tool; anything the assistant's own documents may answer → file search, and cite the document title). When you run code on data that suits a visual, ALSO save a chart as a PNG file and present tables as markdown tables. "
            "Cite sources briefly when you searched. Never claim you cannot access the web or run code.")


async def _hold(uid: str, name: str, mime: str, data: bytes, meta: dict) -> dict:
    from pending_files import hold_file
    return await hold_file(uid, name, mime, data, meta)


async def _container_files(client, r, uid: str) -> list:
    """Code Interpreter outputs (charts, CSV, XLSX…) referenced by the answer → downloaded and HELD for the user's Simpan confirmation."""
    import hashlib
    seen, hashes, found = set(), set(), []
    for o in r.output:
        if o.type != "message":
            continue
        for part in o.content:
            for a in getattr(part, "annotations", None) or []:
                if getattr(a, "type", "") == "container_file_citation" and getattr(a, "file_id", None) and a.file_id not in seen:
                    seen.add(a.file_id)
                    try:
                        resp = await client.containers.files.content.retrieve(a.file_id, container_id=a.container_id)
                        data = await resp.aread() if hasattr(resp, "aread") else resp.content
                    except Exception:
                        continue
                    h = hashlib.sha1(data).hexdigest()
                    if h in hashes:
                        continue  # the same chart cited twice
                    hashes.add(h)
                    name = getattr(a, "filename", None) or f"hasil-{len(found) + 1}.png"
                    ext = os.path.splitext(name)[1].lower()
                    mime = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".csv": "text/csv", ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            ".pdf": "application/pdf", ".json": "application/json", ".txt": "text/plain", ".md": "text/markdown", ".html": "text/html"}.get(ext, "application/octet-stream")
                    found.append((name, mime, data))
    # plt.show() auto-captures an unnamed "cfile_….png"; drop it when the model also saved a named image of its own
    if any(n.startswith("cfile_") and m.startswith("image/") for n, m, _ in found) and any(not n.startswith("cfile_") and m.startswith("image/") for n, m, _ in found):
        found = [f for f in found if not (f[0].startswith("cfile_") and f[1].startswith("image/"))]
    held = []
    for name, mime, data in found:
        if name.startswith("cfile_"):
            name = f"grafik-{len(held) + 1}{os.path.splitext(name)[1] or '.png'}"
        held.append(await _hold(uid, name, mime, data, {"source": "code_interpreter"}))
    return held


async def _run_openai(system: str, prompt: str, model: str, tool_ids: list, uid: str, vector_store_ids: Optional[list] = None) -> dict:
    from openai import AsyncOpenAI
    spec = {"openai:web_search": {"type": "web_search"}, "openai:code_interpreter": {"type": "code_interpreter", "container": {"type": "auto"}},
            "openai:image_generation": {"type": "image_generation"},
            "openai:file_search": {"type": "file_search", "vector_store_ids": vector_store_ids or [], "max_num_results": 8}}
    if not vector_store_ids:
        tool_ids = [t for t in tool_ids if t != "openai:file_search"]
    client = AsyncOpenAI(api_key=provider_key("openai"))
    r = await client.responses.create(model=model, instructions=system, input=prompt, tools=[spec[t] for t in tool_ids])
    counts, citations, pending, files = {}, [], [], []
    for o in r.output:
        if o.type == "web_search_call":
            counts["openai:web_search"] = counts.get("openai:web_search", 0) + 1
        elif o.type == "file_search_call":
            counts["openai:file_search"] = counts.get("openai:file_search", 0) + 1
        elif o.type == "code_interpreter_call":
            counts["openai:code_interpreter"] = counts.get("openai:code_interpreter", 0) + 1
        elif o.type == "image_generation_call" and getattr(o, "result", None):
            counts["openai:image_generation"] = counts.get("openai:image_generation", 0) + 1
            pending.append(await _hold(uid, "gambar.png", "image/png", base64.b64decode(o.result), {"source": "image_generation", "prompt": (getattr(o, "revised_prompt", None) or prompt)[:400]}))
        elif o.type == "message":
            for part in o.content:
                for a in getattr(part, "annotations", None) or []:
                    if getattr(a, "type", "") == "url_citation" and getattr(a, "url", None):
                        citations.append({"url": a.url, "title": getattr(a, "title", None) or a.url})
                    elif getattr(a, "type", "") == "file_citation" and getattr(a, "filename", None) and a.filename not in files:
                        files.append(a.filename)
    if "openai:code_interpreter" in counts:
        pending += await _container_files(client, r, uid)
    text = re.sub(r"\[([^\]]*)\]\(sandbox:[^)]*\)", r"\1", (r.output_text or "")).strip()  # sandbox:/mnt/data links are unusable outside the container
    if files:
        text += "\n\n📄 Sumber dokumen: " + ", ".join(re.sub(r"\.txt$", "", f).replace("_", " ") for f in files[:6])
    return {"text": text, "counts": counts, "citations": citations, "media": [], "pending_files": pending}


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
    return {"text": (resp.content or "").strip(), "counts": counts, "citations": citations, "media": [], "pending_files": []}


WEB_SEARCH_TOOLS = {"openai": "openai:web_search", "gemini": "gemini:google_search", "anthropic": "anthropic:web_search"}
CODE_TOOLS = {"openai": "openai:code_interpreter", "gemini": "gemini:code_execution", "anthropic": "anthropic:code_execution"}


def _voice_tool(persona: dict, table: dict) -> Optional[str]:
    ids = persona_tools(persona, persona.get("model"))
    tid = table[resolve_model(persona.get("model"))[0]]
    return tid if tid in ids else None


def web_search_tool(persona: dict) -> Optional[str]:
    """The web-search tool enabled for this persona's model provider (used by voice calls), else None."""
    return _voice_tool(persona, WEB_SEARCH_TOOLS)


def code_tool(persona: dict) -> Optional[str]:
    """The Python/code-execution tool enabled for this persona's model provider, else None."""
    return _voice_tool(persona, CODE_TOOLS)


async def voice_web_search(persona: dict, lang_name: str, query: str, uid: str) -> dict:
    """Voice-call helper: search the live web with the persona's provider tool → short spoken-style answer + sources."""
    tid = web_search_tool(persona)
    if not tid:
        raise ValueError("web search not enabled")
    system = (f"You are {persona.get('name')}'s research helper. Search the web and answer the question in {lang_name} in at most 3 short spoken sentences "
              "(no markdown, no bullet lists, no URLs in the text). Name the source site briefly in words (e.g. 'menurut Kompas'). Facts must come from the search results.")
    return await run_with_tools(system, query, persona.get("model"), [tid], uid)


async def voice_run_code(persona: dict, lang_name: str, task: str, uid: str) -> dict:
    """Voice-call helper: solve a calculation/data task by actually running Python → short spoken result."""
    tid = code_tool(persona)
    if not tid:
        raise ValueError("code execution not enabled")
    system = (f"You are {persona.get('name')}'s calculation helper. You MUST solve the task by running Python code (never estimate mentally). "
              f"Reply in {lang_name} in at most 3 short spoken sentences: state the result clearly (numbers in words-friendly form, e.g. 'sekitar 2,4 juta' plus the exact figure), "
              "and one short phrase on how it was computed. No code in the reply, no bullet lists. If the result is a series/comparison/breakdown, ALSO save a clear chart as a PNG file "
              "(matplotlib, labeled axes, Indonesian labels) and, when useful, a CSV of the numbers; mention briefly that the chart was sent to the chat.")
    return await run_with_tools(system, task, persona.get("model"), [tid], uid)


async def run_with_tools(system: str, prompt: str, model_key: Optional[str], tool_ids: list, uid: str, vector_store_ids: Optional[list] = None) -> dict:
    """→ {text, tools_used:[{id,label,count,credits}], tool_credits, citations, media}. Raises on provider failure (caller falls back)."""
    provider, model = resolve_model(model_key)
    system = system + tools_prompt(tool_ids)
    out = await (_run_openai(system, prompt, model, tool_ids, uid, vector_store_ids) if provider == "openai" else _run_litellm(system, prompt, provider, model, tool_ids))
    p = await get_pricing()
    used = []
    for tid, n in out["counts"].items():
        per = tool_credits(p, tid)
        used.append({"id": tid, "label": TOOL_BY_ID[tid]["label"], "count": n, "credits": per * n})
    out["tools_used"] = used
    out["tool_credits"] = sum(x["credits"] for x in used)
    out["citations"] = out["citations"][:8]
    return out
