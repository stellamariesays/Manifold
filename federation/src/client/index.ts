import { EventEmitter } from 'events'
import { v4 as uuid } from 'uuid'
import { createNodeSocket, ManagedSocket } from './websocket.js'
import { parseMessage } from '../protocol/validation.js'
import type {
  FederationMessage,
  AgentInfo,
  MeshSyncMessage,
  CapabilityResponseMessage,
  AgentResponseMessage,
} from '../protocol/messages.js'
import type {
  ManifoldClientConfig,
  PendingRequest,
  PendingWorkRequest,
} from './types.js'
import type {
  AgentResult,
  ClientEvents,
  QueryOptions,
  RouteOptions,
} from '../shared/types.js'

export type { ManifoldClientConfig } from './types.js'
export type { AgentResult, QueryOptions, RouteOptions } from '../shared/types.js'

type EventName = keyof ClientEvents

export class ManifoldClient extends EventEmitter {
  private readonly config: Required<ManifoldClientConfig>
  private sockets: Map<string, ManagedSocket> = new Map()

  /** All agents known to this client, keyed by "name@hub" */
  private agentIndex: Map<string, AgentResult> = new Map()

  /** Pending capability queries keyed by requestId */
  private pendingQueries: Map<string, PendingRequest> = new Map()

  /** Pending work requests keyed by requestId */
  private pendingWork: Map<string, PendingWorkRequest> = new Map()

  /** Own registered capabilities */
  private ownCapabilities: string[] = []

  private started = false

  constructor(config: ManifoldClientConfig) {
    super()
    this.config = {
      reconnectDelay: 5000,
      maxReconnectAttempts: Infinity,
      defaultQueryTimeout: 10000,
      debug: false,
      ...config,
    }
  }

  // ── Lifecycle ───────────────────────────────────────────────────────────────

  async start(): Promise<void> {
    if (this.started) return
    this.started = true

    for (const url of this.config.servers) {
      await this._connectToServer(url)
    }
  }

  async stop(): Promise<void> {
    for (const sock of this.sockets.values()) {
      sock.close()
    }
    this.sockets.clear()
    this.started = false
  }

  // ── Public API ──────────────────────────────────────────────────────────────

  /**
   * Register this agent's capabilities with all connected servers.
   */
  async register(capabilities: string[], seams?: string[]): Promise<void> {
    this.ownCapabilities = capabilities

    const msg: MeshSyncMessage = {
      type: 'mesh_sync',
      hub: this.config.identity.name,
      agents: [
        {
          name: this.config.identity.name,
          hub: this.config.identity.name,
          capabilities,
          seams: seams ?? [],
        },
      ],
      darkCircles: [],
      timestamp: new Date().toISOString(),
    }

    this._broadcast(JSON.stringify(msg))
  }

  /**
   * Query for agents by capability, optionally filtered by pressure.
   * Searches local agent index immediately, then queries federation servers.
   */
  async query(capability: string, options?: QueryOptions): Promise<AgentResult[]> {
    const {
      minPressure,
      local = false,
      timeoutMs = this.config.defaultQueryTimeout,
    } = options ?? {}

    // Collect results: local first, then federated
    const localResults = this._queryLocal(capability, minPressure)

    if (local) {
      return localResults
    }

    // Fan out capability query to all connected servers
    const requestId = uuid()
    const federatedResults = await this._queryFederation(capability, minPressure, requestId, timeoutMs)

    // Merge, dedup by name@hub
    const merged = new Map<string, AgentResult>()
    for (const a of [...localResults, ...federatedResults]) {
      merged.set(`${a.name}@${a.hub}`, a)
    }

    return Array.from(merged.values())
  }

  /**
   * Route a work request to a specific agent.
   * Target format: "agentName@hubName" or just "agentName" (sent to first match).
   */
  async routeWork(
    target: string,
    task: { type?: string; [key: string]: unknown },
    options?: RouteOptions,
  ): Promise<unknown> {
    const requestId = uuid()
    const timeout = options?.timeout ?? 30

    const msg = {
      type: 'agent_request' as const,
      target,
      task: { type: task.type ?? 'generic', ...task },
      timeout,
      requestId,
    }

    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pendingWork.delete(requestId)
        reject(new Error(`Work request to ${target} timed out after ${timeout}s`))
      }, timeout * 1000)

      this.pendingWork.set(requestId, { resolve, reject, timer })
      const sent = this._broadcast(JSON.stringify(msg))

      if (!sent) {
        clearTimeout(timer)
        this.pendingWork.delete(requestId)
        reject(new Error('No connected servers to route work to'))
      }
    })
  }

  /**
   * Get all known agents (local + federated).
   */
  getAgents(): AgentResult[] {
    return Array.from(this.agentIndex.values())
  }

  /**
   * Get connected server URLs.
   */
  getConnectedServers(): string[] {
    return Array.from(this.sockets.entries())
      .filter(([, s]) => s.isConnected)
      .map(([url]) => url)
  }

  // Typed emit/on for strict event types
  emit<K extends EventName>(event: K, ...args: Parameters<ClientEvents[K]>): boolean {
    return super.emit(event, ...args)
  }

  on<K extends EventName>(event: K, listener: ClientEvents[K]): this {
    return super.on(event, listener)
  }

  // ── Private ─────────────────────────────────────────────────────────────────

  private async _connectToServer(url: string): Promise<void> {
    const sock = await createNodeSocket(url, {
      reconnectDelay: this.config.reconnectDelay,
      maxReconnectAttempts: this.config.maxReconnectAttempts,
      debug: this.config.debug,
    })

    this.sockets.set(url, sock)

    sock.on('open', () => {
      this._log(`Connected to ${url}`)
      this.emit('connected')
      // Announce self
      if (this.ownCapabilities.length > 0) {
        this.register(this.ownCapabilities).catch(() => {})
      }
    })

    sock.on('message', (data: unknown) => {
      const raw = typeof data === 'string' ? data : String(data)
      const msg = parseMessage(raw)
      if (msg) this._handleMessage(msg, url)
    })

    sock.on('close', () => {
      this._log(`Disconnected from ${url}`)
      this.emit('disconnected')
    })

    sock.on('error', (err: Error) => {
      this._log(`Error on ${url}: ${err.message}`)
    })

    sock.connect()
  }

  private _handleMessage(msg: FederationMessage, _fromUrl: string): void {
    switch (msg.type) {
      case 'mesh_sync':
        this._handleMeshSync(msg)
        break
      case 'capability_response':
        this._handleCapabilityResponse(msg)
        break
      case 'agent_response':
        this._handleAgentResponse(msg)
        break
      case 'ping':
        this._sendTo(_fromUrl, JSON.stringify({ type: 'pong', timestamp: new Date().toISOString() }))
        break
      case 'peer_announce':
        this._log(`Peer announced: ${msg.hub} at ${msg.address}`)
        break
      default:
        break
    }
  }

  private _handleMeshSync(msg: MeshSyncMessage): void {
    const prevAgents = new Set(
      Array.from(this.agentIndex.values())
        .filter(a => a.hub === msg.hub)
        .map(a => `${a.name}@${a.hub}`),
    )

    const incoming = new Set<string>()

    for (const agent of msg.agents) {
      const key = `${agent.name}@${agent.hub}`
      incoming.add(key)

      const prev = this.agentIndex.get(key)
      const result: AgentResult = {
        ...agent,
        lastSeen: new Date().toISOString(),
        isLocal: agent.hub === this.config.identity.name,
      }

      if (!prev) {
        this.agentIndex.set(key, result)
        this.emit('agent:join', result)
      } else {
        // Check capability changes
        const added = agent.capabilities.filter(c => !prev.capabilities.includes(c))
        const removed = prev.capabilities.filter(c => !agent.capabilities.includes(c))
        if (added.length > 0 || removed.length > 0) {
          this.emit('capability:change', { agent: key, added, removed })
        }
        this.agentIndex.set(key, result)
      }
    }

    // Agents that disappeared from this hub
    for (const key of prevAgents) {
      if (!incoming.has(key)) {
        const agent = this.agentIndex.get(key)!
        this.agentIndex.delete(key)
        this.emit('agent:leave', { name: agent.name, hub: agent.hub })
      }
    }

    // Emit pressure updates for dark circles
    for (const dc of msg.darkCircles) {
      this.emit('pressure:update', {
        circle: dc.name,
        pressure: dc.pressure,
        hub: msg.hub,
      })
    }
  }

  private _handleCapabilityResponse(msg: CapabilityResponseMessage): void {
    const pending = this.pendingQueries.get(msg.requestId)
    if (!pending) return

    clearTimeout(pending.timer)
    this.pendingQueries.delete(msg.requestId)

    const results: AgentResult[] = msg.agents.map(a => ({
      ...a,
      isLocal: a.hub === this.config.identity.name,
    }))
    pending.resolve(results)
  }

  private _handleAgentResponse(msg: AgentResponseMessage): void {
    const pending = this.pendingWork.get(msg.requestId)
    if (!pending) return

    clearTimeout(pending.timer)
    this.pendingWork.delete(msg.requestId)

    if (msg.success) {
      pending.resolve(msg.result)
    } else {
      pending.reject(new Error(msg.error ?? 'Agent request failed'))
    }
  }

  private _queryLocal(capability: string, minPressure?: number): AgentResult[] {
    return Array.from(this.agentIndex.values()).filter(a => {
      if (!a.capabilities.includes(capability)) return false
      if (minPressure !== undefined && (a.pressure ?? 0) < minPressure) return false
      return true
    })
  }

  private _queryFederation(
    capability: string,
    minPressure: number | undefined,
    requestId: string,
    timeoutMs: number,
  ): Promise<AgentResult[]> {
    return new Promise<AgentResult[]>((resolve, reject) => {
      const msg = {
        type: 'capability_query' as const,
        capability,
        minPressure,
        requestId,
      }

      const timer = setTimeout(() => {
        this.pendingQueries.delete(requestId)
        // On timeout, resolve with empty (don't reject — local results are still usable)
        resolve([])
      }, timeoutMs)

      this.pendingQueries.set(requestId, {
        resolve: (agents: AgentInfo[] | AgentResult[]) => resolve(agents as AgentResult[]),
        reject,
        timer,
      } as unknown as PendingRequest)

      const sent = this._broadcast(JSON.stringify(msg))
      if (!sent) {
        clearTimeout(timer)
        this.pendingQueries.delete(requestId)
        resolve([])
      }
    })
  }

  private _broadcast(data: string): boolean {
    let sent = false
    for (const sock of this.sockets.values()) {
      if (sock.send(data)) sent = true
    }
    return sent
  }

  private _sendTo(url: string, data: string): void {
    this.sockets.get(url)?.send(data)
  }

  private _log(msg: string): void {
    if (this.config.debug) console.log(`[ManifoldClient:${this.config.identity.name}] ${msg}`)
  }
}
