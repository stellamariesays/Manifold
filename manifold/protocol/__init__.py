"""
Protocol message types for Manifold Federation — Task Execution (Phase 2).

Python mirror of federation/src/protocol/messages.ts TaskExecution types.
These define the contract between agents, runners, and federation servers.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any


# ── Enums ───────────────────────────────────────────────────────────────────────

class TaskStatus(str, Enum):
    SUCCESS = "success"
    ERROR = "error"
    TIMEOUT = "timeout"
    NOT_FOUND = "not_found"
    REJECTED = "rejected"


class MessageType(str, Enum):
    # Existing federation messages
    PEER_ANNOUNCE = "peer_announce"
    PEER_BYE = "peer_bye"
    CAPABILITY_QUERY = "capability_query"
    CAPABILITY_RESPONSE = "capability_response"
    AGENT_REQUEST = "agent_request"
    AGENT_RESPONSE = "agent_response"
    MESH_SYNC = "mesh_sync"
    PING = "ping"
    PONG = "pong"
    ERROR = "error"
    # Phase 2: Task execution
    TASK_REQUEST = "task_request"
    TASK_RESULT = "task_result"
    TASK_ACK = "task_ack"


# ── Task Execution ──────────────────────────────────────────────────────────────

@dataclass
class TaskRequest:
    """
    A request to execute a command on a target agent.

    Example:
        req = TaskRequest(
            target="cron-monitor@hog",
            command="watch",
            origin="hog",
            caller="eddie@hog",
        )
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    target: str = ""                     # "name@hub", "name" (local), or "any"
    capability: str | None = None        # required when target="any"
    command: str = ""                     # e.g. "watch", "audit", "status"
    args: dict[str, Any] = field(default_factory=dict)
    timeout_ms: int = 30000              # 30s default
    origin: str = ""                      # origin hub name
    caller: str = ""                      # "agent@hub" identity
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> TaskRequest:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class TaskResult:
    """
    Result of a task execution.

    Example:
        result = TaskResult(
            id=request_id,
            status=TaskStatus.SUCCESS,
            output={"total": 17, "issues": 0},
            executed_by="cron-monitor@hog",
            execution_ms=234,
        )
    """
    id: str = ""                         # matches TaskRequest.id
    status: TaskStatus = TaskStatus.SUCCESS
    output: Any = None                   # agent-defined JSON structure
    error: str | None = None             # human-readable if status != success
    executed_by: str | None = None       # "agent@hub"
    execution_ms: int | None = None      # wall-clock time
    completed_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> TaskResult:
        if "status" in data and isinstance(data["status"], str):
            data["status"] = TaskStatus(data["status"])
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

    @property
    def ok(self) -> bool:
        return self.status == TaskStatus.SUCCESS


@dataclass
class TaskAck:
    """Acknowledgment that a task was received and queued."""
    type: str = "task_ack"
    task_id: str = ""
    queue_position: int = 0             # 0 = executing immediately


# ── Wire Messages ───────────────────────────────────────────────────────────────

@dataclass
class TaskRequestMessage:
    """Wire format for sending a TaskRequest through the federation."""
    type: str = "task_request"
    task: TaskRequest = field(default_factory=TaskRequest)

    def to_dict(self) -> dict:
        return {"type": self.type, "task": self.task.to_dict()}

    @classmethod
    def from_dict(cls, data: dict) -> TaskRequestMessage:
        return cls(task=TaskRequest.from_dict(data.get("task", {})))


@dataclass
class TaskResultMessage:
    """Wire format for sending a TaskResult through the federation."""
    type: str = "task_result"
    result: TaskResult = field(default_factory=TaskResult)

    def to_dict(self) -> dict:
        return {"type": self.type, "result": self.result.to_dict()}

    @classmethod
    def from_dict(cls, data: dict) -> TaskResultMessage:
        return cls(result=TaskResult.from_dict(data.get("result", {})))


# ── Helper ──────────────────────────────────────────────────────────────────────

def parse_message(data: dict) -> TaskRequestMessage | TaskResultMessage | dict:
    """Parse a raw dict into the appropriate message type."""
    msg_type = data.get("type", "")
    if msg_type == "task_request":
        return TaskRequestMessage.from_dict(data)
    elif msg_type == "task_result":
        return TaskResultMessage.from_dict(data)
    return data
