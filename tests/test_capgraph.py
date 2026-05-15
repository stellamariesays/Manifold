"""Tests for capability graph."""

from manifold.capgraph import CapabilityGraph


def _make_graph() -> CapabilityGraph:
    g = CapabilityGraph()
    g.add_capability("a@hub", "trading")
    g.add_capability("a@hub", "analysis")
    g.add_capability("b@hub", "analysis")
    g.add_capability("b@hub", "risk-scoring")
    g.add_capability("c@hub", "risk-scoring")
    g.add_capability("c@hub", "compliance")
    g.add_relation("trading", "analysis")
    g.add_relation("analysis", "risk-scoring")
    g.add_relation("risk-scoring", "compliance")
    return g


def test_add_capability():
    g = CapabilityGraph()
    g.add_capability("a@hub", "trading")
    assert g.get_providers("trading") == ["a@hub"]
    assert g.get_agent_capabilities("a@hub") == ["trading"]


def test_get_providers():
    g = _make_graph()
    assert set(g.get_providers("analysis")) == {"a@hub", "b@hub"}


def test_find_path_direct():
    g = _make_graph()
    path = g.find_path("trading", "analysis")
    assert path == ["trading", "analysis"]


def test_find_path_multi_hop():
    g = _make_graph()
    path = g.find_path("trading", "compliance")
    assert len(path) >= 3
    assert path[0] == "trading"
    assert path[-1] == "compliance"


def test_find_path_none():
    g = _make_graph()
    assert g.find_path("trading", "cooking") == []


def test_get_reachable():
    g = _make_graph()
    reachable = g.get_reachable("a@hub")
    assert "trading" in reachable
    assert "analysis" in reachable
    assert "risk-scoring" in reachable


def test_shortest_path_direct_overlap():
    g = CapabilityGraph()
    g.add_capability("a@hub", "trading")
    g.add_capability("a@hub", "analysis")
    g.add_capability("b@hub", "analysis")
    path = g.shortest_path("a@hub", "b@hub")
    assert path == ["a@hub", "b@hub"]


def test_shortest_path_multi_hop():
    g = _make_graph()
    path = g.shortest_path("a@hub", "c@hub")
    assert len(path) >= 2
    assert path[0] == "a@hub"
    assert path[-1] == "c@hub"


def test_shortest_path_none():
    g = CapabilityGraph()
    g.add_capability("a@hub", "trading")
    g.add_capability("b@hub", "cooking")
    assert g.shortest_path("a@hub", "b@hub") == []


def test_subgraph():
    g = _make_graph()
    sub = g.subgraph({"trading", "analysis"})
    assert sub.capability_count == 2
    assert "a@hub" in sub.get_providers("trading")


def test_serialization():
    g = _make_graph()
    d = g.to_dict()
    g2 = CapabilityGraph.from_dict(d)
    assert g2.get_providers("trading") == ["a@hub"]
    assert g2.agent_count == g.agent_count


def test_counts():
    g = _make_graph()
    assert g.agent_count == 3
    assert g.capability_count == 4


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
