"""Tests for the security capability pack."""

import asyncio
import time
import pytest

from manifold.agent import Agent
from manifold.capability_builder import CapabilityBuilder
from manifold.capability_pack import load_security_pack


def _make_builder() -> CapabilityBuilder:
    agent = Agent(name="test-security")
    builder = CapabilityBuilder(agent)
    load_security_pack(builder)
    return builder


@pytest.fixture
def builder():
    return _make_builder()


# ─── Pack loading ─────────────────────────────────────────────────────

class TestSecurityPackLoading:
    def test_loads_five_capabilities(self, builder):
        caps = builder.list_capabilities()
        names = [c.name for c in caps]
        assert "sec-auth" in names
        assert "sec-permission" in names
        assert "sec-rate-limit" in names
        assert "sec-sanitize" in names
        assert "sec-audit" in names
        assert len(names) == 5

    def test_all_caps_have_security_tag(self, builder):
        for cap in builder.list_capabilities():
            assert "security" in cap.tags

    def test_all_caps_are_invocable(self, builder):
        for cap in builder.list_capabilities():
            assert cap.is_invocable


# ─── Auth token ───────────────────────────────────────────────────────

class TestSecAuth:
    @pytest.mark.asyncio
    async def test_issue_token(self, builder):
        result = await builder.invoke("sec-auth", {
            "mode": "issue",
            "agent": "alice",
            "role": "operator",
            "ttl": 3600,
        })
        assert result.ok
        assert result.output["ok"] is True
        assert "token" in result.output
        assert result.output["token"].startswith("mf_")
        assert result.output["role"] == "operator"

    @pytest.mark.asyncio
    async def test_verify_valid_token(self, builder):
        issue = await builder.invoke("sec-auth", {
            "mode": "issue",
            "agent": "bob",
            "role": "admin",
            "ttl": 3600,
        })
        token = issue.output["token"]

        result = await builder.invoke("sec-auth", {
            "mode": "verify",
            "token": token,
        })
        assert result.output["ok"] is True
        assert result.output["valid"] is True
        assert result.output["agent"] == "bob"
        assert result.output["role"] == "admin"

    @pytest.mark.asyncio
    async def test_verify_invalid_token(self, builder):
        result = await builder.invoke("sec-auth", {
            "mode": "verify",
            "token": "mf_nonexistent_token",
        })
        assert result.output["valid"] is False

    @pytest.mark.asyncio
    async def test_verify_no_token(self, builder):
        result = await builder.invoke("sec-auth", {
            "mode": "verify",
        })
        assert result.output["ok"] is False

    @pytest.mark.asyncio
    async def test_issue_requires_agent(self, builder):
        result = await builder.invoke("sec-auth", {
            "mode": "issue",
        })
        assert result.output["ok"] is False


# ─── Permission check ────────────────────────────────────────────────

class TestSecPermission:
    @pytest.mark.asyncio
    async def test_admin_has_all_perms(self, builder):
        for perm in ["read", "write", "delete", "manage", "invoke", "delegate"]:
            result = await builder.invoke("sec-permission", {
                "role": "admin",
                "permission": perm,
                "agent": "root",
            })
            assert result.output["allowed"] is True, f"admin should have {perm}"

    @pytest.mark.asyncio
    async def test_agent_limited_perms(self, builder):
        result = await builder.invoke("sec-permission", {
            "role": "agent",
            "permission": "read",
        })
        assert result.output["allowed"] is True

        result = await builder.invoke("sec-permission", {
            "role": "agent",
            "permission": "delete",
        })
        assert result.output["allowed"] is False

    @pytest.mark.asyncio
    async def test_observer_readonly(self, builder):
        result = await builder.invoke("sec-permission", {
            "role": "observer",
            "permission": "read",
        })
        assert result.output["allowed"] is True

        result = await builder.invoke("sec-permission", {
            "role": "observer",
            "permission": "write",
        })
        assert result.output["allowed"] is False

    @pytest.mark.asyncio
    async def test_unknown_role_no_perms(self, builder):
        result = await builder.invoke("sec-permission", {
            "role": "stranger",
            "permission": "read",
        })
        assert result.output["allowed"] is False

    @pytest.mark.asyncio
    async def test_missing_permission_fails(self, builder):
        result = await builder.invoke("sec-permission", {
            "role": "admin",
        })
        assert result.ok is False
        assert "permission" in (result.error or "")


# ─── Rate limiting ───────────────────────────────────────────────────

class TestSecRateLimit:
    @pytest.mark.asyncio
    async def test_under_limit_allowed(self, builder):
        result = await builder.invoke("sec-rate-limit", {
            "action": "consume",
            "key": "test-rl-1",
            "max_requests": 5,
            "window_seconds": 60,
        })
        assert result.output["allowed"] is True
        assert result.output["current"] == 1

    @pytest.mark.asyncio
    async def test_over_limit_blocked(self, builder):
        key = "test-rl-exhaust"
        for _ in range(3):
            await builder.invoke("sec-rate-limit", {
                "action": "consume",
                "key": key,
                "max_requests": 3,
                "window_seconds": 60,
            })
        # 4th should be blocked
        result = await builder.invoke("sec-rate-limit", {
            "action": "consume",
            "key": key,
            "max_requests": 3,
            "window_seconds": 60,
        })
        assert result.output["allowed"] is False

    @pytest.mark.asyncio
    async def test_check_does_not_consume(self, builder):
        key = "test-rl-check"
        await builder.invoke("sec-rate-limit", {
            "action": "consume",
            "key": key,
            "max_requests": 1,
            "window_seconds": 60,
        })
        # check shouldn't add another
        result = await builder.invoke("sec-rate-limit", {
            "action": "check",
            "key": key,
            "max_requests": 1,
            "window_seconds": 60,
        })
        assert result.output["current"] == 1


# ─── Input sanitization ──────────────────────────────────────────────

class TestSecSanitize:
    @pytest.mark.asyncio
    async def test_strips_html(self, builder):
        result = await builder.invoke("sec-sanitize", {
            "data": "<b>Hello</b> <script>alert('xss')</script> world",
            "mode": "text",
        })
        assert result.output["ok"] is True
        assert "<script>" not in result.output["cleaned"]
        assert "Hello" in result.output["cleaned"]

    @pytest.mark.asyncio
    async def test_normalizes_whitespace(self, builder):
        result = await builder.invoke("sec-sanitize", {
            "data": "hello   world\n\nfoo",
            "mode": "text",
        })
        assert result.output["cleaned"] == "hello world foo"

    @pytest.mark.asyncio
    async def test_strict_blocks_sql_injection(self, builder):
        result = await builder.invoke("sec-sanitize", {
            "data": "SELECT * FROM users WHERE 1=1",
            "mode": "strict",
        })
        assert "sql_injection" in result.output["threats"]
        assert result.output["safe"] is False

    @pytest.mark.asyncio
    async def test_strict_blocks_command_injection(self, builder):
        result = await builder.invoke("sec-sanitize", {
            "data": "; rm -rf /",
            "mode": "strict",
        })
        assert "command_injection" in result.output["threats"]

    @pytest.mark.asyncio
    async def test_strict_blocks_path_traversal(self, builder):
        result = await builder.invoke("sec-sanitize", {
            "data": "../../../etc/passwd",
            "mode": "strict",
        })
        assert "path_traversal" in result.output["threats"]

    @pytest.mark.asyncio
    async def test_clean_text_passes(self, builder):
        result = await builder.invoke("sec-sanitize", {
            "data": "Hello, this is fine.",
            "mode": "strict",
        })
        assert result.output["safe"] is True
        assert result.output["threats"] == []

    @pytest.mark.asyncio
    async def test_non_string_fails(self, builder):
        result = await builder.invoke("sec-sanitize", {
            "data": 42,
            "mode": "text",
        })
        assert result.output["ok"] is False


# ─── Audit log ───────────────────────────────────────────────────────

class TestSecAudit:
    @pytest.mark.asyncio
    async def test_append_and_query(self, builder):
        await builder.invoke("sec-audit", {
            "action": "append",
            "agent": "alice",
            "event": "login",
            "details": {"ip": "10.0.0.1"},
        })
        result = await builder.invoke("sec-audit", {
            "action": "query",
            "agent": "alice",
            "limit": 10,
        })
        assert result.output["ok"] is True
        assert result.output["returned"] >= 1
        found = any(e["action"] == "login" for e in result.output["entries"])
        assert found

    @pytest.mark.asyncio
    async def test_query_filter_by_agent(self, builder):
        await builder.invoke("sec-audit", {
            "action": "append",
            "agent": "charlie-filter-test",
            "event": "test-event",
        })
        result = await builder.invoke("sec-audit", {
            "action": "query",
            "agent": "charlie-filter-test",
        })
        for entry in result.output["entries"]:
            assert entry["agent"] == "charlie-filter-test"

    @pytest.mark.asyncio
    async def test_query_respects_limit(self, builder):
        for i in range(5):
            await builder.invoke("sec-audit", {
                "action": "append",
                "agent": "limit-test",
                "event": f"event-{i}",
            })
        result = await builder.invoke("sec-audit", {
            "action": "query",
            "agent": "limit-test",
            "limit": 2,
        })
        assert result.output["returned"] == 2
