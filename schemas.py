"""
Pydantic schemas for structured LLM output.
Replaces brittle regex JSON parsing in agent nodes.
"""

from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel, Field


# ── Intent Analysis ──────────────────────────────────────────────────────────

class BudgetSignals(BaseModel):
    explicit_egp: Optional[float] = None
    implicit_range: List[int] = Field(default_factory=lambda: [0, 99999])
    price_sensitive: bool = False


class ProductContext(BaseModel):
    room_type: str = "unknown"
    product_category: Optional[str] = None
    color_signals: List[str] = Field(default_factory=list)
    style: str = "unknown"
    size_signals: str = "unknown"


class IntentAnalysisOutput(BaseModel):
    """Full intent analysis extracted from a customer message."""
    detected_language: str = "ar"
    primary_intent: str = "search"
    emotional_state: str = "neutral"
    urgency: str = "medium"
    budget_signals: BudgetSignals = Field(default_factory=BudgetSignals)
    product_context: ProductContext = Field(default_factory=ProductContext)
    occasion: str = "undefined"
    search_query_optimized: str = ""
    needs_clarification: bool = False
    clarification_reason: Optional[str] = None
    clarification_question_ar: Optional[str] = None
    conversation_phase: str = "discovery"


# ── Query Enrichment ─────────────────────────────────────────────────────────

class QueryEnrichmentOutput(BaseModel):
    """Structured query enrichment — semantic query + metadata filter."""
    core_category_ar: str = Field(description="Core product category in Arabic, e.g. 'مرايا'")
    core_category_en: str = Field(description="Core product category in English, e.g. 'mirrors'")
    style_signals: List[str] = Field(default_factory=list, description="Style keywords: elegant, modern, luxury, etc.")
    spatial_context: Optional[str] = Field(None, description="Size/space context, e.g. '2-seater', 'small dining'")
    material_signals: List[str] = Field(default_factory=list, description="Material keywords: marble, wood, metal, etc.")
    semantic_query_ar: str = Field(description="Enriched Arabic query for vector similarity on text field")
    semantic_query_hybrid: str = Field(description="Combined Arabic+English hybrid query for vector store")
    product_type_filter: List[str] = Field(default_factory=list, description="Exact product_type values to filter on")
    sort_preference: Optional[str] = Field(None, description="'price_asc' | 'price_desc' | 'discount' | None")


# ── Reranking ────────────────────────────────────────────────────────────────

class ScoreBreakdown(BaseModel):
    relevance: int = 0
    color_style: int = 0
    price_fit: int = 0
    room_match: int = 0
    occasion: int = 0


class RankedProductOutput(BaseModel):
    """A single ranked product with scoring metadata."""
    id: str
    score: int = Field(default=80, ge=0, le=100)
    score_breakdown: ScoreBreakdown = Field(default_factory=ScoreBreakdown)
    sales_angle: str = ""
    potential_objection: str = "none"


class RankedProductsList(BaseModel):
    """Wrapper list — required so with_structured_output works reliably."""
    items: List[RankedProductOutput]


# ── HITL Checklist ───────────────────────────────────────────────────────────

class HITLChecklistItem(BaseModel):
    """A single dynamically-generated checklist item."""
    label: str = Field(description="Short description of what is being checked")
    passed: bool = Field(description="Whether this check passed")
    detail: str = Field(default="", description="Brief explanation of the result")


class HITLChecklist(BaseModel):
    """Dynamically-generated HITL checklist — items vary per query."""
    items: list[HITLChecklistItem] = Field(description="List of checklist items relevant to this specific query")
    overall_pass: bool = Field(description="True if the recommendation is good enough to send to the customer")
    summary_note: str = Field(default="", description="One-line summary for the human reviewer")

    @property
    def all_passed(self) -> bool:
        return self.overall_pass

    @property
    def summary(self) -> str:
        lines = []
        for item in self.items:
            icon = "☑" if item.passed else "☐"
            line = f"{icon} {item.label}"
            if item.detail:
                line += f" — {item.detail}"
            lines.append(line)
        if self.summary_note:
            lines.append(f"\n📝 {self.summary_note}")
        return "\n".join(lines)
