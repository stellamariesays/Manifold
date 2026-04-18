import { z } from 'zod'
import type { FederationMessage } from './messages.js'

// ── Shared schemas ─────────────────────────────────────────────────────────────

const AgentInfoSchema = z.object({
  name: z.string(),
  hub: z.string(),
  capabilities: z.array(z.string()),
  pressure: z.number().min(0).max(1).optional(),
  seams: z.array(z.string()).optional(),
  lastSeen: z.string().optional(),
})

const DarkCircleSchema = z.object({
  name: z.string(),
  pressure: z.number().min(0).max(1),
  hub: z.string().optional(),
})

const WorkPayloadSchema = z.object({
  type: z.string(),
}).passthrough()

// ── Message schemas ────────────────────────────────────────────────────────────

const PeerAnnounceSchema = z.object({
  type: z.literal('peer_announce'),
  hub: z.string(),
  address: z.string().url(),
  pubkey: z.string().optional(),
  timestamp: z.string(),
  signature: z.string().optional(),
  requestId: z.string().optional(),
  capabilityBloom: z.object({
    size: z.number(),
    hashCount: z.number(),
    bits: z.string(),
  }).optional(),
})

const PeerByeSchema = z.object({
  type: z.literal('peer_bye'),
  hub: z.string(),
  timestamp: z.string(),
  requestId: z.string().optional(),
})

const CapabilityQuerySchema = z.object({
  type: z.literal('capability_query'),
  capability: z.string(),
  minPressure: z.number().min(0).max(1).optional(),
  requestId: z.string(),
})

const CapabilityResponseSchema = z.object({
  type: z.literal('capability_response'),
  requestId: z.string(),
  agents: z.array(AgentInfoSchema),
})

const AgentRequestSchema = z.object({
  type: z.literal('agent_request'),
  target: z.string(),
  task: WorkPayloadSchema,
  timeout: z.number().positive().optional(),
  requestId: z.string(),
})

const AgentResponseSchema = z.object({
  type: z.literal('agent_response'),
  requestId: z.string(),
  success: z.boolean(),
  result: z.unknown().optional(),
  error: z.string().optional(),
})

const MeshSyncSchema = z.object({
  type: z.literal('mesh_sync'),
  hub: z.string(),
  agents: z.array(AgentInfoSchema),
  darkCircles: z.array(DarkCircleSchema),
  timestamp: z.string(),
  version: z.number().optional(), // V2: version for delta sync
  requestId: z.string().optional(),
})

const AgentDeltaSchema = z.object({
  op: z.enum(['upsert', 'remove']),
  agent: AgentInfoSchema,
})

const DarkCircleDeltaSchema = z.object({
  op: z.enum(['upsert', 'remove']),
  circle: DarkCircleSchema,
  hub: z.string(),
})

const MeshDeltaSchema = z.object({
  type: z.literal('mesh_delta'),
  hub: z.string(),
  fromVersion: z.number(),
  toVersion: z.number(),
  agentDeltas: z.array(AgentDeltaSchema),
  darkCircleDeltas: z.array(DarkCircleDeltaSchema),
  timestamp: z.string(),
  requestId: z.string().optional(),
})

const MeshDeltaAckSchema = z.object({
  type: z.literal('mesh_delta_ack'),
  hub: z.string(),
  version: z.number(),
  requestId: z.string().optional(),
})

const PingSchema = z.object({
  type: z.literal('ping'),
  timestamp: z.string(),
  requestId: z.string().optional(),
})

const PongSchema = z.object({
  type: z.literal('pong'),
  timestamp: z.string(),
  requestId: z.string().optional(),
})

const ErrorSchema = z.object({
  type: z.literal('error'),
  code: z.string(),
  message: z.string(),
  requestId: z.string().optional(),
})

// ── Phase 2: Task Execution schemas ────────────────────────────────────────────

const TaskRequestSchema = z.object({
  type: z.literal('task_request'),
  task: z.object({
    id: z.string(),
    target: z.string(),
    capability: z.string().optional(),
    command: z.string(),
    args: z.record(z.unknown()).optional(),
    timeout_ms: z.number().positive().optional(),
    origin: z.string().optional(),
    caller: z.string().optional(),
    created_at: z.string().optional(),
    teacup: z.object({
      trigger: z.string(),
      ground_state: z.string().optional(),
      observation: z.string().optional(),
    }).optional(),
  }),
})

const TaskResultSchema = z.object({
  type: z.literal('task_result'),
  result: z.object({
    id: z.string(),
    status: z.enum(['success', 'error', 'timeout', 'not_found', 'rejected']),
    output: z.unknown().optional(),
    error: z.string().optional(),
    executed_by: z.string().optional(),
    execution_ms: z.number().optional(),
    completed_at: z.string(),
  }),
})

const TaskAckSchema = z.object({
  type: z.literal('task_ack'),
  task_id: z.string(),
  queue_position: z.number().optional(),
})

const AgentRunnerReadySchema = z.object({
  type: z.literal('agent_runner_ready'),
  hub: z.string().optional(),
  agents: z.array(z.string()),
})

// ── Phase 3: Detection-Coordination schemas ────────────────────────────────────

const DetectionClaimSchema = z.object({
  id: z.string(),
  source: z.string(),
  domain: z.string(),
  summary: z.string(),
  confidence: z.number().min(0).max(1),
  evidence_hash: z.string(),
  created_at: z.string(),
  ttl_seconds: z.number().positive().optional(),
  evidence: z.record(z.unknown()).optional(),
})

const DetectionVerifySchema = z.object({
  claim_id: z.string(),
  verifier: z.string(),
  agrees: z.boolean(),
  confidence: z.number().min(0).max(1),
  notes: z.string().optional(),
  verified_at: z.string(),
})

const DetectionChallengeSchema = z.object({
  claim_id: z.string(),
  challenger: z.string(),
  reason: z.string(),
  counter_evidence_hash: z.string().optional(),
  challenged_at: z.string(),
})

const DetectionOutcomeSchema = z.object({
  claim_id: z.string(),
  outcome: z.enum(['confirmed', 'false_positive', 'expired', 'superseded']),
  resolved_by: z.string(),
  resolved_at: z.string(),
  notes: z.string().optional(),
  superseded_by: z.string().optional(),
})

const DetectionClaimMessageSchema = z.object({
  type: z.literal('detection_claim'),
  claim: DetectionClaimSchema,
})

const DetectionVerifyMessageSchema = z.object({
  type: z.literal('detection_verify'),
  verification: DetectionVerifySchema,
})

const DetectionChallengeMessageSchema = z.object({
  type: z.literal('detection_challenge'),
  challenge: DetectionChallengeSchema,
})

const DetectionOutcomeMessageSchema = z.object({
  type: z.literal('detection_outcome'),
  outcome: DetectionOutcomeSchema,
})

// ── Discriminated union validator ──────────────────────────────────────────────

const FederationMessageSchema = z.discriminatedUnion('type', [
  // Phase 1
  PeerAnnounceSchema,
  PeerByeSchema,
  CapabilityQuerySchema,
  CapabilityResponseSchema,
  AgentRequestSchema,
  AgentResponseSchema,
  MeshSyncSchema,
  MeshDeltaSchema,
  MeshDeltaAckSchema,
  PingSchema,
  PongSchema,
  ErrorSchema,
  // Phase 2
  TaskRequestSchema,
  TaskResultSchema,
  TaskAckSchema,
  AgentRunnerReadySchema,
  // Phase 3
  DetectionClaimMessageSchema,
  DetectionVerifyMessageSchema,
  DetectionChallengeMessageSchema,
  DetectionOutcomeMessageSchema,
])

export function validateMessage(raw: unknown): FederationMessage {
  return FederationMessageSchema.parse(raw) as FederationMessage
}

export function parseMessage(json: string): FederationMessage | null {
  try {
    const raw = JSON.parse(json)
    return validateMessage(raw)
  } catch {
    return null
  }
}

export function isValidMessage(raw: unknown): raw is FederationMessage {
  return FederationMessageSchema.safeParse(raw).success
}
