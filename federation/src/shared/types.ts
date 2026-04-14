// Shared types across client and server

export interface Identity {
  name: string
  pubkey?: string
}

export interface AgentRegistration {
  name: string
  capabilities: string[]
  seams?: string[]
  pressure?: number
}

export interface QueryOptions {
  /** Minimum dark circle pressure to filter by */
  minPressure?: number
  /** Search local mesh first before federation */
  local?: boolean
  /** Query timeout in milliseconds */
  timeoutMs?: number
}

export interface AgentResult {
  /** Agent name, e.g. "braid@trillian" */
  name: string
  hub: string
  capabilities: string[]
  pressure?: number
  seams?: string[]
  lastSeen?: string
  /** Whether this agent is on the local hub */
  isLocal?: boolean
}

export interface WorkRequest {
  type: string
  payload?: Record<string, unknown>
  [key: string]: unknown
}

export interface RouteOptions {
  timeout?: number
}

export interface PeerInfo {
  hub: string
  address: string
  pubkey?: string
  connectedAt: string
  lastSeen: string
  /** Number of agents known on this peer */
  agentCount: number
}

export interface DarkCircleInfo {
  name: string
  /** Aggregated pressure across all hubs */
  pressure: number
  /** Per-hub breakdown */
  byHub?: Record<string, number>
}

export interface MeshStatus {
  hub: string
  localAgents: AgentResult[]
  federatedAgents: AgentResult[]
  peers: PeerInfo[]
  darkCircles: DarkCircleInfo[]
  uptime: number
  timestamp: string
}

// Event maps ────────────────────────────────────────────────────────────────────

export interface ClientEvents {
  'agent:join': (agent: AgentResult) => void
  'agent:leave': (agent: Pick<AgentResult, 'name' | 'hub'>) => void
  'capability:change': (event: { agent: string; added: string[]; removed: string[] }) => void
  'pressure:update': (event: { circle: string; pressure: number; hub: string }) => void
  'peer:connect': (peer: PeerInfo) => void
  'peer:disconnect': (peer: Pick<PeerInfo, 'hub'>) => void
  'error': (err: Error) => void
  'connected': () => void
  'disconnected': () => void
}

export interface ServerEvents {
  'peer:connect': (peer: PeerInfo) => void
  'peer:disconnect': (peer: Pick<PeerInfo, 'hub'>) => void
  'agent:join': (agent: AgentResult) => void
  'agent:leave': (agent: Pick<AgentResult, 'name' | 'hub'>) => void
  'mesh:sync': (hub: string) => void
  'error': (err: Error) => void
}
