// Federation protocol message types

export type MessageType =
  | 'peer_announce'
  | 'peer_bye'
  | 'capability_query'
  | 'capability_response'
  | 'agent_request'
  | 'agent_response'
  | 'mesh_sync'
  | 'ping'
  | 'pong'
  | 'error'

export interface BaseMessage {
  type: MessageType
  requestId?: string
  timestamp?: string
}

// ── Peer Discovery ─────────────────────────────────────────────────────────────

export interface PeerAnnounceMessage extends BaseMessage {
  type: 'peer_announce'
  hub: string
  address: string
  pubkey?: string
  timestamp: string
  signature?: string
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
  target: string
  task: WorkPayload
  timeout?: number
  requestId: string
}

export interface AgentResponseMessage extends BaseMessage {
  type: 'agent_response'
  requestId: string
  success: boolean
  result?: unknown
  error?: string
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
  agents: AgentInfo[]
  darkCircles: DarkCircle[]
  timestamp: string
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

export type FederationMessage =
  | PeerAnnounceMessage
  | PeerByeMessage
  | CapabilityQueryMessage
  | CapabilityResponseMessage
  | AgentRequestMessage
  | AgentResponseMessage
  | MeshSyncMessage
  | PingMessage
  | PongMessage
  | ErrorMessage
