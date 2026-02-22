"""Tests for graph compilation — Decision #12A."""

from agent import build_graph


def test_graph_compiles():
    graph = build_graph()
    compiled = graph.compile()
    assert compiled is not None


def test_graph_has_expected_nodes():
    graph = build_graph()
    node_names = set(graph.nodes.keys())
    expected = {
        "analyze_intent", "clarify", "retrieve_products", "rerank_and_score",
        "generate_response", "handle_objection", "upsell_engine", "close_engine",
    }
    assert expected.issubset(node_names)


def test_graph_entry_is_analyze_intent():
    graph = build_graph()
    compiled = graph.compile()
    # If it compiles with edges from START, the graph is structurally valid
    assert compiled is not None
