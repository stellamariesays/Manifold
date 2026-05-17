"""Tests for goal decomposition capability pack."""

import asyncio
import pytest
from manifold.capability_builder import CapabilityBuilder
from manifold.capability_pack import (
    load_goal_decomposition_pack,
    _goal_store,
)


@pytest.fixture(autouse=True)
def clear_goal_store():
    _goal_store.clear()
    yield
    _goal_store.clear()


@pytest.fixture
def builder():
    b = CapabilityBuilder(None)
    load_goal_decomposition_pack(b)
    return b


def _invoke(builder, name, payload):
    return asyncio.run(builder.invoke(name, payload))


class TestGoalDecompose:
    def test_basic_decomposition(self, builder):
        res = _invoke(builder, "goal-decompose", {
            "goal": "Design the system. Implement the API. Write tests. Deploy to production."
        })
        r = res.output
        assert r["ok"] is True
        assert len(r["subtasks"]) == 4
        assert r["subtasks"][0]["status"] == "pending"
        assert r["subtasks"][0]["depends_on"] == []
        assert r["subtasks"][1]["depends_on"] == [r["subtasks"][0]["id"]]
        assert r["goal_id"].startswith("goal-")

    def test_priority_detection(self, builder):
        r = _invoke(builder, "goal-decompose", {
            "goal": "Fix critical security issue. Update docs. Refactor code."
        }).output
        assert r["ok"]
        assert r["subtasks"][0]["priority"] == "high"
        assert r["subtasks"][1]["priority"] == "normal"

    def test_empty_goal(self, builder):
        r = _invoke(builder, "goal-decompose", {"goal": ""}).output
        assert r["ok"] is False

    def test_max_subtasks(self, builder):
        r = _invoke(builder, "goal-decompose", {
            "goal": "One. Two. Three. Four. Five. Six. Seven. Eight. Nine. Ten.",
            "max_subtasks": 3,
        }).output
        assert r["ok"]
        assert len(r["subtasks"]) == 3

    def test_bulleted_input(self, builder):
        r = _invoke(builder, "goal-decompose", {
            "goal": "1. First thing\n2. Second thing\n3. Third thing"
        }).output
        assert r["ok"]
        assert len(r["subtasks"]) == 3


class TestGoalStatus:
    def test_status_after_decompose(self, builder):
        dec = _invoke(builder, "goal-decompose", {"goal": "Do something important."}).output
        gid = dec["goal_id"]
        r = _invoke(builder, "goal-status", {"goal_id": gid}).output
        assert r["ok"]
        assert r["status"] == "planned"
        assert r["progress"] == "0/1"

    def test_nonexistent_goal(self, builder):
        r = _invoke(builder, "goal-status", {"goal_id": "goal-9999"}).output
        assert r["ok"] is False


class TestGoalSubtaskUpdate:
    def test_update_status(self, builder):
        dec = _invoke(builder, "goal-decompose", {"goal": "Do A. Then do B."}).output
        gid = dec["goal_id"]
        sub0 = dec["subtasks"][0]["id"]
        r = _invoke(builder, "goal-subtask-update", {
            "goal_id": gid, "subtask_id": sub0, "status": "done"
        }).output
        assert r["ok"] is True
        assert r["status"] == "done"

    def test_dependency_blocking(self, builder):
        dec = _invoke(builder, "goal-decompose", {"goal": "Do A. Then do B."}).output
        gid = dec["goal_id"]
        sub1 = dec["subtasks"][1]["id"]
        r = _invoke(builder, "goal-subtask-update", {
            "goal_id": gid, "subtask_id": sub1, "status": "done"
        }).output
        assert r["ok"] is False
        assert "blocked_by" in r


class TestGoalNext:
    def test_get_next(self, builder):
        dec = _invoke(builder, "goal-decompose", {"goal": "Do A. Then do B."}).output
        gid = dec["goal_id"]
        r = _invoke(builder, "goal-next", {"goal_id": gid}).output
        assert r["ok"]
        assert r["subtask"]["id"] == dec["subtasks"][0]["id"]

    def test_blocked(self, builder):
        dec = _invoke(builder, "goal-decompose", {"goal": "Do A. Then do B."}).output
        gid = dec["goal_id"]
        sub0 = dec["subtasks"][0]["id"]
        _invoke(builder, "goal-subtask-update", {"goal_id": gid, "subtask_id": sub0, "status": "in_progress"})
        r = _invoke(builder, "goal-next", {"goal_id": gid}).output
        assert r["ok"] is True
        assert r.get("blocked") is True

    def test_all_done(self, builder):
        dec = _invoke(builder, "goal-decompose", {"goal": "Single task."}).output
        gid = dec["goal_id"]
        sub0 = dec["subtasks"][0]["id"]
        _invoke(builder, "goal-subtask-update", {"goal_id": gid, "subtask_id": sub0, "status": "done"})
        r = _invoke(builder, "goal-next", {"goal_id": gid}).output
        assert r["ok"]
        assert r.get("completed") is True


class TestGoalList:
    def test_list_goals(self, builder):
        _invoke(builder, "goal-decompose", {"goal": "Goal A."})
        _invoke(builder, "goal-decompose", {"goal": "Goal B."})
        r = _invoke(builder, "goal-list", {}).output
        assert r["ok"]
        assert r["total"] == 2

    def test_filter_by_status(self, builder):
        _invoke(builder, "goal-decompose", {"goal": "Goal A."})
        r = _invoke(builder, "goal-list", {"status": "planned"}).output
        assert r["ok"]
        assert r["total"] == 1


class TestGoalMerge:
    def test_merge_two_goals(self, builder):
        g1 = _invoke(builder, "goal-decompose", {"goal": "Design. Build."}).output
        g2 = _invoke(builder, "goal-decompose", {"goal": "Test. Deploy."}).output
        r = _invoke(builder, "goal-merge", {
            "goal_id_1": g1["goal_id"], "goal_id_2": g2["goal_id"]
        }).output
        assert r["ok"]
        assert r["total_subtasks"] == 4
        assert r["merged_goal_id"].startswith("goal-")

    def test_merge_nonexistent(self, builder):
        g1 = _invoke(builder, "goal-decompose", {"goal": "Only goal."}).output
        r = _invoke(builder, "goal-merge", {
            "goal_id_1": g1["goal_id"], "goal_id_2": "goal-9999"
        }).output
        assert r["ok"] is False
