"""
server.py — Custom FastAPI backend for Chic Homz Sales Agent.

Replaces `langgraph dev`. No LangSmith. No browser pop-ups. Zero extra tooling.

Endpoints:
  POST /threads                          → create persistent thread
  POST /threads/{thread_id}/runs/stream  → run graph, stream state as SSE
  POST /threads/{thread_id}/approve      → approve/reject HITL recommendation
  GET  /health                           → liveness probe
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
import traceback
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

log = logging.getLogger("chichomz")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# ── Build graph with in-memory checkpointer ───────────────────────────────────
from agent import build_graph, LLM_MODEL, LLM_ANALYTICAL_MODEL  # noqa: E402

log.info(f"LLM model: {LLM_MODEL}")
log.info(f"LLM analytical model: {LLM_ANALYTICAL_MODEL}")

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
        pending_nodes = saved.next if saved.next else []
        is_resuming_clarify = "clarify" in pending_nodes
        is_resuming_hitl = "human_review_checkpoint" in pending_nodes
        is_first_turn = not bool(saved.values.get("messages"))
    except Exception:
        is_resuming_clarify = False
        is_resuming_hitl = False
        is_first_turn = True

    if is_resuming_clarify:
        graph_input: Any = Command(resume=raw_query)
    elif is_resuming_hitl:
        # Resume HITL with approval decision
        approval = inp.get("approval", raw_query)
        graph_input = Command(resume=approval)
    elif is_first_turn:
        graph_input = {
            "messages": messages,
            "raw_query": raw_query,
            "customer_profile": {},
            "intent_analysis": {},
            "retrieved_products": [],
            "reranked_products": [],
            "ranked_products": [],
            "cart": [],
            "awaiting_human_approval": False,
            "human_feedback": "",
            "confidence_score": 0.0,
            "response_draft": "",
            "needs_clarification": False,
            "clarification_question": "",
            "turn_count": 0,
            "interrupt_triggered": False,
            "matched_product_types": [],
            "enriched_query": "",
            "metadata_filter": {},
        }
    else:
        graph_input = {
            "messages": messages,
            "raw_query": raw_query,
        }

    # ── Stream graph ─────────────────────────────────────────────────────────
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()

    def _run() -> None:
        try:
            for chunk in _graph.stream(graph_input, config=config, stream_mode=["values", "messages"]):
                loop.call_soon_threadsafe(queue.put_nowait, chunk)
        except Exception as exc:
            log.error(f"Graph error: {exc}\n{traceback.format_exc()}")
            loop.call_soon_threadsafe(queue.put_nowait, {"__error__": str(exc)})
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, None)

    threading.Thread(target=_run, daemon=True).start()

    while True:
        item = await queue.get()
        if item is None:
            break

        # Manually injected error dict
        if isinstance(item, dict):
            if "__error__" in item:
                err_payload = {"messages": [{"type": "ai", "content": f"عذراً، حصل خطأ: {item['__error__']}"}]}
                yield f"data: {json.dumps(err_payload, ensure_ascii=False)}\n\n"
            continue

        # Normal chunk: (mode_str, data) tuple from stream_mode=["values","messages"]
        if not isinstance(item, tuple) or len(item) != 2:
            continue

        mode, data = item

        if mode == "messages":
            # Per-token event from an LLM call inside a node
            try:
                msg_chunk, metadata = data
                node = metadata.get("langgraph_node", "")
                content = getattr(msg_chunk, "content", "") or ""
                if node == "response_generator" and content:
                    yield f"data: {json.dumps({'__token__': content}, ensure_ascii=False)}\n\n"
            except Exception:
                pass

        elif mode == "values":
            chunk = data
            # Send progress hints based on which node just ran
            ser_chunk = _ser(chunk)

            # Detect node progress for UX status messages
            if chunk.get("intent_analysis") and not chunk.get("retrieved_products"):
                yield f"data: {json.dumps({'__progress__': 'بفهم طلبك... 🧠'}, ensure_ascii=False)}\n\n"
            elif chunk.get("enriched_query") and not chunk.get("retrieved_products"):
                yield f"data: {json.dumps({'__progress__': 'بحضّر البحث... 🔍'}, ensure_ascii=False)}\n\n"
            elif chunk.get("retrieved_products") and not chunk.get("reranked_products"):
                yield f"data: {json.dumps({'__progress__': 'بدور على أحسن المنتجات... 🛋️'}, ensure_ascii=False)}\n\n"
            elif chunk.get("reranked_products") and not chunk.get("response_draft"):
                yield f"data: {json.dumps({'__progress__': 'بختار لك الأنسب... ✨'}, ensure_ascii=False)}\n\n"
            elif chunk.get("response_draft") and not chunk.get("awaiting_human_approval"):
                yield f"data: {json.dumps({'__progress__': 'بجهّز الرد... ✍️'}, ensure_ascii=False)}\n\n"

            yield f"data: {json.dumps(ser_chunk, ensure_ascii=False)}\n\n"

    # ── After stream: check for pending interrupts ───────────────────────────
    try:
        final = _graph.get_state(config)
        if final.next:
            if "clarify" in final.next:
                q = (
                    final.values.get("clarification_question")
                    or "ممكن تقولي أكتر عن اللي بتدور عليه؟"
                )
                synthetic = {
                    "messages": [{"type": "ai", "content": q}],
                    "__interrupt__": [{"value": q, "type": "clarify"}],
                }
                yield f"data: {json.dumps(synthetic, ensure_ascii=False)}\n\n"

            elif "human_review_checkpoint" in final.next:
                # HITL interrupt — extract dynamic checklist from interrupt payload
                state_values = final.values or {}
                products = state_values.get("reranked_products") or state_values.get("ranked_products", [])
                response_draft = state_values.get("response_draft", "")
                matched_types = state_values.get("matched_product_types", [])
                confidence = state_values.get("confidence_score", 0.0)

                product_cards = []
                for p in products[:4]:
                    if not isinstance(p, dict):
                        continue
                    product_cards.append({
                        "clean_title": p.get("clean_title") or p.get("title", ""),
                        "product_type": p.get("product_type", ""),
                        "price": p.get("price", 0),
                        "compare_at_price": p.get("compare_at_price") or p.get("compare_price", 0),
                        "discount_pct": p.get("discount_pct", 0),
                        "cover": p.get("cover", ""),
                        "url": p.get("url", ""),
                        "vendor": p.get("vendor", ""),
                        "text": (p.get("text", "") or "")[:300],
                        "dimensions": p.get("dimensions", ""),
                        "score": p.get("score", 0),
                        "sales_angle": p.get("sales_angle", ""),
                    })

                # Get dynamic checklist from the interrupt payload in state
                dynamic_checklist = []
                auto_approved = True
                summary_note = ""
                try:
                    tasks = final.tasks or []
                    for task in tasks:
                        interrupts = getattr(task, 'interrupts', []) or []
                        for intr in interrupts:
                            val = getattr(intr, 'value', None) or {}
                            if isinstance(val, dict) and 'checklist' in val:
                                dynamic_checklist = val.get('checklist', [])
                                auto_approved = val.get('auto_approved', True)
                                summary_note = val.get('summary_note', '')
                                break
                except Exception:
                    pass

                hitl_payload = {
                    "__interrupt__": [{
                        "type": "human_review",
                        "value": {
                            "response_preview": response_draft[:500],
                            "products": product_cards,
                            "matched_types": matched_types,
                            "confidence_score": confidence,
                            "auto_approved": auto_approved,
                            "summary_note": summary_note,
                            "checklist": dynamic_checklist,
                        },
                    }],
                    "awaiting_human_approval": True,
                }
                yield f"data: {json.dumps(hitl_payload, ensure_ascii=False)}\n\n"
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


@app.post("/threads/{thread_id}/approve")
async def approve_recommendation(thread_id: str, request: Request):
    """
    Dedicated endpoint for HITL approval/rejection.
    Body: { "approved": true/false, "reason": "optional rejection reason" }
    """
    if thread_id not in _threads:
        raise HTTPException(status_code=404, detail="Thread not found")

    body = await request.json()
    approved = body.get("approved", True)
    reason = body.get("reason", "")

    if approved:
        approval_input = {"approved": True}
    else:
        approval_input = {"approved": False, "reason": reason}

    # Stream the resumed graph
    resume_body = {
        "input": {
            "approval": approval_input,
            "messages": [],
            "raw_query": "",
        }
    }

    return StreamingResponse(
        _sse_stream(thread_id, resume_body),
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
