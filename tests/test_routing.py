"""Tests for routing functions — Decision #10A."""

from agent import route_after_intent, route_after_rerank


# ── route_after_intent ───────────────────────────────────────────────────────


def test_route_clarification_needed():
    state = {"needs_clarification": True, "interrupt_triggered": False}
    assert route_after_intent(state) == "clarify"


def test_route_no_clarification():
    state = {"needs_clarification": False, "interrupt_triggered": False}
    assert route_after_intent(state) == "retrieve_products"


def test_route_clarification_already_triggered():
    state = {"needs_clarification": True, "interrupt_triggered": True}
    assert route_after_intent(state) == "retrieve_products"


def test_route_missing_keys_defaults_to_retrieve():
    state = {}
    assert route_after_intent(state) == "retrieve_products"


# ── route_after_rerank ───────────────────────────────────────────────────────


def test_route_objection_phase():
    state = {"customer_profile": {"conversation_phase": "objection"}, "intent_analysis": {}}
    assert route_after_rerank(state) == "handle_objection"


def test_route_objection_intent():
    state = {
        "customer_profile": {"conversation_phase": "discovery"},
        "intent_analysis": {"primary_intent": "objection"},
    }
    assert route_after_rerank(state) == "handle_objection"


def test_route_upsell():
    state = {"customer_profile": {"conversation_phase": "upsell"}, "intent_analysis": {}}
    assert route_after_rerank(state) == "upsell_engine"


def test_route_closing_phase():
    state = {"customer_profile": {"conversation_phase": "closing"}, "intent_analysis": {}}
    assert route_after_rerank(state) == "close_engine"


def test_route_purchase_ready_intent():
    state = {
        "customer_profile": {"conversation_phase": "presenting"},
        "intent_analysis": {"primary_intent": "purchase_ready"},
    }
    assert route_after_rerank(state) == "close_engine"


def test_route_default_generate():
    state = {
        "customer_profile": {"conversation_phase": "discovery"},
        "intent_analysis": {"primary_intent": "search"},
    }
    assert route_after_rerank(state) == "generate_response"


def test_route_empty_state():
    state = {"customer_profile": {}, "intent_analysis": {}}
    assert route_after_rerank(state) == "generate_response"
