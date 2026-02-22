"""
╔══════════════════════════════════════════════════════════════════════════════╗
║         CHIC HOMZ  —  AGENTIC SALES GRAPH  (LangGraph + agent-chat-ui)     ║
║         Arabic sales agent · 11,939 products · Human-in-loop               ║
╚══════════════════════════════════════════════════════════════════════════════╝

Graph topology:
  START
    └─▶ analyze_intent
          ├─▶ [needs_clarification]  ──▶ clarify (INTERRUPT) ──▶ analyze_intent
          └─▶ retrieve_products
                └─▶ rerank_and_score
                      ├─▶ [phase=objection]  ──▶ handle_objection ──▶ END
                      ├─▶ [phase=upsell]     ──▶ upsell_engine    ──▶ END
                      ├─▶ [phase=closing]    ──▶ close_engine      ──▶ END
                      └─▶ [default]          ──▶ generate_response ──▶ END
"""

from __future__ import annotations

import json
import os
from typing import Literal

from dotenv import load_dotenv
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from state import AgentState
from tools import search_products, TOP_K_RETRIEVE
from agent_prompts import (
    MASTER_SYSTEM_PROMPT,
    INTENT_ANALYSIS_PROMPT,
    RERANKING_PROMPT,
    OBJECTION_PROMPT,
    UPSELL_PROMPT,
    CLOSING_PROMPT,
)
from utils import parse_llm_json

load_dotenv()

# ──────────────────────────────────────────────────────────────────────────────
# CONFIGURATION
# ──────────────────────────────────────────────────────────────────────────────

TOP_K_PRESENT = 3
LLM_MODEL = os.getenv("LLM_MODEL", "upstage/solar-pro-3:free")
LLM_ANALYTICAL_MODEL = os.getenv("LLM_ANALYTICAL_MODEL", "upstage/solar-pro-3:free")

_openrouter_key = os.getenv("OPENROUTER_API_KEY", "")
_openrouter_base = "https://openrouter.ai/api/v1"

llm = ChatOpenAI(
    model=LLM_MODEL,
    openai_api_key=_openrouter_key,
    openai_api_base=_openrouter_base,
    temperature=0.3,
    max_tokens=1024,
)

llm_analytical = ChatOpenAI(
    model=LLM_ANALYTICAL_MODEL,
    openai_api_key=_openrouter_key,
    openai_api_base=_openrouter_base,
    temperature=0.0,
    max_tokens=1024,
)


# ──────────────────────────────────────────────────────────────────────────────
# INTENT ANALYSIS FALLBACK
# ──────────────────────────────────────────────────────────────────────────────

_INTENT_FALLBACK = {
    "detected_language": "ar",
    "primary_intent": "search",
    "emotional_state": "neutral",
    "urgency": "medium",
    "budget_signals": {"price_sensitive": False, "implicit_range": [0, 99999]},
    "product_context": {
        "room_type": "unknown",
        "color_signals": [],
        "style": "unknown",
    },
    "occasion": "undefined",
    "search_query_optimized": "",
    "needs_clarification": False,
    "clarification_question_ar": None,
    "conversation_phase": "discovery",
}


# ──────────────────────────────────────────────────────────────────────────────
# NODE FUNCTIONS
# ──────────────────────────────────────────────────────────────────────────────


def _extract_text(content) -> str:
    """Safely extract a plain string from a message content (str or list of blocks)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
        return " ".join(parts)
    return str(content)


def _as_dict(value, fallback: dict | None = None) -> dict:
    """Return value if it's a dict, else fallback (or empty dict)."""
    if isinstance(value, dict):
        return value
    return fallback.copy() if fallback is not None else {}


def analyze_intent(state: AgentState) -> dict:
    """Deep NLU: emotion, budget, color, style, urgency, conversation phase."""
    last_message = state["messages"][-1]
    query = _extract_text(
        last_message.content if hasattr(last_message, "content") else last_message
    )

    # Build history summary (last 3 turns = 6 messages)
    history = state["messages"][:-1][-6:]
    history_summary = (
        " | ".join(
            f"{'Customer' if isinstance(m, HumanMessage) else 'Agent'}: {_extract_text(m.content)[:100]}"
            for m in history
        )
        or "First message"
    )

    prompt = INTENT_ANALYSIS_PROMPT.format(
        query=query,
        history_summary=history_summary,
        current_profile=json.dumps(
            state.get("customer_profile", {}), ensure_ascii=False
        ),
    )

    response = llm_analytical.invoke([HumanMessage(content=prompt)])

    fallback = {**_INTENT_FALLBACK, "search_query_optimized": query}
    analysis = parse_llm_json(response.content, fallback)

    # Ensure analysis is a dict (if LLM returned a list, take first item)
    if isinstance(analysis, list):
        if analysis and isinstance(analysis[0], dict):
            analysis = analysis[0]
        else:
            analysis = fallback
    if not isinstance(analysis, dict):
        analysis = fallback

    # Update customer profile incrementally (never overwrite with unknown)
    profile = dict(_as_dict(state.get("customer_profile", {})))
    pc = analysis.get("product_context", {})
    if not isinstance(pc, dict):
        pc = {}

    if pc.get("room_type") and pc["room_type"] != "unknown":
        profile["room_type"] = pc["room_type"]
    if pc.get("style") and pc["style"] != "unknown":
        profile["style_preference"] = pc["style"]
    if pc.get("color_signals"):
        existing = set(profile.get("color_signals", []))
        profile["color_signals"] = list(existing | set(pc["color_signals"]))
    if analysis.get("emotional_state") and analysis["emotional_state"] != "neutral":
        profile["emotional_state"] = analysis["emotional_state"]
    if analysis.get("urgency") and analysis["urgency"] != "low":
        profile["urgency"] = analysis["urgency"]
    if analysis.get("occasion") and analysis["occasion"] != "undefined":
        profile["occasion"] = analysis["occasion"]
    if analysis.get("budget_signals", {}).get("implicit_range"):
        profile["budget_range_egp"] = analysis["budget_signals"]["implicit_range"]

    profile["conversation_phase"] = analysis.get("conversation_phase", "discovery")
    profile.setdefault("products_shown", [])
    profile.setdefault("objections_raised", [])

    return {
        "raw_query": query,
        "intent_analysis": analysis,
        "customer_profile": profile,
        "needs_clarification": (
            analysis.get("needs_clarification", False)
            and state.get("turn_count", 0) == 0
        ),
        "clarification_question": analysis.get("clarification_question_ar", ""),
        "turn_count": state.get("turn_count", 0) + 1,
    }


def clarify(state: AgentState) -> dict:
    """Human-in-the-loop interrupt — surfaces one targeted question."""
    question = state.get(
        "clarification_question",
        "ممكن تقولي أكتر — بتدور على إيه بالظبط؟",
    )
    user_response = interrupt(question)
    return {
        "messages": [
            AIMessage(content=question),
            HumanMessage(content=user_response),
        ],
        "needs_clarification": False,
        "interrupt_triggered": True,
    }


def retrieve_products(state: AgentState) -> dict:
    """Vector search with intent-aware query enrichment and budget filtering."""
    analysis = _as_dict(state.get("intent_analysis", {}))
    profile = _as_dict(state.get("customer_profile", {}))

    search_query = analysis.get("search_query_optimized") or state["raw_query"]
    filters = {}
    
    budget = profile.get("budget_range_egp", [0, 99999])
    if not isinstance(budget, list) or len(budget) != 2:
        budget = [0, 99999]

    if budget[1] < 99999:
        filters["price_max"] = budget[1]
    if budget[0] > 0:
        filters["price_min"] = budget[0]

    # Augment query with color signals for better retrieval
    color_boost = " ".join(profile.get("color_signals", []))
    if color_boost:
        search_query = f"{search_query} {color_boost}"

    products = search_products.invoke(
        {"query": search_query, "filters": filters if filters else None, "top_k": TOP_K_RETRIEVE}
    )

    # Filter out already-shown products to avoid repetition
    shown = set(str(pid) for pid in profile.get("products_shown", []))
    products = [p for p in products if str(p.get("id")) not in shown]

    return {"retrieved_products": products}


def rerank_and_score(state: AgentState) -> dict:
    """LLM-powered re-ranking: color harmony, occasion fit, emotional state."""
    profile = _as_dict(state.get("customer_profile", {}))
    products = state["retrieved_products"][:20]  # limit for LLM context

    if not products:
        return {"ranked_products": []}

    prompt = RERANKING_PROMPT.format(
        customer_profile_json=json.dumps(profile, ensure_ascii=False, indent=2),
        products_json=json.dumps(products, ensure_ascii=False, indent=2),
        top_k=TOP_K_PRESENT,
    )

    response = llm_analytical.invoke([HumanMessage(content=prompt)])

    fallback_ranked = [
        {"id": p["id"], "score": 80, "sales_angle": "", "potential_objection": "none"}
        for p in products[:TOP_K_PRESENT]
    ]
    ranked_ids = parse_llm_json(response.content, fallback_ranked)
    if isinstance(ranked_ids, dict):
        ranked_ids = [ranked_ids]

    # Merge scores with full product data
    product_map = {str(p["id"]): p for p in products if isinstance(p, dict)}
    ranked = []
    for item in (ranked_ids or fallback_ranked)[:TOP_K_PRESENT]:
        if not isinstance(item, dict):
            continue
        pid = str(item.get("id", ""))
        if pid in product_map:
            ranked.append({**product_map[pid], **item})

    if not ranked:
        ranked = products[:TOP_K_PRESENT]

    # Track shown products
    profile_updated = dict(_as_dict(profile))
    shown = set(str(pid) for pid in profile.get("products_shown", []))
    shown.update(str(p.get("id", "")) for p in ranked)
    profile_updated["products_shown"] = list(shown)

    return {"ranked_products": ranked, "customer_profile": profile_updated}


def generate_response(state: AgentState) -> dict:
    """Main sales response — discovery/presenting phase only."""
    profile = _as_dict(state.get("customer_profile", {}))
    products = state["ranked_products"]

    product_context = _build_product_context(products)
    phase = profile.get("conversation_phase", "discovery")

    user_prompt = f"""
المنتجات المرشحة لهذا العميل:
{product_context}

ملف العميل:
- الحالة العاطفية: {profile.get('emotional_state', 'neutral')}
- الإلحاح: {profile.get('urgency', 'medium')}
- نوع الغرفة: {profile.get('room_type', 'غير محدد')}
- الستايل: {profile.get('style_preference', 'غير محدد')}
- الألوان: {', '.join(profile.get('color_signals', [])) or 'غير محددة'}
- الميزانية المتوقعة: {profile.get('budget_range_egp', [0, 99999])} جنيه
- المناسبة: {profile.get('occasion', 'غير محددة')}
- مرحلة المحادثة: {phase}

رسالة العميل الأخيرة: {state['raw_query']}

قواعد للرد:
1. ابدأ بجملة انعكاس تثبت إنك فهمت
2. اعرض المنتجات باستخدام أسلوب القصة — مش قوائم مواصفات
3. اذكر الصور بشكل طبيعي
4. اختم بسؤال واحد يقرب من القرار
"""

    messages_to_send = [
        SystemMessage(content=MASTER_SYSTEM_PROMPT),
        *state["messages"][-8:],
        HumanMessage(content=user_prompt),
    ]

    response = llm.invoke(messages_to_send)

    return {
        "messages": [AIMessage(content=response.content)],
        "response_draft": response.content,
    }


def handle_objection(state: AgentState) -> dict:
    """Specialized objection handler — price, delivery, quality, trust."""
    products = state["ranked_products"]

    analysis = _as_dict(state.get("intent_analysis", {}))

    emotional = analysis.get("emotional_state", "neutral")
    raw = state["raw_query"]

    if emotional == "price_sensitive" or "غالي" in raw or "مش تمن" in raw:
        objection_type = "price"
    elif "تأخير" in raw or "توصيل" in raw:
        objection_type = "delivery"
    elif "جودة" in raw or "خامة" in raw:
        objection_type = "quality"
    else:
        objection_type = "general"

    profile = dict(_as_dict(state.get("customer_profile", {})))

    objections = set(profile.get("objections_raised", []))
    objections.add(objection_type)
    profile["objections_raised"] = list(objections)

    main_product = products[0] if products else {}
    alt_price_max = int(float(main_product.get("price", 99999)) * 0.7)

    alternatives = search_products.invoke(
        {"query": state["raw_query"], "filters": {"price_max": alt_price_max}, "top_k": 2}
    )

    prompt = OBJECTION_PROMPT.format(
        objection_type=objection_type,
        customer_message=state["raw_query"],
        product_json=json.dumps(main_product, ensure_ascii=False),
        alternatives_json=json.dumps(alternatives[:2], ensure_ascii=False),
    )

    response = llm.invoke([
        SystemMessage(content=MASTER_SYSTEM_PROMPT),
        HumanMessage(content=prompt),
    ])

    return {
        "messages": [AIMessage(content=response.content)],
        "customer_profile": profile,
    }


def upsell_engine(state: AgentState) -> dict:
    """Intelligent upsell — complementary products, never pushy."""
    products = state["ranked_products"]
    profile = _as_dict(state.get("customer_profile", {}))

    if not products:
        return {
            "messages": [
                AIMessage(
                    content="ممكن تقولي أكتر عن اللي بتدور عليه عشان أساعدك أحسن؟"
                )
            ],
        }

    confirmed = products[0]
    if not isinstance(confirmed, dict):
        confirmed = {}

    complement_query = (
        f"يتناسب مع {confirmed.get('product_type', '')} "
        f"{confirmed.get('title', '')} "
        f"{' '.join(profile.get('color_signals', []))}"
    )

    complements = search_products.invoke(
        {"query": complement_query, "filters": None, "top_k": 5}
    )

    shown = set(str(pid) for pid in profile.get("products_shown", []))
    complements = [
        p
        for p in complements
        if str(p.get("id")) not in shown
        and str(p.get("id")) != str(confirmed.get("id"))
    ]

    prompt = UPSELL_PROMPT.format(
        confirmed_product_json=json.dumps(confirmed, ensure_ascii=False),
        customer_profile_json=json.dumps(profile, ensure_ascii=False),
        complement_products_json=json.dumps(complements[:3], ensure_ascii=False),
    )

    response = llm.invoke([
        SystemMessage(content=MASTER_SYSTEM_PROMPT),
        HumanMessage(content=prompt),
    ])

    return {"messages": [AIMessage(content=response.content)]}


def close_engine(state: AgentState) -> dict:
    """Frictionless close — product URL + delivery + soft confirmation."""
    products = state["ranked_products"]
    analysis = _as_dict(state.get("intent_analysis", {}))

    intent = analysis.get("primary_intent", "")
    emotional = analysis.get("emotional_state", "")

    if intent == "purchase_ready":
        closing_signal = "العميل جاهز للشراء"
    elif emotional == "decided":
        closing_signal = "العميل اتخذ قراره"
    else:
        closing_signal = "العميل مهتم وسأل عن التفاصيل"

    prompt = CLOSING_PROMPT.format(
        products_json=json.dumps(products[:2], ensure_ascii=False),
        closing_signal=closing_signal,
    )

    response = llm.invoke([
        SystemMessage(content=MASTER_SYSTEM_PROMPT),
        HumanMessage(content=prompt),
    ])

    return {"messages": [AIMessage(content=response.content)]}


# ──────────────────────────────────────────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────────────────────────────────────────


def _build_product_context(products: list[dict]) -> str:
    if not products:
        return "لا توجد منتجات مطابقة — اقترح بديلاً أو اسأل عن تفاصيل أكثر."

    lines = []
    for i, p in enumerate(products, 1):
        if not isinstance(p, dict):
            continue
        discount_text = (
            f" (خصم {p.get('discount_pct', 0)}%)"
            if p.get("discount_pct", 0) > 0
            else ""
        )
        lines.append(
            f"منتج {i}: {p.get('title', '')}\n"
            f"- السعر: {p.get('price', '')} جنيه{discount_text}\n"
            f"- الرابط: {p.get('url', '')}\n"
            f"- الصورة: {p.get('cover', '')}\n"
            f"- الوصف: {p.get('text', '')[:300]}\n"
            f"- زاوية البيع: {p.get('sales_angle', '')}\n"
            f"- اعتراض محتمل: {p.get('potential_objection', 'none')}"
        )
    return "\n\n".join(lines)


# ──────────────────────────────────────────────────────────────────────────────
# ROUTING LOGIC
# ──────────────────────────────────────────────────────────────────────────────


def route_after_intent(
    state: AgentState,
) -> Literal["clarify", "retrieve_products"]:
    """Route to clarification or directly to retrieval."""
    if state.get("needs_clarification") and not state.get("interrupt_triggered"):
        return "clarify"
    return "retrieve_products"


def route_after_rerank(
    state: AgentState,
) -> Literal["generate_response", "handle_objection", "upsell_engine", "close_engine"]:
    """Route to the correct phase-specific node after re-ranking."""
    profile = _as_dict(state.get("customer_profile", {}))
    analysis = _as_dict(state.get("intent_analysis", {}))
    phase = profile.get("conversation_phase", "discovery")
    intent = analysis.get("primary_intent", "")

    if phase == "objection" or intent == "objection":
        return "handle_objection"
    if phase == "upsell":
        return "upsell_engine"
    if phase == "closing" or intent == "purchase_ready":
        return "close_engine"
    return "generate_response"


# ──────────────────────────────────────────────────────────────────────────────
# GRAPH CONSTRUCTION
# ──────────────────────────────────────────────────────────────────────────────


def build_graph() -> StateGraph:
    graph = StateGraph(AgentState)

    # Nodes
    graph.add_node("analyze_intent", analyze_intent)
    graph.add_node("clarify", clarify)
    graph.add_node("retrieve_products", retrieve_products)
    graph.add_node("rerank_and_score", rerank_and_score)
    graph.add_node("generate_response", generate_response)
    graph.add_node("handle_objection", handle_objection)
    graph.add_node("upsell_engine", upsell_engine)
    graph.add_node("close_engine", close_engine)

    # Edges
    graph.add_edge(START, "analyze_intent")
    graph.add_conditional_edges(
        "analyze_intent",
        route_after_intent,
        {"clarify": "clarify", "retrieve_products": "retrieve_products"},
    )
    graph.add_edge("clarify", "analyze_intent")
    graph.add_edge("retrieve_products", "rerank_and_score")
    graph.add_conditional_edges(
        "rerank_and_score",
        route_after_rerank,
        {
            "generate_response": "generate_response",
            "handle_objection": "handle_objection",
            "upsell_engine": "upsell_engine",
            "close_engine": "close_engine",
        },
    )
    graph.add_edge("generate_response", END)
    graph.add_edge("handle_objection", END)
    graph.add_edge("upsell_engine", END)
    graph.add_edge("close_engine", END)

    return graph


# ──────────────────────────────────────────────────────────────────────────────
# COMPILED GRAPH  (the export that agent-chat-ui / langgraph dev consumes)
# ──────────────────────────────────────────────────────────────────────────────

# LangGraph API manages persistence automatically — no custom checkpointer needed.
graph = build_graph().compile(
    interrupt_before=["clarify"],
)


# ──────────────────────────────────────────────────────────────────────────────
# CLI TEST MODE
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uuid

    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    print("Chic Homz Sales Agent — CLI Test Mode")
    print("Type your message (or 'exit'):\n")

    while True:
        user_input = input("You: ").strip()
        if user_input.lower() == "exit":
            break

        initial_state = {
            "messages": [HumanMessage(content=user_input)],
            "customer_profile": {},
            "raw_query": user_input,
            "intent_analysis": {},
            "retrieved_products": [],
            "ranked_products": [],
            "response_draft": "",
            "needs_clarification": False,
            "clarification_question": "",
            "turn_count": 0,
            "interrupt_triggered": False,
        }

        for event in graph.stream(initial_state, config=config):
            for node_name, node_output in event.items():
                if "messages" in node_output:
                    last = node_output["messages"][-1]
                    if isinstance(last, AIMessage):
                        print(f"\nنور: {last.content}\n")
