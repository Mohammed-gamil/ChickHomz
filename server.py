"""
server.py — Custom FastAPI backend for Chic Homz Sales Agent.

Replaces `langgraph dev`. No LangSmith. No browser pop-ups. Zero extra tooling.

Endpoints:
  POST /threads                          → create persistent thread
  POST /threads/{thread_id}/runs/stream  → run graph, stream state as SSE
  GET  /health                           → liveness probe
"""

from __future__ import annotations

import asyncio
import json
import os
import threading
import uuid
from typing import Any, AsyncGenerator

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

load_dotenv()

# ── Build graph with in-memory checkpointer ───────────────────────────────────
# Import after dotenv so env vars (OPENROUTER_API_KEY etc.) are available.
from agent import build_graph  # noqa: E402

_checkpointer = MemorySaver()
_graph = build_graph().compile(
    checkpointer=_checkpointer,
    interrupt_before=["clarify"],
)

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(title="Chic Homz Agent API", docs_url=None, redoc_url=None)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Thread registry (just tracks existence; real state is in MemorySaver)
_threads: dict[str, dict] = {}


# ── Serialisation helper ──────────────────────────────────────────────────────
def _ser(obj: Any) -> Any:
    """Recursively make LangGraph state JSON-serialisable."""
    if isinstance(obj, dict):
        return {k: _ser(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_ser(i) for i in obj]
    if isinstance(obj, HumanMessage):
        return {"type": "human", "content": obj.content}
    if isinstance(obj, AIMessage):
        return {"type": "ai", "content": obj.content}
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    try:
        json.dumps(obj)
        return obj
    except Exception:
        return str(obj)


# ── Endpoints ─────────────────────────────────────────────────────────────────
@app.post("/threads")
async def create_thread(request: Request):
    thread_id = str(uuid.uuid4())
    try:
        body = await request.json()
        _threads[thread_id] = body.get("metadata", {})
    except Exception:
        _threads[thread_id] = {}
    return {"thread_id": thread_id}


async def _sse_stream(thread_id: str, body: dict) -> AsyncGenerator[str, None]:
    inp = body.get("input", {})
    raw_msgs = inp.get("messages", [])
    raw_query = inp.get("raw_query", "")

    # Convert to LangChain messages
    messages: list = []
    for m in raw_msgs:
        content = m.get("content", "")
        messages.append(
            HumanMessage(content=content)
            if m.get("role", "human") == "human"
            else AIMessage(content=content)
        )
    if not raw_query and messages:
        raw_query = messages[-1].content

    config = {"configurable": {"thread_id": thread_id}}

    # ── Decide: resume interrupted thread OR new/continuing run ──────────────
    try:
        saved = _graph.get_state(config)
        is_resuming = bool(saved.next) and "clarify" in saved.next
        is_first_turn = not bool(saved.values.get("messages"))
    except Exception:
        is_resuming = False
        is_first_turn = True

    if is_resuming:
        # Resume clarification interrupt with user's reply
        graph_input: Any = Command(resume=raw_query)
    elif is_first_turn:
        # First message — supply full initial state
        graph_input = {
            "messages": messages,
            "raw_query": raw_query,
            "customer_profile": {},
            "intent_analysis": {},
            "retrieved_products": [],
            "ranked_products": [],
            "response_draft": "",
            "needs_clarification": False,
            "clarification_question": "",
            "turn_count": 0,
            "interrupt_triggered": False,
        }
    else:
        # Subsequent turns — only supply new fields; let checkpointer restore rest
        graph_input = {
            "messages": messages,
            "raw_query": raw_query,
        }

    # ── Stream graph in background thread (sync LangGraph → async bridge) ────
    loop = asyncio.get_event_loop()
    queue: asyncio.Queue = asyncio.Queue()

    def _run() -> None:
        try:
            for chunk in _graph.stream(graph_input, config=config, stream_mode="values"):
                loop.call_soon_threadsafe(queue.put_nowait, chunk)
        except Exception as exc:
            loop.call_soon_threadsafe(queue.put_nowait, {"__error__": str(exc)})
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, None)  # sentinel

    threading.Thread(target=_run, daemon=True).start()

    while True:
        chunk = await queue.get()
        if chunk is None:
            break
        if "__error__" not in chunk:
            yield f"data: {json.dumps(_ser(chunk), ensure_ascii=False)}\n\n"

    # ── After stream: check for pending clarification interrupt ──────────────
    try:
        final = _graph.get_state(config)
        if final.next and "clarify" in final.next:
            q = (
                final.values.get("clarification_question")
                or "ممكن تقولي أكتر عن اللي بتدور عليه؟"
            )
            synthetic = {
                "messages": [{"type": "ai", "content": q}],
                "__interrupt__": [{"value": q}],
            }
            yield f"data: {json.dumps(synthetic, ensure_ascii=False)}\n\n"
    except Exception:
        pass

    yield "data: [DONE]\n\n"


@app.post("/threads/{thread_id}/runs/stream")
async def stream_run(thread_id: str, request: Request):
    if thread_id not in _threads:
        raise HTTPException(status_code=404, detail="Thread not found")
    body = await request.json()
    return StreamingResponse(
        _sse_stream(thread_id, body),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/health")
async def health():
    return {"status": "ok"}


# ── Serve React frontend (must come after all API routes) ─────────────────────
_DIST = os.path.join(os.path.dirname(__file__), "frontend", "dist")

# Explicit MIME types (Windows registry often has wrong values)
_MIME_TYPES = {
    ".js": "application/javascript",
    ".mjs": "application/javascript",
    ".css": "text/css",
    ".html": "text/html",
    ".json": "application/json",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
    ".ttf": "font/ttf",
}


def _get_mime(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    return _MIME_TYPES.get(ext, "application/octet-stream")


if os.path.isdir(_DIST):
    @app.get("/")
    async def serve_index():
        return FileResponse(os.path.join(_DIST, "index.html"), media_type="text/html")

    @app.get("/{full_path:path}")
    async def serve_static(full_path: str):
        file_path = os.path.join(_DIST, full_path)
        if os.path.isfile(file_path):
            return FileResponse(file_path, media_type=_get_mime(file_path))
        # SPA fallback
        return FileResponse(os.path.join(_DIST, "index.html"), media_type="text/html")


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    port = int(os.getenv("PORT", 2024))
    print(f"\n🏠  Chic Homz Sales Agent  →  http://localhost:{port}\n")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")
