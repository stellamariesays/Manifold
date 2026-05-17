"""Tests for manifold.capability_builder."""

import asyncio
import pytest
from unittest.mock import MagicMock

from manifold.capability_builder import (
    CapabilityBuilder,
    CapabilityStatus,
    CapSpec,
    InvocationResult,
)


def _make_agent(name: str = "test-agent", caps: list[str] | None = None):
    """Create a mock agent with the minimum interface."""
    agent = MagicMock()
    agent._name = name
    agent._capabilities = list(caps or [])
    agent.knows = MagicMock(side_effect=lambda c: agent._capabilities.extend(
        x for x in c if x not in agent._capabilities
    ))
    return agent


def _run(coro):
    return asyncio.run(coro)


class TestCapSpec:
    def test_defaults(self):
        spec = CapSpec(name="test-cap")
        assert spec.version == "1.0.0"
        assert spec.status == CapabilityStatus.ACTIVE
        assert spec.is_invocable is False  # no handler

    def test_is_invocable(self):
        async def handler(payload):
            return payload
        spec = CapSpec(name="cap", handler=handler)
        assert spec.is_invocable is True

    def test_is_invocable_when_disabled(self):
        async def handler(payload):
            return {}
        spec = CapSpec(name="cap", handler=handler, status=CapabilityStatus.DISABLED)
        assert spec.is_invocable is False

    def test_matches_tag(self):
        spec = CapSpec(name="solar-prediction", tags=["energy", "forecast"])
        assert spec.matches_tag("energy")
        assert spec.matches_tag("solar-prediction")
        assert not spec.matches_tag("bitcoin")

    def test_matches_any(self):
        spec = CapSpec(
            name="solar-prediction",
            description="Predicts solar energy output",
            tags=["energy"],
        )
        assert spec.matches_any("solar")
        assert spec.matches_any("predicts")
        assert spec.matches_any("energy")
        assert not spec.matches_any("bitcoin")

    def test_schema_summary(self):
        spec = CapSpec(
            name="solar-prediction",
            inputs=["region"],
            outputs=["predicted_mw"],
        )
        s = spec.schema_summary()
        assert "solar-prediction" in s
        assert "region" in s
        assert "predicted_mw" in s


class TestCapabilityBuilder:
    def test_define_decorator(self):
        agent = _make_agent()
        builder = CapabilityBuilder(agent)

        @builder.define(
            name="solar-prediction",
            inputs=["region"],
            outputs=["predicted_mw"],
            tags=["energy"],
        )
        async def solar_predict(payload):
            return {"predicted_mw": 42.0}

        assert builder.get("solar-prediction") is not None
        assert "solar-prediction" in agent._capabilities

    def test_register_imperative(self):
        agent = _make_agent()
        builder = CapabilityBuilder(agent)

        async def handler(payload):
            return {"result": True}

        spec = builder.register(
            name="test-cap",
            handler=handler,
            inputs=["data"],
            outputs=["result"],
        )
        assert spec.name == "test-cap"
        assert builder.get("test-cap") is spec

    def test_invoke_success(self):
        agent = _make_agent()
        builder = CapabilityBuilder(agent)

        @builder.define(name="echo", inputs=["msg"])
        async def echo(payload):
            return {"msg": payload["msg"]}

        result = _run(builder.invoke("echo", {"msg": "hello"}))
        assert result.ok
        assert result.output["msg"] == "hello"
        assert result.elapsed_ms >= 0

    def test_invoke_updates_stats(self):
        agent = _make_agent()
        builder = CapabilityBuilder(agent)

        @builder.define(name="echo")
        async def echo(payload):
            return {}

        _run(builder.invoke("echo", {}))
        _run(builder.invoke("echo", {}))

        spec = builder.get("echo")
        assert spec.invocation_count == 2
        assert spec.last_invoked_at is not None

    def test_invoke_unknown_capability(self):
        agent = _make_agent()
        builder = CapabilityBuilder(agent)

        result = _run(builder.invoke("nonexistent", {}))
        assert not result.ok
        assert "Unknown capability" in result.error

    def test_invoke_missing_inputs(self):
        agent = _make_agent()
        builder = CapabilityBuilder(agent)

        @builder.define(name="strict", inputs=["required_field"])
        async def strict(payload):
            return {}

        result = _run(builder.invoke("strict", {}))
        assert not result.ok
        assert "Missing required inputs" in result.error

    def test_invoke_skip_validation(self):
        agent = _make_agent()
        builder = CapabilityBuilder(agent)

        @builder.define(name="flex", inputs=["optional"])
        async def flex(payload):
            return {"ok": True}

        result = _run(builder.invoke("flex", {}, validate_inputs=False))
        assert result.ok

    def test_invoke_handler_error(self):
        agent = _make_agent()
        builder = CapabilityBuilder(agent)

        @builder.define(name="crashy")
        async def crashy(payload):
            raise ValueError("boom")

        result = _run(builder.invoke("crashy", {}))
        assert not result.ok
        assert "boom" in result.error

    def test_invoke_disabled(self):
        agent = _make_agent()
        builder = CapabilityBuilder(agent)

        async def handler(payload):
            return {}

        builder.register(name="cap", handler=handler)
        builder.disable("cap")

        result = _run(builder.invoke("cap", {}))
        assert not result.ok
        assert "not invocable" in result.error

    def test_deprecate(self):
        agent = _make_agent()
        builder = CapabilityBuilder(agent)

        async def handler(payload):
            return {}

        builder.register(name="old-cap", handler=handler)
        builder.deprecate("old-cap", replaced_by="new-cap")

        spec = builder.get("old-cap")
        assert spec.status == CapabilityStatus.DEPRECATED
        assert spec.deprecated_by == "new-cap"

    def test_enable_after_disable(self):
        agent = _make_agent()
        builder = CapabilityBuilder(agent)

        async def handler(payload):
            return {"ok": True}

        builder.register(name="toggle-cap", handler=handler)
        builder.disable("toggle-cap")
        assert not builder.get("toggle-cap").is_invocable

        builder.enable("toggle-cap")
        assert builder.get("toggle-cap").is_invocable

        result = _run(builder.invoke("toggle-cap", {}))
        assert result.ok

    def test_list_capabilities_filter(self):
        agent = _make_agent()
        builder = CapabilityBuilder(agent)

        async def h(payload):
            return {}

        builder.register(name="cap-a", handler=h, tags=["energy"])
        builder.register(name="cap-b", handler=h, tags=["nlp"])
        builder.deprecate("cap-a")

        active = builder.list_capabilities(status=CapabilityStatus.ACTIVE)
        assert len(active) == 1
        assert active[0].name == "cap-b"

        energy = builder.list_capabilities(tag="energy")
        assert len(energy) == 1

    def test_search(self):
        agent = _make_agent()
        builder = CapabilityBuilder(agent)

        async def noop(p): return {}
        builder.register(name="solar-prediction", handler=noop, description="solar energy forecasting", tags=["energy"])
        builder.register(name="wind-forecast", handler=noop, description="wind energy forecasting", tags=["energy"])
        builder.register(name="sentiment-analysis", handler=noop, description="text sentiment", tags=["nlp"])

        results = builder.search("energy")
        assert len(results) == 2

        results = builder.search("forecast")
        assert len(results) == 2

        results = builder.search("sentiment")
        assert len(results) == 1

    def test_stats(self):
        agent = _make_agent()
        builder = CapabilityBuilder(agent)

        @builder.define(name="cap-x")
        async def cap_x(payload):
            return {}

        @builder.define(name="cap-y")
        async def cap_y(payload):
            return {}

        _run(builder.invoke("cap-x", {}))

        stats = builder.stats()
        assert stats["total_capabilities"] == 2
        assert stats["active"] == 2
        assert stats["total_invocations"] == 1

    def test_catalog(self):
        agent = _make_agent()
        builder = CapabilityBuilder(agent)

        async def noop(p): return {}
        builder.register(
            name="test-cap",
            handler=noop,
            version="2.0.0",
            inputs=["data"],
            outputs=["result"],
            tags=["test"],
        )

        cat = builder.catalog()
        assert "test-cap" in cat
        assert cat["test-cap"]["version"] == "2.0.0"
        assert cat["test-cap"]["inputs"] == ["data"]

    def test_register_preserves_stats_on_upgrade(self):
        agent = _make_agent()
        builder = CapabilityBuilder(agent)

        async def v1(payload):
            return {"v": 1}

        async def v2(payload):
            return {"v": 2}

        builder.register(name="cap", handler=v1, version="1.0.0")
        _run(builder.invoke("cap", {}))
        _run(builder.invoke("cap", {}))

        # Upgrade handler
        builder.register(name="cap", handler=v2, version="2.0.0")
        spec = builder.get("cap")
        assert spec.version == "2.0.0"
        assert spec.invocation_count == 2  # preserved from v1

        # New invocation uses v2
        result = _run(builder.invoke("cap", {}))
        assert result.ok
        assert result.output["v"] == 2

    def test_agent_knows_sync(self):
        agent = _make_agent(caps=["existing-cap"])
        builder = CapabilityBuilder(agent)

        async def noop(p): return {}
        builder.register(name="new-cap", handler=noop)
        assert "new-cap" in agent._capabilities
        assert "existing-cap" in agent._capabilities
