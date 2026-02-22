"""
╔══════════════════════════════════════════════════════════════════════════════╗
║         CHIC HOMZ  —  AGENTIC SALES GRAPH  (LangGraph 2026)               ║
║         Arabic sales agent · 11,939 products · Human-in-loop              ║
╚══════════════════════════════════════════════════════════════════════════════╝

Graph topology:
  START
    └─▶ intent_classifier
          ├─▶ [needs_clarification]  ──▶ clarify (INTERRUPT) ──▶ intent_classifier
          └─▶ query_enricher
                └─▶ retriever
                      └─▶ reranker
                            └─▶ response_generator
                                  └─▶ human_review_checkpoint (INTERRUPT)
                                        ├─▶ [approved]  ──▶ final_response ──▶ END
                                        └─▶ [rejected]  ──▶ retriever (retry with corrected query)
"""

from __future__ import annotations

import json
import logging
import os
from typing import Literal

from dotenv import load_dotenv
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from llm_utility import create_llm
from schemas import (
    IntentAnalysisOutput,
    QueryEnrichmentOutput,
    RankedProductsList,
    HITLChecklist,
)
from state import AgentState
from tools import search_products, search_products_with_metadata_filter, TOP_K_RETRIEVE
from product_search import get_catalog, classify_query_to_types
from agent_prompts import (
    MASTER_SYSTEM_PROMPT,
    INTENT_ANALYSIS_PROMPT,
    QUERY_ENRICHMENT_PROMPT,
    RERANKING_PROMPT,
    RESPONSE_GENERATION_PROMPT,
    OBJECTION_PROMPT,
    UPSELL_PROMPT,
    CLOSING_PROMPT,
    HITL_CHECKLIST_PROMPT,
)

_log = logging.getLogger(__name__)

load_dotenv()

# ──────────────────────────────────────────────────────────────────────────────
# CONFIGURATION
# ──────────────────────────────────────────────────────────────────────────────

TOP_K_PRESENT = 3
LLM_MODEL = os.getenv("LLM_MODEL", "meta-llama/llama-3.3-70b-instruct:free")
LLM_ANALYTICAL_MODEL = os.getenv("LLM_ANALYTICAL_MODEL", "meta-llama/llama-3.3-70b-instruct:free")

# Lazy singletons
_llm = None
_llm_analytical = None
_structured_intent = None
_structured_enrichment = None
_structured_rerank = None
_structured_hitl = None


def _get_llm():
    global _llm
    if _llm is None:
        _llm = create_llm(temperature=0.3, max_tokens=1024)
    return _llm


def _get_llm_analytical():
    global _llm_analytical
    if _llm_analytical is None:
        _llm_analytical = create_llm(temperature=0.0, max_tokens=1024)
    return _llm_analytical


def _get_structured_intent():
    global _structured_intent
    if _structured_intent is None:
        _structured_intent = _get_llm_analytical().with_structured_output(IntentAnalysisOutput)
    return _structured_intent


def _get_structured_enrichment():
    global _structured_enrichment
    if _structured_enrichment is None:
        _structured_enrichment = _get_llm_analytical().with_structured_output(QueryEnrichmentOutput)
    return _structured_enrichment


def _get_structured_rerank():
    global _structured_rerank
    if _structured_rerank is None:
        _structured_rerank = _get_llm_analytical().with_structured_output(RankedProductsList)
    return _structured_rerank


def _get_structured_hitl():
    global _structured_hitl
    if _structured_hitl is None:
        _structured_hitl = _get_llm_analytical().with_structured_output(HITLChecklist)
    return _structured_hitl


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
# HELPERS
# ──────────────────────────────────────────────────────────────────────────────


def _extract_text(content) -> str:
    """Safely extract a plain string from a message content."""
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
    if isinstance(value, dict):
        return value
    return fallback.copy() if fallback is not None else {}


def _build_product_cards(products: list[dict]) -> str:
    """Build structured product card text for the LLM response generator."""
    if not products:
        return "لا توجد منتجات مطابقة."

    lines = []
    for i, p in enumerate(products, 1):
        if not isinstance(p, dict):
            continue

        title = p.get("clean_title") or p.get("title", "")
        price = p.get("price", 0)
        compare = p.get("compare_at_price") or p.get("compare_price", 0)
        discount = p.get("discount_pct", 0)
        vendor = p.get("vendor", "")
        text = p.get("text", "")
        dimensions = p.get("dimensions", "")
        url = p.get("url", "")
        cover = p.get("cover", "")

        # Extract delivery info from text
        delivery = ""
        if "يوم عمل" in text:
            import re
            dm = re.search(r'(\d+[-–]\d+\s*يوم عمل)', text)
            if dm:
                delivery = dm.group(1)

        # Custom order detection
        custom_order = "يصنع خصيصًا" in text or "يُصنع بالطلب" in text

        price_text = f"{price:,.0f} ج.م"
        if discount > 0 and compare > 0:
            price_text = f"{price:,.0f} ج.م  ~~{compare:,.0f} ج.م~~  (خصم {discount}%)"

        lines.append(
            f"منتج {i}:\n"
            f"  الاسم: {title}\n"
            f"  الماركة: {vendor}\n"
            f"  السعر: {price_text}\n"
            f"  المقاسات: {dimensions or 'غير محدد'}\n"
            f"  التوصيل: {delivery or 'غير محدد'}\n"
            f"  يُصنع بالطلب: {'نعم' if custom_order else 'لا'}\n"
            f"  الوصف: {text[:400]}\n"
            f"  رابط المنتج (href فقط — لا تلصقه كتكست): {url}\n"
            f"  صورة المنتج (src فقط — لا تلصقها كتكست): {cover}\n"
            f"  زاوية البيع: {p.get('sales_angle', '')}\n"
            f"  اعتراض محتمل: {p.get('potential_objection', 'none')}"
        )
    return "\n\n".join(lines)


# ──────────────────────────────────────────────────────────────────────────────
# NODE 1: INTENT CLASSIFIER
# ──────────────────────────────────────────────────────────────────────────────


def intent_classifier(state: AgentState) -> dict:
    """Deep NLU: emotion, budget, color, style, urgency, conversation phase."""
    last_message = state["messages"][-1]
    query = _extract_text(
        last_message.content if hasattr(last_message, "content") else last_message
    )

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

    fallback = {**_INTENT_FALLBACK, "search_query_optimized": query}
    try:
        analysis_obj = _get_structured_intent().invoke([HumanMessage(content=prompt)])
        analysis = analysis_obj.model_dump()
    except Exception as exc:
        _log.warning("Structured intent analysis failed: %s — using fallback", exc)
        analysis = fallback

    # Update customer profile incrementally
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
            and not state.get("interrupt_triggered", False)
        ),
        "clarification_question": analysis.get("clarification_question_ar", ""),
        "turn_count": state.get("turn_count", 0) + 1,
    }


# ──────────────────────────────────────────────────────────────────────────────
# NODE 2: CLARIFY (INTERRUPT)
# ──────────────────────────────────────────────────────────────────────────────


def clarify(state: AgentState) -> dict:
    """Human-in-the-loop interrupt — surfaces one targeted clarification question.
    Maximum ONE clarifying question before retrieving."""
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


# ──────────────────────────────────────────────────────────────────────────────
# NODE 3: QUERY ENRICHER
# ──────────────────────────────────────────────────────────────────────────────


def query_enricher(state: AgentState) -> dict:
    """
    Enriches the user query by:
    a. Extracting core product category
    b. Extracting style/spatial/material signals
    c. Building semantic Arabic + English hybrid query
    d. Building metadata filter for product_type pre-filtering
    """
    analysis = _as_dict(state.get("intent_analysis", {}))
    pc = analysis.get("product_context", {})
    if not isinstance(pc, dict):
        pc = {}

    raw_query = state.get("raw_query", "")

    # First: use the deterministic classifier from product_search.py
    _, type_index = get_catalog()
    detected_types = classify_query_to_types(raw_query, type_index) if type_index else []

    # Then: try LLM enrichment for semantic query
    prompt = QUERY_ENRICHMENT_PROMPT.format(
        query=raw_query,
        product_category=pc.get("product_category", "unknown"),
        room_type=pc.get("room_type", "unknown"),
        style=pc.get("style", "unknown"),
        color_signals=", ".join(pc.get("color_signals", [])) or "none",
        size_signals=pc.get("size_signals", "unknown"),
    )

    try:
        enrichment = _get_structured_enrichment().invoke([HumanMessage(content=prompt)])
        enriched_query = enrichment.semantic_query_hybrid or enrichment.semantic_query_ar or raw_query
        llm_types = enrichment.product_type_filter or []

        # Merge deterministic + LLM-detected types (deterministic takes priority)
        all_types = list(dict.fromkeys(detected_types + llm_types))
        if type_index:
            all_types = [t for t in all_types if t in type_index]
        if not all_types:
            all_types = detected_types

    except Exception as exc:
        _log.warning("Query enrichment failed: %s — using basic query", exc)
        enriched_query = analysis.get("search_query_optimized") or raw_query
        all_types = detected_types

    # Remove types that the user explicitly excluded (e.g. "مش عايز كراسي")
    from product_search import _extract_negations, _NEGATION_TYPE_GROUPS
    excluded_types: set[str] = set()
    for negated_word in _extract_negations(raw_query):
        negated_lower = negated_word.strip().lower()
        for kw, types in _NEGATION_TYPE_GROUPS.items():
            if kw in negated_lower or negated_lower in kw:
                excluded_types.update(types)
    if excluded_types:
        all_types = [t for t in all_types if t not in excluded_types]
        _log.info("Excluded types based on user negation: %s", excluded_types)

    # Build metadata filter
    metadata_filter = {}
    if all_types:
        metadata_filter["product_type"] = {"$in": all_types}

    return {
        "enriched_query": enriched_query,
        "matched_product_types": all_types,
        "metadata_filter": metadata_filter,
    }


# ──────────────────────────────────────────────────────────────────────────────
# NODE 4: RETRIEVER
# ──────────────────────────────────────────────────────────────────────────────


def retriever(state: AgentState) -> dict:
    """
    Vector search with metadata pre-filter.
    Uses enriched query + product_type filter from query_enricher.
    Applies budget filters from customer profile.
    """
    profile = _as_dict(state.get("customer_profile", {}))
    enriched_query = state.get("enriched_query") or state.get("raw_query", "")
    matched_types = state.get("matched_product_types", [])

    # Build filters
    filters = {}
    if matched_types:
        filters["product_type"] = matched_types

    budget = profile.get("budget_range_egp", [0, 99999])
    if not isinstance(budget, list) or len(budget) != 2:
        budget = [0, 99999]
    if budget[1] < 99999:
        filters["price_max"] = budget[1]
    if budget[0] > 0:
        filters["price_min"] = budget[0]

    # Augment query with color signals
    color_boost = " ".join(profile.get("color_signals", []))
    if color_boost:
        enriched_query = f"{enriched_query} {color_boost}"

    # If human rejected previous results, append rejection reason as negative signal
    if state.get("human_feedback"):
        enriched_query = f"{enriched_query} (NOT: {state['human_feedback']})"

    products = search_products.invoke(
        {"query": enriched_query, "filters": filters if filters else None, "top_k": TOP_K_RETRIEVE}
    )

    # Filter out already-shown products
    shown = set(str(pid) for pid in profile.get("products_shown", []))
    products = [p for p in products if str(p.get("id")) not in shown]

    # Handle 0 results
    if not products:
        return {
            "retrieved_products": [],
            "confidence_score": 0.0,
        }

    return {"retrieved_products": products}


# ──────────────────────────────────────────────────────────────────────────────
# NODE 5: RERANKER
# ──────────────────────────────────────────────────────────────────────────────


def reranker(state: AgentState) -> dict:
    """
    LLM-powered re-ranking: relevance, color harmony, occasion fit.
    Uses Cross-Encoder style scoring via structured output.
    Keeps top-3, prioritizes: exact category > style > price range.
    """
    profile = _as_dict(state.get("customer_profile", {}))
    products = state.get("retrieved_products", [])[:20]

    if not products:
        return {
            "reranked_products": [],
            "ranked_products": [],
            "confidence_score": 0.0,
        }

    prompt = RERANKING_PROMPT.format(
        customer_profile_json=json.dumps(profile, ensure_ascii=False, indent=2),
        products_json=json.dumps(products[:10], ensure_ascii=False, indent=2),
        top_k=TOP_K_PRESENT,
    )

    fallback_ranked = [
        {"id": p["id"], "score": 80, "sales_angle": "", "potential_objection": "none"}
        for p in products[:TOP_K_PRESENT]
    ]

    try:
        result = _get_structured_rerank().invoke([HumanMessage(content=prompt)])
        ranked_ids = [r.model_dump() for r in result.items]
    except Exception as exc:
        _log.warning("Structured reranking failed: %s — using fallback", exc)
        ranked_ids = fallback_ranked

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

    # Calculate confidence score (average of top scores / 100)
    scores = [r.get("score", 0) for r in ranked if isinstance(r, dict)]
    confidence = sum(scores) / (len(scores) * 100) if scores else 0.0

    # Track shown products
    profile_updated = dict(_as_dict(profile))
    shown = set(str(pid) for pid in profile.get("products_shown", []))
    shown.update(str(p.get("id", "")) for p in ranked)
    profile_updated["products_shown"] = list(shown)

    return {
        "reranked_products": ranked,
        "ranked_products": ranked,
        "customer_profile": profile_updated,
        "confidence_score": confidence,
    }


# ──────────────────────────────────────────────────────────────────────────────
# NODE 6: RESPONSE GENERATOR
# ──────────────────────────────────────────────────────────────────────────────


def response_generator(state: AgentState) -> dict:
    """
    Generates the sales response using the approved product cards.
    Handles special phases: objection, upsell, closing.
    """
    profile = _as_dict(state.get("customer_profile", {}))
    analysis = _as_dict(state.get("intent_analysis", {}))
    products = state.get("reranked_products") or state.get("ranked_products", [])
    phase = profile.get("conversation_phase", "discovery")
    intent = analysis.get("primary_intent", "")

    # Handle 0 results
    if not products:
        no_result_msg = "معندناش حاجة بالظبط دلوقتي بتطابق اللي بتدور عليه. "
        no_result_msg += "ممكن توصفلي أكتر عشان ألاقيلك أقرب حاجة ليها؟"
        return {
            "messages": [AIMessage(content=no_result_msg)],
            "response_draft": no_result_msg,
            "awaiting_human_approval": False,
        }

    # Route to specialized handler based on phase
    if phase == "objection" or intent == "objection":
        return _handle_objection(state, products, profile)
    if phase == "upsell":
        return _handle_upsell(state, products, profile)
    if phase == "closing" or intent == "purchase_ready":
        return _handle_closing(state, products, profile, analysis)

    # Default: product recommendation response
    product_cards = _build_product_cards(products)

    prompt = RESPONSE_GENERATION_PROMPT.format(
        product_cards=product_cards,
        emotional_state=profile.get("emotional_state", "neutral"),
        urgency=profile.get("urgency", "medium"),
        room_type=profile.get("room_type", "غير محدد"),
        style=profile.get("style_preference", "غير محدد"),
        colors=", ".join(profile.get("color_signals", [])) or "غير محددة",
        budget=profile.get("budget_range_egp", [0, 99999]),
        occasion=profile.get("occasion", "غير محددة"),
        user_query=state["raw_query"],
    )

    messages_to_send = [
        SystemMessage(content=MASTER_SYSTEM_PROMPT),
        *state["messages"][-8:],
        HumanMessage(content=prompt),
    ]

    response = _get_llm().invoke(messages_to_send)
    content = response.content or "عذراً، مقدرتش أرد دلوقتي. جرب تاني."

    return {
        "response_draft": content,
        "awaiting_human_approval": True,
    }


def _handle_objection(state, products, profile):
    """Specialized objection handler."""
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

    profile_updated = dict(profile)
    objections = set(profile.get("objections_raised", []))
    objections.add(objection_type)
    profile_updated["objections_raised"] = list(objections)

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

    response = _get_llm().invoke([
        SystemMessage(content=MASTER_SYSTEM_PROMPT),
        HumanMessage(content=prompt),
    ])

    return {
        "messages": [AIMessage(content=response.content)],
        "response_draft": response.content,
        "customer_profile": profile_updated,
        "awaiting_human_approval": False,
    }


def _handle_upsell(state, products, profile):
    """Upsell handler."""
    confirmed = products[0] if products else {}
    if not isinstance(confirmed, dict):
        confirmed = {}

    complement_query = (
        f"يتناسب مع {confirmed.get('product_type', '')} "
        f"{confirmed.get('clean_title', '')} "
        f"{' '.join(profile.get('color_signals', []))}"
    )

    complements = search_products.invoke(
        {"query": complement_query, "filters": None, "top_k": 5}
    )

    shown = set(str(pid) for pid in profile.get("products_shown", []))
    complements = [
        p for p in complements
        if str(p.get("id")) not in shown and str(p.get("id")) != str(confirmed.get("id"))
    ]

    prompt = UPSELL_PROMPT.format(
        confirmed_product_json=json.dumps(confirmed, ensure_ascii=False),
        customer_profile_json=json.dumps(profile, ensure_ascii=False),
        complement_products_json=json.dumps(complements[:3], ensure_ascii=False),
    )

    response = _get_llm().invoke([
        SystemMessage(content=MASTER_SYSTEM_PROMPT),
        HumanMessage(content=prompt),
    ])

    return {
        "messages": [AIMessage(content=response.content)],
        "response_draft": response.content,
        "awaiting_human_approval": False,
    }


def _handle_closing(state, products, profile, analysis):
    """Closing handler."""
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

    response = _get_llm().invoke([
        SystemMessage(content=MASTER_SYSTEM_PROMPT),
        HumanMessage(content=prompt),
    ])

    return {
        "messages": [AIMessage(content=response.content)],
        "response_draft": response.content,
        "awaiting_human_approval": False,
    }


# ──────────────────────────────────────────────────────────────────────────────
# NODE 7: HUMAN REVIEW CHECKPOINT (HITL)
# ──────────────────────────────────────────────────────────────────────────────


def human_review_checkpoint(state: AgentState) -> dict:
    """
    HITL checkpoint — generates a DYNAMIC checklist per query via LLM,
    then pauses the graph for a single human approve/reject decision.

    No retry loop — reviewer sees the checklist once, decides to send or drop.
    """
    if not state.get("awaiting_human_approval"):
        # Skip HITL for non-recommendation responses (objections, upsell, closing)
        return {
            "messages": [AIMessage(content=state.get("response_draft", ""))],
            "awaiting_human_approval": False,
        }

    products = state.get("reranked_products") or state.get("ranked_products", [])
    matched_types = state.get("matched_product_types", [])
    response_draft = state.get("response_draft", "")

    # Generate dynamic checklist via LLM
    checklist_items = []
    auto_approved = True
    summary_note = ""
    try:
        hitl_prompt = HITL_CHECKLIST_PROMPT.format(
            user_query=state.get("raw_query", ""),
            matched_types=json.dumps(matched_types, ensure_ascii=False),
            products_json=json.dumps(products[:4], ensure_ascii=False, indent=2),
            response_draft=response_draft[:1000],
        )
        checklist = _get_structured_hitl().invoke([HumanMessage(content=hitl_prompt)])
        auto_approved = checklist.all_passed
        summary_note = checklist.summary_note
        checklist_items = [
            {"label": item.label, "passed": item.passed, "detail": item.detail}
            for item in checklist.items
        ]
    except Exception as exc:
        _log.warning("HITL auto-evaluation failed: %s — defaulting to approve", exc)
        auto_approved = True
        checklist_items = [{"label": "Auto-evaluation unavailable", "passed": True, "detail": ""}]

    # Build interrupt payload with dynamic checklist
    interrupt_payload = {
        "type": "recommendation_review",
        "checklist": checklist_items,
        "auto_approved": auto_approved,
        "summary_note": summary_note,
        "products_count": len(products),
        "matched_types": matched_types,
        "response_preview": response_draft[:500],
        "products": [
            {
                "clean_title": p.get("clean_title") or p.get("title", ""),
                "product_type": p.get("product_type", ""),
                "price": p.get("price", 0),
                "discount_pct": p.get("discount_pct", 0),
                "score": p.get("score", 0),
            }
            for p in products[:4]
        ],
    }

    # Trigger interrupt — human sees checklist, decides once
    human_decision = interrupt(interrupt_payload)

    # Parse human decision
    if isinstance(human_decision, str):
        decision_lower = human_decision.lower().strip()
        approved = decision_lower in ("approve", "approved", "yes", "ok", "✅", "true", "1")
    elif isinstance(human_decision, dict):
        approved = human_decision.get("approved", False)
    else:
        approved = bool(human_decision)

    if approved:
        # Send the response to the customer
        return {
            "messages": [AIMessage(content=response_draft)],
            "awaiting_human_approval": False,
            "human_feedback": "",
        }
    else:
        # Rejected — drop this response, tell customer we're looking for better options
        drop_msg = "لحظة واحدة، بدور لك على حاجات أفضل تناسبك أكتر... 🔍"
        return {
            "messages": [AIMessage(content=drop_msg)],
            "awaiting_human_approval": False,
            "human_feedback": "",
        }


# ──────────────────────────────────────────────────────────────────────────────
# NODE 8: FINAL RESPONSE (no-op pass-through)
# ──────────────────────────────────────────────────────────────────────────────


def final_response(state: AgentState) -> dict:
    """Pass-through — the response was already added to messages by human_review_checkpoint."""
    return {}


# ──────────────────────────────────────────────────────────────────────────────
# ROUTING LOGIC
# ──────────────────────────────────────────────────────────────────────────────


def route_after_intent(
    state: AgentState,
) -> Literal["clarify", "query_enricher"]:
    """Route to clarification or query enrichment."""
    if state.get("needs_clarification") and not state.get("interrupt_triggered"):
        return "clarify"
    return "query_enricher"


def route_after_hitl(
    state: AgentState,
) -> Literal["final_response"]:
    """Route after HITL: always go to final_response (no retry loop)."""
    return "final_response"


# ──────────────────────────────────────────────────────────────────────────────
# GRAPH CONSTRUCTION
# ──────────────────────────────────────────────────────────────────────────────


def build_graph() -> StateGraph:
    graph = StateGraph(AgentState)

    # Nodes
    graph.add_node("intent_classifier", intent_classifier)
    graph.add_node("clarify", clarify)
    graph.add_node("query_enricher", query_enricher)
    graph.add_node("retriever", retriever)
    graph.add_node("reranker", reranker)
    graph.add_node("response_generator", response_generator)
    graph.add_node("human_review_checkpoint", human_review_checkpoint)
    graph.add_node("final_response", final_response)

    # Edges
    graph.add_edge(START, "intent_classifier")
    graph.add_conditional_edges(
        "intent_classifier",
        route_after_intent,
        {"clarify": "clarify", "query_enricher": "query_enricher"},
    )
    graph.add_edge("clarify", "intent_classifier")
    graph.add_edge("query_enricher", "retriever")
    graph.add_edge("retriever", "reranker")
    graph.add_edge("reranker", "response_generator")
    graph.add_edge("response_generator", "human_review_checkpoint")
    graph.add_edge("human_review_checkpoint", "final_response")
    graph.add_edge("final_response", END)

    return graph


# ──────────────────────────────────────────────────────────────────────────────
# COMPILED GRAPH
# ──────────────────────────────────────────────────────────────────────────────

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

        for event in graph.stream(initial_state, config=config):
            for node_name, node_output in event.items():
                if "messages" in node_output:
                    last = node_output["messages"][-1]
                    if isinstance(last, AIMessage):
                        print(f"\nنور: {last.content}\n")
