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
    retrieved_products: list[dict]
    ranked_products: list[dict]
    response_draft: str
    needs_clarification: bool
    clarification_question: str
    turn_count: int
    interrupt_triggered: bool
