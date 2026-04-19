# Manifold Federation Protocol

## Message Format

All messages are JSON objects with a `type` field. Messages flow over WebSocket connections (federation port 8766, local port 8768).

---

## Message Types

### Peer Discovery

#### `peer_announce`
**Direction:** hub → hub (federation)

A hub announces itself to a peer.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | string | ✓ | `"peer_announce"` |
| `hub` | string | ✓ | Announcing hub name |
| `address` | string | ✓ | Hub's federation address |
| `pubkey` | string | | Public key (MeshPass, future) |
| `timestamp` | string | ✓ | ISO timestamp |
| `signature` | string | | Message signature (future) |
| `capabilityBloom` | object | | Bloom filter of hub capabilities |

#### `peer_bye`
**Direction:** hub → hub

Graceful disconnection notice.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | string | ✓ | `"peer_bye"` |
| `hub` | string | ✓ | Departing hub name |
| `timestamp` | string | ✓ | ISO timestamp |

---

### Capability Query

#### `capability_query`
**Direction:** any → hub

Search for agents with a specific capability.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | string | ✓ | `"capability_query"` |
| `capability` | string | ✓ | Capability to search for |
| `minPressure` | number | | Minimum dark circle pressure filter |
| `requestId` | string | ✓ | Correlation ID |

#### `capability_response`
**Direction:** hub → requester

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | string | ✓ | `"capability_response"` |
| `requestId` | string | ✓ | Correlates to query |
| `agents` | AgentInfo[] | ✓ | Matching agents |

**AgentInfo:**
| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Agent name |
| `hub` | string | Hub name |
| `capabilities` | string[] | Capability list |
| `pressure` | number | Dark circle pressure |
| `seams` | string[] | Domain seams |
| `lastSeen` | string | ISO timestamp |

---

### Agent Request (Phase 1)

#### `agent_request`
**Direction:** client → hub

Direct request to a specific agent.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | string | ✓ | `"agent_request"` |
| `target` | string | ✓ | `"agent@hub"` or `"agent"` (local) |
| `task` | WorkPayload | ✓ | Arbitrary work payload |
| `timeout` | number | | Timeout in ms (default 30000) |
| `requestId` | string | ✓ | Correlation ID |

#### `agent_response`
**Direction:** hub → client

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | string | ✓ | `"agent_response"` |
| `requestId` | string | ✓ | Correlates to request |
| `success` | boolean | ✓ | Whether task succeeded |
| `result` | any | | Response data |
| `error` | string | | Error message if failed |

---

### Task Execution (Phase 2)

#### `task_request`
**Direction:** hub → runner, or hub → hub (forwarded)

Structured task with routing semantics.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | string | ✓ | `"task_request"` |
| `task` | TaskRequest | ✓ | Task object |

**TaskRequest:**
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | ✓ | UUID v4 |
| `target` | string | ✓ | `"name@hub"`, `"name"`, or `"any"` |
| `capability` | string | | Required capability (when target is "any") |
| `command` | string | ✓ | Agent command to execute |
| `args` | object | | Command arguments |
| `timeout_ms` | number | | Timeout (default 30000) |
| `origin` | string | ✓ | Origin hub name |
| `caller` | string | ✓ | Caller identity |
| `created_at` | string | ✓ | ISO timestamp |
| `teacup` | object | | Context: `{trigger, ground_state?, observation?}` |

#### `task_result`
**Direction:** runner → hub

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | string | ✓ | `"task_result"` |
| `result` | TaskResult | ✓ | Result object |

**TaskResult:**
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | ✓ | Matches TaskRequest.id |
| `status` | string | ✓ | `"success"` \| `"error"` \| `"timeout"` \| `"not_found"` \| `"rejected"` |
| `output` | any | | Agent output |
| `error` | string | | Error message |
| `executed_by` | string | | Agent that executed |
| `execution_ms` | number | | Wall-clock time |
| `completed_at` | string | ✓ | ISO timestamp |

#### `task_ack`
**Direction:** hub → submitter

Acknowledgment that task was received and queued.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | string | ✓ | `"task_ack"` |
| `task_id` | string | ✓ | Task ID |
| `queue_position` | number | | Position in queue (0 = immediate) |

#### `task_forward`
**Direction:** hub → hub (store-and-forward relay)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | string | ✓ | `"task_forward"` |
| `task` | TaskRequest | ✓ | Original task |
| `hopCount` | number | ✓ | Hops taken so far |
| `maxHops` | number | ✓ | Maximum allowed hops |
| `originHub` | string | ✓ | Original sender hub |

---

### Agent Registration

#### `agent_runner_ready`
**Direction:** runner → hub (local WS)

Announces agents available on a runner.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | string | ✓ | `"agent_runner_ready"` |
| `hub` | string | | Hub name |
| `agents` | array | ✓ | Agent definitions (see below) |

**Agent definitions** (union type):
```json
// Option 1: object (recommended)
{"name": "my-agent", "capabilities": ["cap1", "cap2"], "seams": ["domain1"]}

// Option 2: string (legacy)
"my-agent"
```

---

### Mesh Sync

#### `mesh_sync`
**Direction:** hub → hub, hub → client

Full snapshot of a hub's state.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | string | ✓ | `"mesh_sync"` |
| `hub` | string | ✓ | Hub name |
| `version` | number | | Monotonic version counter |
| `agents` | AgentInfo[] | ✓ | All agents on this hub |
| `darkCircles` | DarkCircle[] | ✓ | Active dark circles |
| `timestamp` | string | ✓ | ISO timestamp |

#### `mesh_delta`
**Direction:** hub → hub

Incremental update (only changes since last version).

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | string | ✓ | `"mesh_delta"` |
| `hub` | string | ✓ | Hub name |
| `fromVersion` | number | ✓ | Previous version |
| `toVersion` | number | ✓ | New version |
| `agentDeltas` | AgentDelta[] | ✓ | Agent changes |
| `darkCircleDeltas` | DarkCircleDelta[] | ✓ | Dark circle changes |
| `timestamp` | string | ✓ | ISO timestamp |

**AgentDelta:** `{ op: "upsert" | "remove", agent: AgentInfo }`
**DarkCircleDelta:** `{ op: "upsert" | "remove", circle: DarkCircle, hub: string }`

#### `mesh_delta_ack`
**Direction:** hub → hub

Confirms delta was processed.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | string | ✓ | `"mesh_delta_ack"` |
| `hub` | string | ✓ | Acknowledging hub |
| `version` | number | ✓ | Version acknowledged |

---

### Detection Coordination (Phase 3)

#### `detection_claim`
**Direction:** agent → hub → federation

A detection agent posts a claim.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | ✓ | Claim ID |
| `source` | string | ✓ | Detector identity (`"name@hub"`) |
| `domain` | string | ✓ | `"solar"` \| `"market"` \| `"mesh"` \| `"security"` \| `"deployment"` |
| `summary` | string | ✓ | Human-readable summary |
| `confidence` | number | ✓ | 0–1 |
| `evidence_hash` | string | ✓ | SHA-256 hash of evidence |
| `created_at` | string | ✓ | ISO timestamp |
| `ttl_seconds` | number | | Time to live |
| `evidence` | object | | Structured evidence |

#### `detection_verify`
**Direction:** agent → hub

Peer verification of a claim.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `claim_id` | string | ✓ | Claim being verified |
| `verifier` | string | ✓ | Verifier identity |
| `agrees` | boolean | ✓ | Confirms or disputes |

#### `detection_challenge`
**Direction:** agent → hub

Challenge a claim with counter-evidence.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `claim_id` | string | ✓ | Claim being challenged |
| `challenger` | string | ✓ | Challenger identity |
| `counter_evidence` | object | ✓ | Counter-evidence |

#### `detection_outcome`
**Direction:** agent → hub

Final resolution of a claim.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `claim_id` | string | ✓ | Claim being resolved |
| `status` | string | ✓ | `"confirmed"` \| `"refuted"` \| `"expired"` |
| `resolved_by` | string | ✓ | Resolver identity |

---

### Control

#### `ping` / `pong`
**Direction:** any ↔ any

Keep-alive. Both carry `timestamp`.

#### `error`
**Direction:** hub → any

Error response.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `code` | string | ✓ | Error code |
| `message` | string | ✓ | Human-readable message |
| `requestId` | string | | Related request ID |

---

### Gossip (Shuffle)

Shuffle messages (`shuffle_request` / `shuffle_response`) are used for peer sampling in GossipSub. These bypass the Zod parser and are handled at the transport layer.
