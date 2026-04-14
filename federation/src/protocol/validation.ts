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

// ── Discriminated union validator ──────────────────────────────────────────────

const FederationMessageSchema = z.discriminatedUnion('type', [
  PeerAnnounceSchema,
  PeerByeSchema,
  CapabilityQuerySchema,
  CapabilityResponseSchema,
  AgentRequestSchema,
  AgentResponseSchema,
  MeshSyncSchema,
  PingSchema,
  PongSchema,
  ErrorSchema,
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
