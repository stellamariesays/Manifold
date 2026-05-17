"""Tests for the adapter/translation capability pack."""

import asyncio
import json
import pytest
from unittest.mock import MagicMock

from manifold.agent import Agent
from manifold.capability_builder import CapabilityBuilder
from manifold.capability_pack import load_adapter_pack


def _make_builder() -> CapabilityBuilder:
    agent = Agent(name="test-adapter")
    builder = CapabilityBuilder(agent)
    load_adapter_pack(builder)
    return builder


@pytest.fixture
def builder():
    return _make_builder()


# ─── Pack loading ─────────────────────────────────────────────────────

class TestAdapterPackLoading:
    def test_loads_five_capabilities(self, builder):
        caps = builder.list_capabilities()
        names = [c.name for c in caps]
        assert "adapter-format" in names
        assert "adapter-schema-map" in names
        assert "adapter-bridge" in names
        assert "adapter-normalize" in names
        assert "adapter-validate" in names
        assert len(names) == 5

    def test_all_caps_have_adapter_tag(self, builder):
        for cap in builder.list_capabilities():
            assert "adapter" in cap.tags

    def test_all_caps_are_invocable(self, builder):
        for cap in builder.list_capabilities():
            assert cap.is_invocable


# ─── Format conversion ────────────────────────────────────────────────

class TestFormatConversion:
    @pytest.mark.asyncio
    async def test_json_to_json(self, builder):
        result = await builder.invoke("adapter-format", {
            "data": '{"name": "test", "value": 42}',
            "from_format": "json",
            "to_format": "json",
        })
        assert result.ok
        parsed = json.loads(result.output["output"])
        assert parsed["name"] == "test"
        assert parsed["value"] == 42

    @pytest.mark.asyncio
    async def test_json_to_text(self, builder):
        result = await builder.invoke("adapter-format", {
            "data": '{"key": "val"}',
            "from_format": "json",
            "to_format": "text",
        })
        assert result.ok
        assert "val" in result.output["output"]

    @pytest.mark.asyncio
    async def test_csv_to_json(self, builder):
        csv_data = "name,age\nalice,30\nbob,25"
        result = await builder.invoke("adapter-format", {
            "data": csv_data,
            "from_format": "csv",
            "to_format": "json",
        })
        assert result.ok
        parsed = json.loads(result.output["output"])
        assert len(parsed) == 2
        assert parsed[0]["name"] == "alice"

    @pytest.mark.asyncio
    async def test_json_to_csv(self, builder):
        data = json.dumps([{"x": 1, "y": 2}, {"x": 3, "y": 4}])
        result = await builder.invoke("adapter-format", {
            "data": data,
            "from_format": "json",
            "to_format": "csv",
        })
        assert result.ok
        assert "x,y" in result.output["output"]
        assert "1,2" in result.output["output"]

    @pytest.mark.asyncio
    async def test_empty_data_fails(self, builder):
        result = await builder.invoke("adapter-format", {
            "data": "",
            "from_format": "json",
            "to_format": "csv",
        })
        assert not result.ok

    @pytest.mark.asyncio
    async def test_unknown_format_fails(self, builder):
        result = await builder.invoke("adapter-format", {
            "data": "stuff",
            "from_format": "xml",
            "to_format": "json",
        })
        assert not result.ok

    @pytest.mark.asyncio
    async def test_csv_export_non_list_fails(self, builder):
        result = await builder.invoke("adapter-format", {
            "data": '"not a list"',
            "from_format": "json",
            "to_format": "csv",
        })
        assert not result.ok


# ─── Schema mapping ───────────────────────────────────────────────────

class TestSchemaMapping:
    @pytest.mark.asyncio
    async def test_explicit_mapping(self, builder):
        result = await builder.invoke("adapter-schema-map", {
            "data": {"first_name": "Ada", "last_name": "Lovelace"},
            "source_fields": ["first_name", "last_name"],
            "target_fields": ["firstName", "lastName"],
            "mapping": {"first_name": "firstName", "last_name": "lastName"},
        })
        assert result.ok
        assert result.output["mapped"]["firstName"] == "Ada"
        assert result.output["mapped"]["lastName"] == "Lovelace"

    @pytest.mark.asyncio
    async def test_auto_mapping_by_similarity(self, builder):
        result = await builder.invoke("adapter-schema-map", {
            "data": {"user_name": "test", "email_address": "a@b.com"},
            "source_fields": ["user_name", "email_address"],
            "target_fields": ["userName", "emailAddress"],
        })
        assert result.ok
        # Should auto-detect similar field names
        mapping = result.output["mapping_used"]
        assert len(mapping) >= 1

    @pytest.mark.asyncio
    async def test_unmapped_fields_carried(self, builder):
        result = await builder.invoke("adapter-schema-map", {
            "data": {"keep": "this", "rename_me": "val"},
            "source_fields": ["keep", "rename_me"],
            "target_fields": ["keep", "renamed"],
            "mapping": {"rename_me": "renamed"},
        })
        assert result.ok
        assert result.output["mapped"]["keep"] == "this"
        assert result.output["mapped"]["renamed"] == "val"

    @pytest.mark.asyncio
    async def test_empty_data_fails(self, builder):
        result = await builder.invoke("adapter-schema-map", {
            "data": {},
            "source_fields": [],
            "target_fields": [],
        })
        assert not result.ok


# ─── Protocol bridging ────────────────────────────────────────────────

class TestProtocolBridge:
    @pytest.mark.asyncio
    async def test_same_version_no_bridge(self, builder):
        result = await builder.invoke("adapter-bridge", {
            "message": {"type": "ping"},
            "from_version": "1.0",
            "to_version": "1.0",
        })
        assert result.ok
        assert not result.output["bridged"]
        assert result.output["message"] == {"type": "ping"}

    @pytest.mark.asyncio
    async def test_v1_to_v2_wraps_envelope(self, builder):
        result = await builder.invoke("adapter-bridge", {
            "message": {"type": "ping", "data": "hello"},
            "from_version": "1.0",
            "to_version": "2.0",
        })
        assert result.ok
        assert result.output["bridged"]
        msg = result.output["message"]
        assert "envelope" in msg
        assert msg["envelope"]["version"] == "2.0"
        assert msg["payload"] == {"type": "ping", "data": "hello"}

    @pytest.mark.asyncio
    async def test_v2_to_v1_flattens(self, builder):
        result = await builder.invoke("adapter-bridge", {
            "message": {
                "envelope": {"version": "2.0", "timestamp": 1234},
                "payload": {"type": "pong", "data": "world"},
                "metadata": {"trace_id": "abc"},
            },
            "from_version": "2.0",
            "to_version": "1.0",
        })
        assert result.ok
        assert result.output["bridged"]
        msg = result.output["message"]
        assert msg["type"] == "pong"
        assert msg["trace_id"] == "abc"
        assert "envelope" not in msg


# ─── Normalization ────────────────────────────────────────────────────

class TestNormalization:
    @pytest.mark.asyncio
    async def test_strip_whitespace(self, builder):
        result = await builder.invoke("adapter-normalize", {
            "data": {"name": "  hello  ", "nested": {"val": " world "}},
        })
        assert result.ok
        assert result.output["normalized"]["name"] == "hello"
        assert result.output["normalized"]["nested"]["val"] == "world"

    @pytest.mark.asyncio
    async def test_lowercase(self, builder):
        result = await builder.invoke("adapter-normalize", {
            "data": {"name": "HELLO"},
            "rules": {"lowercase": True},
        })
        assert result.ok
        assert result.output["normalized"]["name"] == "hello"

    @pytest.mark.asyncio
    async def test_uppercase(self, builder):
        result = await builder.invoke("adapter-normalize", {
            "data": {"name": "hello"},
            "rules": {"uppercase": True},
        })
        assert result.ok
        assert result.output["normalized"]["name"] == "HELLO"

    @pytest.mark.asyncio
    async def test_list_normalization(self, builder):
        result = await builder.invoke("adapter-normalize", {
            "data": ["  a  ", "  b  "],
        })
        assert result.ok
        assert result.output["normalized"] == ["a", "b"]

    @pytest.mark.asyncio
    async def test_no_data_fails(self, builder):
        result = await builder.invoke("adapter-normalize", {})
        assert not result.ok


# ─── Validation ───────────────────────────────────────────────────────

class TestValidation:
    @pytest.mark.asyncio
    async def test_valid_data(self, builder):
        result = await builder.invoke("adapter-validate", {
            "data": {"name": "test", "age": 25, "role": "admin"},
            "schema": {
                "required": ["name", "age"],
                "fields": {
                    "age": {"type": "int"},
                    "role": {"enum": ["admin", "user", "guest"]},
                },
            },
        })
        assert result.ok
        assert result.output["valid"]

    @pytest.mark.asyncio
    async def test_missing_required(self, builder):
        result = await builder.invoke("adapter-validate", {
            "data": {"name": "test"},
            "schema": {
                "required": ["name", "email"],
            },
        })
        assert result.ok
        assert not result.output["valid"]
        assert any("email" in e for e in result.output["errors"])

    @pytest.mark.asyncio
    async def test_wrong_type(self, builder):
        result = await builder.invoke("adapter-validate", {
            "data": {"age": "not_a_number"},
            "schema": {
                "fields": {"age": {"type": "int"}},
            },
        })
        assert result.ok
        assert not result.output["valid"]

    @pytest.mark.asyncio
    async def test_enum_violation(self, builder):
        result = await builder.invoke("adapter-validate", {
            "data": {"status": "unknown"},
            "schema": {
                "fields": {"status": {"enum": ["active", "inactive"]}},
            },
        })
        assert result.ok
        assert not result.output["valid"]

    @pytest.mark.asyncio
    async def test_empty_schema_passes(self, builder):
        result = await builder.invoke("adapter-validate", {
            "data": {"anything": "goes"},
            "schema": {},
        })
        assert result.ok
        assert result.output["valid"]
