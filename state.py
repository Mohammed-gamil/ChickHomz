"""State schema for the Chic Homz sales agent graph."""

from __future__ import annotations

from typing import Annotated
from typing_extensions import TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class CustomerProfile(TypedDict, total=False):
    """Built incrementally across the conversation."""

    detected_language: str       # "ar" | "en" | "mixed"
    emotional_state: str         # curious / excited / hesitant / price_sensitive / decided
    urgency: str                 # low / medium / high
    budget_range_egp: list       # [min, max] inferred from signals
    room_type: str               # bedroom / living_room / kitchen / etc.
    style_preference: str        # modern / classic / minimalist / boho / industrial
    color_signals: list[str]     # ["أبيض","رمادي"] extracted from query
    occasion: str                # wedding / new_home / renovation / gift / undefined
    objections_raised: list[str] # price / quality / delivery / trust
    products_shown: list[str]    # product IDs already presented
    conversation_phase: str      # discovery / presenting / objection / upsell / closing


class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    customer_profile: CustomerProfile
    raw_query: str
    intent_analysis: dict
    retrieved_products: list[dict]       # raw docs from retriever
    reranked_products: list[dict]        # top-3 after reranker
    ranked_products: list[dict]          # legacy compat — same as reranked_products
    cart: list[dict]                     # items user expressed purchase intent on
    awaiting_human_approval: bool        # True = HITL checkpoint active
    human_feedback: str                  # rejection reason from human reviewer
    confidence_score: float              # reranker confidence 0.0-1.0
    response_draft: str
    needs_clarification: bool
    clarification_question: str
    turn_count: int
    interrupt_triggered: bool
    matched_product_types: list[str]     # product_types detected from query
    enriched_query: str                  # semantically enriched query for vector search
    metadata_filter: dict                # metadata pre-filter for Pinecone
