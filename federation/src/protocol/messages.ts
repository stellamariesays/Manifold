// Federation protocol message types

export type MessageType =
  | 'peer_announce'
  | 'peer_bye'
  | 'capability_query'
  | 'capability_response'
  | 'agent_request'
  | 'agent_response'
  | 'task_request'
  | 'task_result'
  | 'task_ack'
  | 'task_forward'
  | 'mesh_sync'
  | 'mesh_delta'
  | 'mesh_delta_ack'
  | 'ping'
  | 'pong'
  | 'error'
  // Phase 3: Detection-Coordination
  | 'detection_claim'
  | 'detection_verify'
  | 'detection_challenge'
  | 'detection_outcome'
  // Phase 1: MeshPass Identity
  | 'mesh_identity_announce'
  | 'mesh_identity_verify'
  | 'mesh_auth'

export interface BaseMessage {
  type: MessageType
  requestId?: string
  timestamp?: string
  /** Sender MeshID (name@hub) if authenticated */
  sender?: string
  /** Sender public key for signature verification */
  senderPublicKey?: string
  /** Gateway hub that relayed this message */
  gatewayHub?: string
  /** Message signature (hex) from sender's MeshPass */
  signature?: string
}

// ── Peer Discovery ─────────────────────────────────────────────────────────────

export interface PeerAnnounceMessage extends BaseMessage {
  type: 'peer_announce'
  hub: string
  address: string
  pubkey?: string
  timestamp: string
  signature?: string
  /** Bloom filter of hub capabilities (optional, for scaling) */
  capabilityBloom?: { size: number; hashCount: number; bits: string }
}

export interface PeerByeMessage extends BaseMessage {
  type: 'peer_bye'
  hub: string
  timestamp: string
}

// ── Capability Query ───────────────────────────────────────────────────────────

export interface CapabilityQueryMessage extends BaseMessage {
  type: 'capability_query'
  capability: string
  minPressure?: number
  requestId: string
}

export interface AgentInfo {
  name: string
  hub: string
  capabilities: string[]
  pressure?: number
  seams?: string[]
  lastSeen?: string
  isLocal?: boolean
}

export interface CapabilityResponseMessage extends BaseMessage {
  type: 'capability_response'
  requestId: string
  agents: AgentInfo[]
}

// ── Work Routing ───────────────────────────────────────────────────────────────

export interface WorkPayload {
  type: string
  [key: string]: unknown
}

export interface AgentRequestMessage extends BaseMessage {
  type: 'agent_request'
  target: string          // "agent-name@hub" or "agent-name" (local)
  task: WorkPayload
  timeout?: number        // ms, default 30000
  requestId: string
}

export interface AgentResponseMessage extends BaseMessage {
  type: 'agent_response'
  requestId: string
  success: boolean
  result?: unknown
  error?: string
}

// ── Task Execution (Phase 2) ───────────────────────────────────────────────────
//
// These extend the basic agent_request/response with structured task execution
// semantics: command routing, timeout enforcement, status tracking, and
// cross-hub forwarding.

export interface TaskRequest {
  /** Unique task ID (UUID v4) */
  id: string
  /** Target agent: "name@hub", "name" (local), or "any" with capability filter */
  target: string
  /** Required capability when target is "any" */
  capability?: string
  /** Agent command to execute (e.g. "watch", "audit", "status") */
  command: string
  /** Command arguments */
  args?: Record<string, unknown>
  /** Execution timeout in milliseconds. Default 30000. */
  timeout_ms?: number
  /** Origin hub for cross-hub routing */
  origin: string
  /** Origin caller identity (e.g. "eddie@hog") */
  caller: string
  /** Timestamp when request was created */
  created_at: string
  /** The teacup — concrete context for why this task was submitted */
  teacup?: {
    trigger: string
    ground_state?: string
    observation?: string
  }
}

export interface TaskResult {
  /** Matches TaskRequest.id */
  id: string
  /** "success" | "error" | "timeout" | "not_found" | "rejected" */
  status: 'success' | 'error' | 'timeout' | 'not_found' | 'rejected'
  /** Agent's JSON output (structured, agent-defined schema) */
  output?: unknown
  /** Human-readable error message if status != "success" */
  error?: string
  /** Which agent actually executed the task (may differ from target if routed) */
  executed_by?: string
  /** Wall-clock execution time in ms */
  execution_ms?: number
  /** Timestamp when result was produced */
  completed_at: string
}

export interface TaskRequestMessage extends BaseMessage {
  type: 'task_request'
  task: TaskRequest
}

export interface TaskResultMessage extends BaseMessage {
  type: 'task_result'
  result: TaskResult
}

/** Acknowledgment that a task was received and queued for execution */
export interface TaskAckMessage extends BaseMessage {
  type: 'task_ack'
  task_id: string
  /** Estimated queue position (0 = executing immediately) */
  queue_position?: number
}

/** Store-and-forward: relay a task toward its destination through the mesh */
export interface TaskForwardMessage extends BaseMessage {
  type: 'task_forward'
  task: TaskRequest
  /** Hops taken so far (prevents infinite loops) */
  hopCount: number
  /** Max hops allowed */
  maxHops: number
  /** Original sender hub */
  originHub: string
}

// ── Mesh Sync ──────────────────────────────────────────────────────────────────

export interface DarkCircle {
  name: string
  pressure: number
  hub?: string
}

export interface MeshSyncMessage extends BaseMessage {
  type: 'mesh_sync'
  hub: string
  /** Monotonic version counter (set by delta sync) */
  version?: number
  agents: AgentInfo[]
  darkCircles: DarkCircle[]
  timestamp: string
}

/** Extended mesh sync with delta versioning support */
export interface MeshSyncMessageV2 extends MeshSyncMessage {
  version: number
}

// ── Delta Sync ────────────────────────────────────────────────────────────────

export interface AgentDelta {
  op: 'upsert' | 'remove'
  agent: AgentInfo
}

export interface DarkCircleDelta {
  op: 'upsert' | 'remove'
  circle: DarkCircle
  hub: string
}

/** Delta-only sync — only changes since fromVersion */
export interface MeshDeltaMessage extends BaseMessage {
  type: 'mesh_delta'
  hub: string
  fromVersion: number
  toVersion: number
  agentDeltas: AgentDelta[]
  darkCircleDeltas: DarkCircleDelta[]
  timestamp: string
}

/** ACK from peer confirming they processed a version */
export interface MeshDeltaAckMessage extends BaseMessage {
  type: 'mesh_delta_ack'
  hub: string
  version: number
}

// ── Control ────────────────────────────────────────────────────────────────────

export interface PingMessage extends BaseMessage {
  type: 'ping'
  timestamp: string
}

export interface PongMessage extends BaseMessage {
  type: 'pong'
  timestamp: string
}

export interface ErrorMessage extends BaseMessage {
  type: 'error'
  code: string
  message: string
  requestId?: string
}

// ── Union ──────────────────────────────────────────────────────────────────────

// ── Detection Coordination (Phase 3) ────────────────────────────────────────
//
// Propagates detection claims across the federation mesh.
// Detectors post claims, validators verify or challenge, outcomes close the loop.

export interface DetectionClaim {
  /** Unique claim ID */
  id: string
  /** Detector that made the claim: "detector-name@hub" */
  source: string
  /** Domain: "solar", "market", "mesh", "security", "deployment" */
  domain: string
  /** Human-readable summary */
  summary: string
  /** Confidence 0-1 */
  confidence: number
  /** SHA-256 hash of supporting evidence (data fingerprint, not raw data) */
  evidence_hash: string
  /** ISO timestamp */
  created_at: string
  /** Optional: TTL in seconds before claim expires */
  ttl_seconds?: number
  /** Optional: structured evidence payload */
  evidence?: Record<string, unknown>
}

export interface DetectionVerify {
  /** Claim being verified */
  claim_id: string
  /** Verifier identity */
  verifier: string
  /** Agreement: true = confirms, false = disputes */
  agrees: boolean
  /** Verifier's own confidence 0-1 */
  confidence: number
  /** Optional notes */
  notes?: string
  /** ISO timestamp */
  verified_at: string
}

export interface DetectionChallenge {
  /** Claim being challenged */
  claim_id: string
  /** Challenger identity */
  challenger: string
  /** Reason for challenge */
  reason: string
  /** Counter-evidence hash */
  counter_evidence_hash?: string
  /** ISO timestamp */
  challenged_at: string
}

export interface DetectionOutcome {
  /** Original claim ID */
  claim_id: string
  /** "confirmed" | "false_positive" | "expired" | "superseded" */
  outcome: 'confirmed' | 'false_positive' | 'expired' | 'superseded'
  /** Agent or human that determined the outcome */
  resolved_by: string
  /** ISO timestamp */
  resolved_at: string
  /** Optional outcome notes */
  notes?: string
  /** Superseding claim ID if outcome is "superseded" */
  superseded_by?: string
}

export interface DetectionClaimMessage extends BaseMessage {
  type: 'detection_claim'
  claim: DetectionClaim
}

export interface DetectionVerifyMessage extends BaseMessage {
  type: 'detection_verify'
  verification: DetectionVerify
}

export interface DetectionChallengeMessage extends BaseMessage {
  type: 'detection_challenge'
  challenge: DetectionChallenge
}

export interface DetectionOutcomeMessage extends BaseMessage {
  type: 'detection_outcome'
  outcome: DetectionOutcome
}

// ── MeshPass Identity (Phase 1) ──────────────────────────────────────────────
//
// Cryptographic identity and mesh authentication using Ed25519 signatures.

export interface MeshIdentityAnnounce {
  /** MeshID in name@hub format */
  meshId: string
  /** Ed25519 public key (hex) */
  publicKey: string
  /** Hub where this identity is registered */
  hub: string
  /** Capabilities this identity claims */
  capabilities?: string[]
  /** Registration timestamp */
  registeredAt: string
  /** Optional identity metadata */
  metadata?: Record<string, unknown>
}

export interface MeshIdentityVerify {
  /** MeshID being verified */
  meshId: string
  /** Challenge nonce to sign */
  nonce: string
  /** Verifier identity */
  verifier: string
  /** Timestamp */
  verifyAt: string
}

export interface MeshAuthRequest {
  /** MeshID requesting authentication */
  meshId: string
  /** Random nonce for this auth request */
  nonce: string
  /** Timestamp */
  timestamp: string
  /** Signature of "AUTH:{meshId}:{nonce}:{timestamp}" */
  signature: string
}

export interface MeshIdentityAnnounceMessage extends BaseMessage {
  type: 'mesh_identity_announce'
  identity: MeshIdentityAnnounce
}

export interface MeshIdentityVerifyMessage extends BaseMessage {
  type: 'mesh_identity_verify'
  verification: MeshIdentityVerify
}

export interface MeshAuthMessage extends BaseMessage {
  type: 'mesh_auth'
  auth: MeshAuthRequest
}

export type FederationMessage =
  | PeerAnnounceMessage
  | PeerByeMessage
  | CapabilityQueryMessage
  | CapabilityResponseMessage
  | AgentRequestMessage
  | AgentResponseMessage
  | TaskRequestMessage
  | TaskResultMessage
  | TaskAckMessage
  | MeshSyncMessage
  | MeshSyncMessageV2
  | MeshDeltaMessage
  | MeshDeltaAckMessage
  | PingMessage
  | PongMessage
  | ErrorMessage
  // Phase 3
  | DetectionClaimMessage
  | DetectionVerifyMessage
  | DetectionChallengeMessage
  | DetectionOutcomeMessage
  // Phase 1: MeshPass
  | MeshIdentityAnnounceMessage
  | MeshIdentityVerifyMessage
  | MeshAuthMessage
