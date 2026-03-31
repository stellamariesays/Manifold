"""Tests for manifold.store.PersistentStore."""

import json
import tempfile
from pathlib import Path

import pytest

from manifold.registry import CapabilityRegistry
from manifold.store import PersistentStore


def _reg(*agents) -> CapabilityRegistry:
    """Build a registry from (name, caps) tuples."""
    reg = CapabilityRegistry()
    for name, caps in agents:
        reg.register_self(name, caps, f"mem://{name}")
    return reg


# ── load / save round-trip ────────────────────────────────────────────────────

def test_save_and_load_round_trip():
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        path = Path(f.name)

    try:
        reg = _reg(
            ("stella", ["identity", "judgment"]),
            ("braid", ["solar", "machine-learning"]),
        )
        PersistentStore.save(path, reg)

        loaded = PersistentStore.load(path)
        names = {r.name for r in loaded.all_agents()}
        assert names == {"stella", "braid"}

        stella = loaded._records["stella"]
        assert "identity" in stella.capabilities
        assert "judgment" in stella.capabilities
    finally:
        path.unlink(missing_ok=True)


def test_load_nonexistent_returns_empty():
    reg = PersistentStore.load("/tmp/manifold_no_such_file_xyz.json")
    assert reg.all_agents() == []


def test_load_corrupt_file_returns_empty(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("this is not json {{{{")
    reg = PersistentStore.load(p)
    assert reg.all_agents() == []


def test_save_creates_parent_dirs(tmp_path):
    deep = tmp_path / "a" / "b" / "c" / "atlas.json"
    reg = _reg(("stella", ["identity"]))
    PersistentStore.save(deep, reg)
    assert deep.exists()


def test_save_json_format(tmp_path):
    p = tmp_path / "atlas.json"
    reg = _reg(("stella", ["identity", "judgment"]))
    PersistentStore.save(p, reg)

    data = json.loads(p.read_text())
    assert data["version"] == 1
    assert "saved_at" in data
    assert len(data["agents"]) == 1
    assert data["agents"][0]["name"] == "stella"


def test_focus_persists(tmp_path):
    p = tmp_path / "atlas.json"
    reg = _reg(("stella", ["identity"]))
    reg._records["stella"].focus = "agent-identity"
    PersistentStore.save(p, reg)

    loaded = PersistentStore.load(p)
    assert loaded._records["stella"].focus == "agent-identity"


# ── merge ─────────────────────────────────────────────────────────────────────

def test_merge_prefer_new(tmp_path):
    p = tmp_path / "atlas.json"

    # Stored state
    stored = _reg(("stella", ["old-cap"]), ("braid", ["solar"]))
    PersistentStore.save(p, stored)

    # New session — stella has updated caps, wake is new
    new_reg = _reg(("stella", ["new-cap"]), ("wake", ["training"]))
    merged = PersistentStore.merge(p, new_reg, prefer_new=True)

    names = {r.name for r in merged.all_agents()}
    assert names == {"stella", "braid", "wake"}
    # Stella's new caps win
    assert "new-cap" in merged._records["stella"].capabilities
    assert "old-cap" not in merged._records["stella"].capabilities


def test_merge_prefer_stored(tmp_path):
    p = tmp_path / "atlas.json"

    stored = _reg(("stella", ["stored-cap"]))
    PersistentStore.save(p, stored)

    new_reg = _reg(("stella", ["new-cap"]))
    merged = PersistentStore.merge(p, new_reg, prefer_new=False)

    assert "stored-cap" in merged._records["stella"].capabilities
    assert "new-cap" not in merged._records["stella"].capabilities


def test_merge_empty_store(tmp_path):
    p = tmp_path / "atlas.json"  # doesn't exist yet

    reg = _reg(("stella", ["identity"]))
    merged = PersistentStore.merge(p, reg)

    assert "stella" in {r.name for r in merged.all_agents()}
    assert p.exists()  # saved after merge


def test_merge_saves_to_disk(tmp_path):
    p = tmp_path / "atlas.json"
    reg = _reg(("stella", ["identity"]), ("braid", ["solar"]))
    PersistentStore.merge(p, reg)

    # Re-load from disk
    reloaded = PersistentStore.load(p)
    names = {r.name for r in reloaded.all_agents()}
    assert "stella" in names
    assert "braid" in names


# ── summary ───────────────────────────────────────────────────────────────────

def test_summary_existing_file(tmp_path):
    p = tmp_path / "atlas.json"
    reg = _reg(("stella", ["identity"]), ("braid", ["solar"]))
    PersistentStore.save(p, reg)

    s = PersistentStore.summary(p)
    assert s["count"] == 2
    assert set(s["agents"]) == {"stella", "braid"}
    assert s["saved_at"] is not None


def test_summary_missing_file():
    s = PersistentStore.summary("/tmp/manifold_missing_xyz.json")
    assert s["count"] == 0
    assert s["agents"] == []
    assert s["saved_at"] is None
