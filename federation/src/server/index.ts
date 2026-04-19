import { EventEmitter } from 'events'
import { createServer as createHttpServer } from 'http'
import WebSocket, { WebSocketServer } from 'ws'
import { v4 as uuid } from 'uuid'
import { PeerRegistry } from './peer-registry.js'
import { CapabilityIndex } from './capability-index.js'
import { MeshSync } from './mesh-sync.js'
import { RestApi } from './rest-api.js'
import { PythonBridge } from './python-bridge.js'
import { TaskRouter } from './task-router.js'
import { HubCapabilityBloom } from './capability-bloom.js'
import { PersistentCapabilityCache } from './capability-cache.js'
import * as wireCodec from '../protocol/wire-codec.js'
import { TaskHistory } from './task-history.js'
import { MetricsCollector } from './metrics.js'
import { TaskAllowlist, RateLimiter, createAuthMiddleware, type SecurityConfig } from './security.js'
import { DetectionLedger } from './detection-ledger.js'
import { DetectionCoord } from './detection-coord.js'
import { parseMessage } from '../protocol/validation.js'
import type {
  FederationMessage,
  CapabilityQueryMessage,
  AgentRequestMessage,
  MeshSyncMessageV2,
  MeshSyncMessage,
  TaskRequest,
  TaskResult,
} from '../protocol/messages.js'
import type { ServerEvents, MeshStatus, PeerInfo, AgentResult } from '../shared/types.js'
import type { PeerEntry } from './peer-registry.js'
import type { BridgeSnapshot } from './python-bridge.js'

export interface ManifoldServerConfig {
  /** Hub name (e.g. 'trillian', 'hog') */
  name: string

  /** Port for local client connections. Default 8765. */
  localPort?: number

  /** Port for federation WebSocket. Default 8766. */
  federationPort?: number

  /** Port for REST control plane. Default 8767. */
  restPort?: number

  /** Identity */
  identity?: {
    name?: string
    pubkey?: string
  }

  /** Peer federation server addresses to connect to / bootstrap from */
  peers?: string[]

  /** External address to advertise to peers (e.g. ws://100.86.105.39:8766).
   *  If not set, defaults to ws://localhost:{federationPort}. */
  advertiseAddress?: string

  /**
   * Path to Python manifold atlas JSON for local mesh state.
   * If provided, the bridge polls this file and injects agents into the index.
   */
  atlasPath?: string

  /** Mesh sync interval in ms. Default 15000. */
  syncIntervalMs?: number

  /** Whether to expose REST API. Default true. */
  restEnabled?: boolean

  /** Security configuration */
  security?: SecurityConfig

  /** Enable GossipSub peer sampling. Default true. */
  gossipEnabled?: boolean

  /** GossipSub view size (max peers to maintain). Default 8. */
  gossipViewSize?: number

  /** GossipSub shuffle interval in ms. Default 10000. */
  gossipShuffleIntervalMs?: number

  /** Wire format for federation messages: 'json' (default) or 'msgpack'. */
  wireFormat?: 'json' | 'msgpack'

  debug?: boolean
}

type EventName = keyof ServerEvents

export class ManifoldServer extends EventEmitter {
  private readonly config: Required<ManifoldServerConfig>
  readonly hub: string

  private federationWss: WebSocketServer | null = null
  private localWss: WebSocketServer | null = null
  private httpServer: ReturnType<typeof createHttpServer> | null = null

  readonly peerRegistry: PeerRegistry
  readonly capIndex: CapabilityIndex
  readonly meshSync: MeshSync
  readonly restApi: RestApi
  readonly taskRouter: TaskRouter
  readonly taskHistory: TaskHistory
  readonly metrics: MetricsCollector
  readonly allowlist: TaskAllowlist
  /** Hub capability bloom filter */
  hubBloom!: HubCapabilityBloom
  /** Persistent capability cache */
  private capCache!: PersistentCapabilityCache
  readonly rateLimiter: RateLimiter
  readonly detectionCoord: DetectionCoord
  readonly detectionLedger: DetectionLedger
  private pythonBridge: PythonBridge | null = null

  private started = false
  private startTime = 0

  constructor(config: ManifoldServerConfig) {
    super()
    this.config = {
      localPort: 8765,
      federationPort: 8766,
      restPort: 8767,
      identity: {},
      peers: [],
      atlasPath: '',
      advertiseAddress: '',
      syncIntervalMs: 15_000,
      restEnabled: true,
      security: {},
      gossipEnabled: true,
      gossipViewSize: 8,
      gossipShuffleIntervalMs: 10_000,
      wireFormat: 'json' as const,
      debug: false,
      ...config,
    }
    this.hub = config.name

    const selfAddress = this.config.advertiseAddress || `ws://localhost:${this.config.federationPort}`

    this.peerRegistry = new PeerRegistry({
      selfHub: this.hub,
      selfAddress,
      selfPubkey: this.config.identity?.pubkey,
      gossipEnabled: this.config.gossipEnabled,
      gossipViewSize: this.config.gossipViewSize,
      gossipShuffleIntervalMs: this.config.gossipShuffleIntervalMs,
      gossipSeeds: this.config.peers,
      capabilityBloomProvider: () => this.hubBloom?.serialize(),
      debug: this.config.debug,
    })

    this.capIndex = new CapabilityIndex()

    // Capability bloom filter — rebuilt whenever capabilities change
    this.hubBloom = new HubCapabilityBloom({ expectedItems: 200, errorRate: 0.01 })
    this.capCache = new PersistentCapabilityCache({ hub: this.hub })

    this.meshSync = new MeshSync({
      hub: this.hub,
      intervalMs: this.config.syncIntervalMs,
      debug: this.config.debug,
      localBroadcast: (data: string) => {
        this.localWss?.clients.forEach(ws => {
          if (ws.readyState === WebSocket.OPEN) {
            ws.send(data)
          }
        })
      },
    })

    this.restApi = new RestApi({
      hub: this.hub,
      port: this.config.restPort,
      debug: this.config.debug,
    })

    this.taskRouter = new TaskRouter({
      hub: this.hub,
      defaultTimeoutMs: 30_000,
      debug: this.config.debug,
    })

    this.taskHistory = new TaskHistory({
      dataDir: './data/task-history',
      debug: this.config.debug,
    })

    this.metrics = new MetricsCollector(this.hub)

    this.allowlist = new TaskAllowlist(this.config.security?.allowedTargets)
    this.rateLimiter = new RateLimiter(
      this.config.security?.rateLimitPerHub ?? 60,
      60_000, // 1 minute window
    )

    // Phase 3: Detection-Coordination
    this.detectionLedger = new DetectionLedger(
      `./detection-ledger-${this.hub}.jsonl`,
    )
    this.detectionCoord = new DetectionCoord({
      hub: this.hub,
      ledger: this.detectionLedger,
      capIndex: this.capIndex,
      peerRegistry: this.peerRegistry,
      debug: this.config.debug,
    })

    this._wirePeerRegistry()
  }

  // ── Lifecycle ───────────────────────────────────────────────────────────────

  async start(): Promise<void> {
    if (this.started) return
    this.started = true
    this.startTime = Date.now()

    // 0. Load persistent capability cache for instant recovery
    try {
      const cached = await this.capCache.load()
      if (cached.agents.length > 0) {
        this.log(`Loading ${cached.agents.length} agents from capability cache`)
        for (const entry of cached.agents) {
          if (!entry.isLocal) {
            this.capIndex.upsertAgent(entry.agent, false)
          }
        }
        if (cached.darkCircles.length > 0) {
          for (const dc of cached.darkCircles) {
            for (const [hub, pressure] of Object.entries(dc.byHub)) {
              this.capIndex.updateDarkCircles(hub, [{ name: dc.name, pressure }])
            }
          }
        }
        this._rebuildBloom()
      }
    } catch (err) {
      this.log(`Cache load failed (non-fatal): ${err}`)
    }

    // 1. Start Python bridge (if atlas configured)
    if (this.config.atlasPath) {
      this.pythonBridge = new PythonBridge({
        atlasPath: this.config.atlasPath,
        hub: this.hub,
        debug: this.config.debug,
      })
      this.pythonBridge.on('update', (snapshot: BridgeSnapshot) => {
        this._ingestBridgeSnapshot(snapshot)
        // Trigger immediate mesh sync when atlas changes
        this.meshSync.sync()
      })
      this.pythonBridge.start()
    }

    // 2. Start federation WebSocket server
    await this._startFederationServer()

    // 3. Start local WebSocket server (for local agents)
    await this._startLocalServer()

    // 4. Start REST API
    if (this.config.restEnabled) {
      await this.restApi.start(
        this.capIndex, this.peerRegistry, this.meshSync,
        this.taskRouter, this.taskHistory, this.metrics,
        this.config.security, this.detectionCoord,
      )
    }

    // 5. Connect to static peers / gossip seeds
    for (const peerAddr of this.config.peers) {
      this.peerRegistry.addPeer(peerAddr)
    }

    // 6. Start gossip sampler
    this.peerRegistry.start()

    // 6. Start periodic mesh sync
    this.meshSync.start(this.capIndex, this.peerRegistry)

    // 7. Start task router
    this.taskRouter.start(this.capIndex, this.peerRegistry, this.allowlist, this.rateLimiter)

    // 8. Start task history
    await this.taskHistory.start()

    // 9. Start metrics collector
    this.metrics.start(this.taskRouter, this.peerRegistry, this.capIndex, this.taskHistory)

    // Wire task completion to history
    this.taskRouter.on('task:complete', ({ result, task }) => {
      this.taskHistory.record({
        id: result.id,
        target: task.target,
        command: task.command,
        args: task.args as Record<string, any> | undefined,
        status: result.status,
        execution_ms: result.execution_ms,
        error: result.error,
        hub: this.hub,
        timestamp: result.completed_at,
        teacup: task.teacup,
      })
    })

    // Remove runner agents from mesh when runner disconnects
    this.taskRouter.on('runner:disconnect', ({ agents }) => {
      for (const agentName of agents) {
        this.capIndex.removeAgent(agentName, this.hub)
      }
      this._rebuildBloom()
      this.log(`Runner agents removed from mesh: ${agents.join(', ')}`)
    })

    // 10. Wire detection coordination broadcast
    this.detectionCoord.setBroadcast((msg) => {
      // Broadcast to all local clients
      this.localWss?.clients.forEach(ws => {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify(msg))
        }
      })
      // Broadcast to all federation peers
      this.peerRegistry.broadcast(JSON.stringify(msg))
    })

    this.log(`Started hub "${this.hub}" on ports: federation=${this.config.federationPort}, local=${this.config.localPort}, rest=${this.config.restPort}`)
  }

  async stop(): Promise<void> {
    if (!this.started) return
    this.started = false

    // Save capability cache for fast restart
    try {
      const agents = this.capIndex.getAllAgents().map(a => ({
        agent: { name: a.name, hub: a.hub, capabilities: a.capabilities, pressure: a.pressure, seams: a.seams, lastSeen: a.lastSeen },
        cachedAt: Date.now(),
        isLocal: !!a.isLocal,
      }))
      const darkCircles = this.capIndex.getDarkCircles().map(dc => ({
        name: dc.name,
        pressure: dc.pressure,
        byHub: dc.byHub ?? {},
      }))
      await this.capCache.save(agents, darkCircles)
      this.log(`Saved ${agents.length} agents to capability cache`)
    } catch (err) {
      this.log(`Cache save failed (non-fatal): ${err}`)
    }

    this.meshSync.stop()
    this.peerRegistry.stop()
    this.taskRouter.stop()
    this.pythonBridge?.stop()

    if (this.config.restEnabled) {
      await this.restApi.stop()
    }

    // Terminate all open clients so close() callback fires immediately
    const terminateAll = (wss: WebSocketServer | null) => {
      wss?.clients.forEach(c => c.terminate())
    }
    terminateAll(this.federationWss)
    terminateAll(this.localWss)

    await new Promise<void>(resolve => {
      if (!this.federationWss) return resolve()
      this.federationWss.close(() => resolve())
    })
    await new Promise<void>(resolve => {
      if (!this.localWss) return resolve()
      this.localWss.close(() => resolve())
    })

    this.log('Stopped')
  }

  // ── Public API ──────────────────────────────────────────────────────────────

  /**
   * Register a local agent's capabilities on this hub.
   */
  registerAgent(name: string, capabilities: string[], seams?: string[]): void {
    const { added } = this.capIndex.upsertAgent(
      { name, hub: this.hub, capabilities, seams },
      true,
    )
    if (added) {
      const agent = this.capIndex.getAgent(name, this.hub)!
      this.emit('agent:join', agent)
    }
    // Update delta sync snapshot
    this.meshSync.onLocalChange()
    this._rebuildBloom()
  }

  /**
   * Query for agents by capability (local + federated).
   */
  query(capability: string, minPressure?: number): AgentResult[] {
    return this.capIndex.findByCapability(capability, minPressure)
  }

  /**
   * Get full mesh status.
   */
  status(): MeshStatus {
    return {
      hub: this.hub,
      localAgents: this.capIndex.getLocalAgents(),
      federatedAgents: this.capIndex.getAllAgents().filter(a => !a.isLocal),
      peers: this.peerRegistry.getPeers(),
      darkCircles: this.capIndex.getDarkCircles(),
      uptime: Math.floor((Date.now() - this.startTime) / 1000),
      timestamp: new Date().toISOString(),
    }
  }

  get federationPort(): number {
    return this.config.federationPort
  }

  get restPort(): number {
    return this.config.restPort
  }

  // Typed events
  emit<K extends EventName>(event: K, ...args: Parameters<ServerEvents[K]>): boolean {
    return super.emit(event, ...args)
  }

  on<K extends EventName>(event: K, listener: ServerEvents[K]): this {
    return super.on(event, listener)
  }

  // ── Private ─────────────────────────────────────────────────────────────────

  private async _startFederationServer(): Promise<void> {
    return new Promise((resolve, reject) => {
      const wss = new WebSocketServer({ port: this.config.federationPort })
      this.federationWss = wss

      wss.on('connection', (ws: WebSocket, req) => {
        const remote = req.socket.remoteAddress ?? 'unknown'
        this.log(`Inbound federation connection from ${remote}`)
        this.peerRegistry.registerInbound(ws, remote)

        // Handle messages from local clients connecting to federation port directly
        ws.on('message', (data) => {
          const raw = typeof data === 'string' ? data : data.toString()
          const msg = parseMessage(raw)
          if (msg) this._handleClientMessage(msg, ws)
        })
      })

      wss.on('error', reject)
      wss.on('listening', () => {
        this.log(`Federation WebSocket on port ${this.config.federationPort}`)
        resolve()
      })
    })
  }

  private async _startLocalServer(): Promise<void> {
    return new Promise((resolve, reject) => {
      const wss = new WebSocketServer({ port: this.config.localPort })
      this.localWss = wss

      wss.on('connection', (ws: WebSocket) => {
        this.log('Local client connected')

        ws.on('message', (data) => {
          const raw = typeof data === 'string' ? data : data.toString()
          const msg = parseMessage(raw)
          if (msg) this._handleClientMessage(msg, ws)
        })

        ws.on('error', (err) => {
          this.log(`Local client error: ${err.message}`)
        })
      })

      wss.on('error', reject)
      wss.on('listening', () => {
        this.log(`Local WebSocket on port ${this.config.localPort}`)
        resolve()
      })
    })
  }

  private _handleClientMessage(msg: FederationMessage | Record<string, any>, ws: WebSocket): void {
    // Handle Phase 2 task messages
    const msgType = (msg as Record<string, any>).type as string

    if (msgType === 'task_request') {
      const task = (msg as any).task as TaskRequest
      this.taskRouter.routeTask(task, ws)
      return
    }

    if (msgType === 'task_result') {
      const result = (msg as any).result as TaskResult
      this.taskRouter.handleResult(result)
      return
    }

    if (msgType === 'task_forward') {
      this.taskRouter.handleForward(msg as any)
      return
    }

    if (msgType === 'agent_runner_ready') {
      const rawAgents = (msg as any).agents
      // Normalize: agents can be strings or {name, capabilities, seams} objects
      const agents: string[] = rawAgents.map((a: any) => typeof a === 'string' ? a : a.name)
      this.taskRouter.registerRunner(ws, agents)

      // Register runner agents in the capability index so they're mesh-visible
      for (const agentName of agents) {
        this.capIndex.upsertAgent({
          name: agentName,
          hub: this.hub,
          capabilities: [agentName],  // agents are their own capability
          pressure: 0,
          isLocal: true,
        }, true)
      }
      this._rebuildBloom()
      this.log(`Runner agents registered in mesh: ${agents.join(', ')}`)
      return
    }

    if (msgType === 'agent_register') {
      const { name, capabilities, seams } = msg as any
      if (name && capabilities) {
        this.registerAgent(name, capabilities, seams)
        this._rebuildBloom()
        const payload = JSON.stringify({ type: 'agent_register_ack', name, status: 'ok' })
        ws.send(payload)
      }
      return
    }

    // Phase 3: Detection messages
    if (msgType === 'detection_claim' || msgType === 'detection_verify' ||
        msgType === 'detection_challenge' || msgType === 'detection_outcome') {
      this.detectionCoord.handleMessage(msg as any)
      return
    }

    // Phase 1 message handling
    const fedMsg = msg as FederationMessage
    switch (fedMsg.type) {
      case 'mesh_sync':
        this._handleMeshSync(fedMsg)
        break
      case 'mesh_delta':
        this._handleMeshDelta(fedMsg)
        break
      case 'mesh_delta_ack':
        this._handleMeshDeltaAck(fedMsg)
        break
      case 'capability_query':
        this._handleCapabilityQuery(fedMsg, ws)
        break
      case 'agent_request':
        this._handleAgentRequest(fedMsg, ws)
        break
      case 'ping':
        ws.send(JSON.stringify({ type: 'pong', timestamp: new Date().toISOString() }))
        break
      default:
        break
    }
  }

  private _handleMeshSync(msg: MeshSyncMessageV2 | MeshSyncMessage): void {
    for (const agent of msg.agents) {
      const isLocal = agent.hub === this.hub
      const { added, capChanges } = this.capIndex.upsertAgent(agent, isLocal)

      if (added) {
        const full = this.capIndex.getAgent(agent.name, agent.hub)!
        this.emit('agent:join', full)
      } else if (capChanges.added.length > 0 || capChanges.removed.length > 0) {
        this.log(`Capability change for ${agent.name}@${agent.hub}`)
      }
    }

    this.capIndex.updateDarkCircles(msg.hub, msg.darkCircles)
    this.peerRegistry.updateAgentCount(msg.hub, msg.agents.length)
    this.emit('mesh:sync', msg.hub)

    // ACK the version if present (delta sync)
    if ('version' in msg && msg.version) {
      this.meshSync.handleDeltaAck({ type: 'mesh_delta_ack', hub: msg.hub, version: msg.version })
    }
  }

  private _handleMeshDelta(msg: FederationMessage): void {
    const delta = msg as any
    if (delta.agentDeltas) {
      for (const ad of delta.agentDeltas) {
        if (ad.op === 'upsert') {
          const isLocal = ad.agent.hub === this.hub
          const { added, capChanges } = this.capIndex.upsertAgent(ad.agent, isLocal)
          if (added) {
            const full = this.capIndex.getAgent(ad.agent.name, ad.agent.hub)!
            this.emit('agent:join', full)
          } else if (capChanges.added.length > 0 || capChanges.removed.length > 0) {
            this.log(`Capability change for ${ad.agent.name}@${ad.agent.hub}`)
          }
        } else if (ad.op === 'remove') {
          this.capIndex.removeAgent(ad.agent.name, ad.agent.hub)
          this.emit('agent:leave', ad.agent)
        }
      }
      this._rebuildBloom()
    }

    if (delta.darkCircleDeltas) {
      // Collect current dark circles for this hub, apply deltas, then update
      for (const dcd of delta.darkCircleDeltas) {
        if (dcd.op === 'upsert') {
          this.capIndex.updateDarkCircles(dcd.hub, [dcd.circle])
        }
        // remove dark circle would need a removeDarkCircle method — for now, upsert handles it
      }
    }

    this.emit('mesh:delta', delta.hub)

    // ACK the version
    if (delta.toVersion) {
      this.meshSync.handleDeltaAck({ type: 'mesh_delta_ack', hub: delta.hub, version: delta.toVersion })
    }
  }

  private _handleMeshDeltaAck(msg: FederationMessage): void {
    const ack = msg as any
    this.meshSync.handleDeltaAck({ type: 'mesh_delta_ack', hub: ack.hub, version: ack.version })
  }

  private _handleCapabilityQuery(msg: CapabilityQueryMessage, replyTo: WebSocket): void {
    const agents = this.capIndex.findByCapability(msg.capability, msg.minPressure)

    const response = {
      type: 'capability_response' as const,
      requestId: msg.requestId,
      agents: agents.map(a => ({
        name: a.name,
        hub: a.hub,
        capabilities: a.capabilities,
        pressure: a.pressure,
        seams: a.seams,
        lastSeen: a.lastSeen,
      })),
    }

    if (replyTo.readyState === WebSocket.OPEN) {
      replyTo.send(JSON.stringify(response))
    }

    // Also fan out to peers
    this.peerRegistry.broadcast(JSON.stringify({
      ...msg,
      requestId: uuid(), // New requestId for federation hop
    }))
  }

  private _handleAgentRequest(msg: AgentRequestMessage, replyTo: WebSocket): void {
    const [agentName, agentHub] = msg.target.includes('@')
      ? msg.target.split('@')
      : [msg.target, this.hub]

    const agent = this.capIndex.getAgent(agentName, agentHub ?? this.hub)

    if (!agent) {
      const errorResponse = {
        type: 'agent_response' as const,
        requestId: msg.requestId,
        success: false,
        error: `Agent not found: ${msg.target}`,
      }
      if (replyTo.readyState === WebSocket.OPEN) {
        replyTo.send(JSON.stringify(errorResponse))
      }
      return
    }

    if (agent.isLocal) {
      // Local agent — acknowledge (full execution is Phase 2)
      const response = {
        type: 'agent_response' as const,
        requestId: msg.requestId,
        success: true,
        result: {
          status: 'acknowledged',
          agent: `${agent.name}@${agent.hub}`,
          message: 'Work request received (execution bridge in Phase 2)',
        },
      }
      if (replyTo.readyState === WebSocket.OPEN) {
        replyTo.send(JSON.stringify(response))
      }
    } else {
      // Route to remote hub
      const routed = this.peerRegistry.sendTo(agent.hub, JSON.stringify(msg))
      if (!routed) {
        const errorResponse = {
          type: 'agent_response' as const,
          requestId: msg.requestId,
          success: false,
          error: `Peer hub ${agent.hub} not connected`,
        }
        if (replyTo.readyState === WebSocket.OPEN) {
          replyTo.send(JSON.stringify(errorResponse))
        }
      }
    }
  }

  private _wirePeerRegistry(): void {
    this.peerRegistry.on('message', (msg: FederationMessage | Record<string, any>, _peer: PeerEntry) => {
      const msgType = (msg as Record<string, any>).type as string

      // Handle Phase 2 task messages from remote peers
      if (msgType === 'task_request') {
        const task = (msg as any).task as TaskRequest
        // Remote task — pass source hub for allowlist check
        this.taskRouter.routeTask(task, null, _peer.hub)
        return
      }

      if (msgType === 'task_result') {
        const result = (msg as any).result as TaskResult
        this.taskRouter.handleResult(result)
        return
      }

      if (msgType === 'task_forward') {
        this.taskRouter.handleForward(msg as any)
        return
      }

      // Phase 3: Detection messages from remote peers
      if (msgType === 'detection_claim' || msgType === 'detection_verify' ||
          msgType === 'detection_challenge' || msgType === 'detection_outcome') {
        this.detectionCoord.handleMessage(msg as any)
        return
      }

      if (msgType === 'mesh_sync') {
        this._handleMeshSync(msg as MeshSyncMessageV2 | MeshSyncMessage)
      }
    })

    this.peerRegistry.on('peer:connect', (peer: PeerInfo) => {
      this.log(`Peer connected: ${peer.hub}`)
      this.meshSync.onPeerConnect(peer.hub)
      // Drain forward queue — new peer might unlock queued tasks
      this.taskRouter.drainForwardQueue()
      this.emit('peer:connect', peer)
      // Send our state immediately
      this.meshSync.sync()
    })

    this.peerRegistry.on('peer:disconnect', (peer: { hub: string; address: string }) => {
      this.meshSync.onPeerDisconnect(peer.hub)
      this.log(`Peer disconnected: ${peer.hub}`)
      const removed = this.capIndex.removeHub(peer.hub)
      for (const key of removed) {
        const [name, hub] = key.split('@')
        this.emit('agent:leave', { name, hub })
      }
      this.emit('peer:disconnect', peer)
      this._rebuildBloom()
    })
  }

  private _ingestBridgeSnapshot(snapshot: BridgeSnapshot): void {
    // Remove stale local agents not in latest snapshot
    const snapshotNames = new Set(snapshot.agents.map(a => a.name))
    for (const agent of this.capIndex.getLocalAgents()) {
      if (!snapshotNames.has(agent.name)) {
        this.capIndex.removeAgent(agent.name, this.hub)
        this.emit('agent:leave', { name: agent.name, hub: this.hub })
      }
    }

    for (const agent of snapshot.agents) {
      const { added } = this.capIndex.upsertAgent(agent, true)
      if (added) {
        const full = this.capIndex.getAgent(agent.name, this.hub)!
        this.emit('agent:join', full)
      }
    }

    this.capIndex.updateDarkCircles(this.hub, snapshot.darkCircles)
    this.meshSync.onLocalChange()
    this._rebuildBloom()
    this.log(`Bridge ingested: ${snapshot.agents.length} agents`)
  }

  /** Rebuild capability bloom filter from current index. */
  private _rebuildBloom(): void {
    const caps = this.capIndex.getAllCapabilities()
    this.hubBloom.rebuild(caps)
  }

  private log(msg: string): void {
    if (this.config.debug) console.log(`[ManifoldServer:${this.hub}] ${msg}`)
  }
}

export { CapabilityIndex } from './capability-index.js'
export { PeerRegistry } from './peer-registry.js'
export { MeshSync } from './mesh-sync.js'
export { RestApi } from './rest-api.js'
export { PythonBridge } from './python-bridge.js'
