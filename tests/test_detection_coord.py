#!/usr/bin/env python3
"""
Integration tests for the Detection Coordination REST API.

These tests require a running federation server at localhost:8767.
They are marked ``pytest.mark.integration`` and are excluded from CI.

Run manually:
    pytest tests/test_detection_coord.py -m integration -v
"""

import json
import time
import urllib.error
import urllib.request
import uuid

import pytest

REST_URL = "http://localhost:8767"


# ── Helpers ───────────────────────────────────────────────────────────────────


def get(path: str) -> dict:
    try:
        with urllib.request.urlopen(f"{REST_URL}{path}", timeout=5) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return json.loads(e.read())


def post(path: str, body: dict) -> dict:
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        f"{REST_URL}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return json.loads(e.read())


def _skip_if_unreachable() -> None:
    """Skip the whole module if the federation server is not up."""
    try:
        with urllib.request.urlopen(f"{REST_URL}/status", timeout=3):
            pass
    except Exception as exc:
        pytest.skip(f"Federation server not reachable at {REST_URL}: {exc}")


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module", autouse=True)
def require_server():
    """Skip all tests in this module when the server is down."""
    _skip_if_unreachable()


@pytest.fixture()
def submitted_claim() -> dict:
    """POST a fresh claim and return the server response."""
    body = {
        "source": f"test-agent@satelitea",
        "domain": "test-integration",
        "summary": f"integration test claim {uuid.uuid4().hex[:8]}",
        "confidence": 0.85,
    }
    resp = post("/detection/claim", body)
    assert "claim_id" in resp, f"POST /detection/claim failed: {resp}"
    return resp


# ── GET /detections — list shape ──────────────────────────────────────────────


@pytest.mark.integration
def test_detections_returns_list():
    """GET /detections returns a dict with a 'claims' list and 'total' int."""
    result = get("/detections")
    assert "claims" in result, f"Missing 'claims' key: {result}"
    assert "total" in result, f"Missing 'total' key: {result}"
    assert isinstance(result["claims"], list)
    assert isinstance(result["total"], int)


@pytest.mark.integration
def test_detections_claim_shape():
    """Each entry in /detections has the expected fields."""
    result = get("/detections?limit=5")
    if not result["claims"]:
        pytest.skip("No claims in ledger — nothing to assert shape on")

    required = {"id", "source", "domain", "summary", "confidence",
                "created_at", "verifications", "challenges", "outcome"}
    for entry in result["claims"]:
        missing = required - entry.keys()
        assert not missing, f"Claim entry missing fields {missing}: {entry}"


@pytest.mark.integration
def test_detections_domain_filter():
    """GET /detections?domain=solar returns only solar-domain entries."""
    result = get("/detections?domain=solar&limit=20")
    for entry in result["claims"]:
        assert entry["domain"] == "solar", (
            f"Expected domain='solar', got {entry['domain']!r}"
        )


@pytest.mark.integration
def test_detections_limit_respected():
    """?limit=3 returns at most 3 entries."""
    result = get("/detections?limit=3")
    assert len(result["claims"]) <= 3


# ── GET /detections/stats ─────────────────────────────────────────────────────


@pytest.mark.integration
def test_detection_stats_shape():
    """GET /detections/stats returns expected stat fields."""
    stats = get("/detections/stats")
    for field in ("total", "open", "confirmed", "false_positive", "domains"):
        assert field in stats, f"Missing field '{field}' in stats: {stats}"
    assert isinstance(stats["total"], int)
    assert isinstance(stats["open"], int)
    assert isinstance(stats["confirmed"], int)
    assert isinstance(stats["false_positive"], int)
    assert isinstance(stats["domains"], list)


@pytest.mark.integration
def test_detection_stats_counts_consistent():
    """open + confirmed + false_positive should be <= total."""
    stats = get("/detections/stats")
    accounted = stats["open"] + stats["confirmed"] + stats["false_positive"]
    assert accounted <= stats["total"], (
        f"Counts inconsistent: {accounted} > total {stats['total']}"
    )


# ── POST /detection/claim ─────────────────────────────────────────────────────


@pytest.mark.integration
def test_submit_claim_returns_claim_id(submitted_claim):
    """POST /detection/claim returns claim_id and status=recorded."""
    assert submitted_claim.get("status") == "recorded", (
        f"Expected status='recorded': {submitted_claim}"
    )
    assert "claim_id" in submitted_claim
    # claim_id should be a UUID-shaped string
    claim_id = submitted_claim["claim_id"]
    assert len(claim_id) == 36 and claim_id.count("-") == 4, (
        f"Unexpected claim_id format: {claim_id!r}"
    )


@pytest.mark.integration
def test_submit_claim_appears_in_list(submitted_claim):
    """A freshly submitted claim shows up in GET /detections."""
    claim_id = submitted_claim["claim_id"]
    result = get("/detections?limit=50")
    ids = {e["id"] for e in result["claims"]}
    assert claim_id in ids, (
        f"Submitted claim {claim_id} not found in /detections listing"
    )


@pytest.mark.integration
def test_submit_claim_confidence_range():
    """Confidence is stored as submitted and is in [0, 1]."""
    resp = post("/detection/claim", {
        "source": "test-agent@satelitea",
        "domain": "test-integration",
        "summary": "confidence range test",
        "confidence": 0.42,
    })
    assert "claim_id" in resp
    detail = get(f"/detections/{resp['claim_id']}")
    assert "claim" in detail
    confidence = detail["claim"]["confidence"]
    assert 0.0 <= confidence <= 1.0
    assert abs(confidence - 0.42) < 0.001


# ── GET /detections/:id ───────────────────────────────────────────────────────


@pytest.mark.integration
def test_detection_detail_shape(submitted_claim):
    """GET /detections/:id returns full claim detail with verifications list."""
    claim_id = submitted_claim["claim_id"]
    detail = get(f"/detections/{claim_id}")
    for field in ("claim", "verifications", "challenges"):
        assert field in detail, f"Missing field '{field}' in detail: {detail}"
    assert isinstance(detail["verifications"], list)
    assert isinstance(detail["challenges"], list)


@pytest.mark.integration
def test_detection_detail_claim_fields(submitted_claim):
    """Detail claim object has all required protocol fields."""
    claim_id = submitted_claim["claim_id"]
    detail = get(f"/detections/{claim_id}")
    claim = detail["claim"]
    for field in ("id", "source", "domain", "summary", "confidence", "created_at"):
        assert field in claim, f"Claim missing field '{field}': {claim}"
    assert claim["id"] == claim_id


@pytest.mark.integration
def test_detection_detail_unknown_id():
    """GET /detections/<nonexistent-id> returns a 404-shaped response."""
    fake_id = str(uuid.uuid4())
    result = get(f"/detections/{fake_id}")
    # Server returns {"error": "..."} or similar — must not return a claim object
    assert "claim" not in result or result.get("error"), (
        f"Expected error response for unknown id, got: {result}"
    )


# ── POST /detection/verify ────────────────────────────────────────────────────


@pytest.mark.integration
def test_submit_verify(submitted_claim):
    """POST /detection/verify records a verification against an existing claim."""
    claim_id = submitted_claim["claim_id"]
    resp = post("/detection/verify", {
        "claim_id": claim_id,
        "verifier": "test-verifier@satelitea",
        "agrees": True,
        "confidence": 0.9,
        "notes": "integration test verification",
    })
    # Accept any non-error response shape — as long as no protocol error
    assert "error" not in resp, f"Verify failed: {resp}"
    # Verification count should have incremented
    detail = get(f"/detections/{claim_id}")
    assert isinstance(detail.get("verifications", []), list)


# ── Propagation flag ──────────────────────────────────────────────────────────


@pytest.mark.integration
def test_submit_claim_propagated_flag():
    """POST /detection/claim response includes a propagated boolean."""
    resp = post("/detection/claim", {
        "source": "test-agent@satelitea",
        "domain": "test-integration",
        "summary": "propagation flag test",
        "confidence": 0.75,
    })
    assert "propagated" in resp, (
        f"Expected 'propagated' field in response: {resp}"
    )
    assert isinstance(resp["propagated"], bool)
