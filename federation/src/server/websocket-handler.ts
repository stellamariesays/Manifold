/**
 * WebSocketHandler — extracted from ManifoldServer.
 *
 * Owns all WebSocket connection lifecycle and message routing for both
 * federation and local connections.  ManifoldServer creates the WebSocketServer
 * instances and delegates each new connection here.
 */

import { EventEmitter } from 'events'
import WebSocket, { WebSocketServer } from 'ws'
import { v4 as uuid } from 'uuid'
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
import type { ServerEvents, PeerInfo, AgentResult } from '../shared/types.js'
import type { PeerEntry } from './peer-registry.js'

// Dependencies that the handler needs from the owning server
export interface WebSocketHandlerDeps {
  hub: string
  debug: boolean
  capIndex: import('./capability-index.js').CapabilityIndex
  peerRegistry: import('./peer-registry.js').PeerRegistry
  meshSync: import('./mesh-sync.js').MeshSync
  taskRouter: import('./task-router.js').TaskRouter
  detectionCoord: import('./detection-coord.js').DetectionCoord
  /** Rebuild the hub capability bloom filter after index changes */
  rebuildBloom: () => void
  /** Register an agent on this hub */
  registerAgent: (name: string, capabilities: string[], seams?: string[]) => void
}

export class WebSocketHandler extends EventEmitter {
  private readonly deps: WebSocketHandlerDeps
  private federationWss: WebSocketServer | null = null
  private localWss: WebSocketServer | null = null

  constructor(deps: WebSocketHandlerDeps) {
    super()
    this.deps = deps
  }

  // ── Server binding ─────────────────────────────────────────────────────────

  /** Bind to the federation WebSocketServer created by ManifoldServer. */
  bindFederation(wss: WebSocketServer): void {
    this.federationWss = wss

    wss.on('connection', (ws: WebSocket, req) => {
      const remote = req.socket.remoteAddress ?? 'unknown'
      this.log(`Inbound federation connection from ${remote}`)
      this.deps.peerRegistry.registerInbound(ws, remote)

      ws.on('message', (data) => {
        const raw = typeof data === 'string' ? data : data.toString()
        const msg = parseMessage(raw)
        if (msg) this._handleClientMessage(msg, ws)
      })
    })
  }

  /** Bind to the local WebSocketServer created by ManifoldServer. */
  bindLocal(wss: WebSocketServer): void {
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
  }

  /** Access local clients for broadcasting. */
  get localClients(): Set<WebSocket> {
    return this.localWss?.clients ?? new Set()
  }

  /** Access federation clients for broadcasting. */
  get federationClients(): Set<WebSocket> {
    return this.federationWss?.clients ?? new Set()
  }

  // ── Peer-registry message wiring ──────────────────────────────────────────

  /**
   * Wire the peer-registry message & lifecycle events into the handler.
   * Called once during server startup.
   */
  wirePeerRegistry(): void {
    const { peerRegistry, taskRouter, detectionCoord, capIndex, meshSync } = this.deps

    peerRegistry.on('message', (msg: FederationMessage | Record<string, any>, _peer: PeerEntry) => {
      const msgType = (msg as Record<string, any>).type as string

      // Phase 2 task messages from remote peers
      if (msgType === 'task_request') {
        const task = (msg as any).task as TaskRequest
        taskRouter.routeTask(task, null, _peer.hub)
        return
      }

      if (msgType === 'task_result') {
        const result = (msg as any).result as TaskResult
        taskRouter.handleResult(result)
        return
      }

      if (msgType === 'task_forward') {
        taskRouter.handleForward(msg as any)
        return
      }

      // Phase 3: Detection messages from remote peers
      if (msgType === 'detection_claim' || msgType === 'detection_verify' ||
          msgType === 'detection_challenge' || msgType === 'detection_outcome') {
        detectionCoord.handleMessage(msg as any)
        return
      }

      if (msgType === 'mesh_sync') {
        this._handleMeshSync(msg as MeshSyncMessageV2 | MeshSyncMessage)
      }
    })

    peerRegistry.on('peer:connect', (peer: PeerInfo) => {
      this.log(`Peer connected: ${peer.hub}`)
      meshSync.onPeerConnect(peer.hub)
      taskRouter.drainForwardQueue()
      this.emit('peer:connect', peer)
      meshSync.sync()
    })

    peerRegistry.on('peer:disconnect', (peer: { hub: string; address: string }) => {
      meshSync.onPeerDisconnect(peer.hub)
      this.log(`Peer disconnected: ${peer.hub}`)
      const removed = capIndex.removeHub(peer.hub)
      for (const key of removed) {
        const [name, hub] = key.split('@')
        this.emit('agent:leave', { name, hub })
      }
      this.emit('peer:disconnect', peer)
      this.deps.rebuildBloom()
    })
  }

  // ── Message routing ───────────────────────────────────────────────────────

  private _handleClientMessage(msg: FederationMessage | Record<string, any>, ws: WebSocket): void {
    const { capIndex, peerRegistry, taskRouter, detectionCoord, hub } = this.deps
    const msgType = (msg as Record<string, any>).type as string

    // Phase 2 task messages
    if (msgType === 'task_request') {
      const task = (msg as any).task as TaskRequest
      taskRouter.routeTask(task, ws)
      return
    }

    if (msgType === 'task_result') {
      const result = (msg as any).result as TaskResult
      taskRouter.handleResult(result)
      return
    }

    if (msgType === 'task_forward') {
      taskRouter.handleForward(msg as any)
      return
    }

    if (msgType === 'agent_runner_ready') {
      const rawAgents = (msg as any).agents
      const agents: string[] = rawAgents.map((a: any) => typeof a === 'string' ? a : a.name)
      taskRouter.registerRunner(ws, agents)

      for (const agentName of agents) {
        capIndex.upsertAgent({
          name: agentName,
          hub,
          capabilities: [agentName],
          pressure: 0,
          isLocal: true,
        }, true)
      }
      this.deps.rebuildBloom()
      this.log(`Runner agents registered in mesh: ${agents.join(', ')}`)
      return
    }

    if (msgType === 'agent_register') {
      const { name, capabilities, seams } = msg as any
      if (name && capabilities) {
        this.deps.registerAgent(name, capabilities, seams)
        this.deps.rebuildBloom()
        const payload = JSON.stringify({ type: 'agent_register_ack', name, status: 'ok' })
        ws.send(payload)
      }
      return
    }

    // Phase 3: Detection messages
    if (msgType === 'detection_claim' || msgType === 'detection_verify' ||
        msgType === 'detection_challenge' || msgType === 'detection_outcome') {
      detectionCoord.handleMessage(msg as any)
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

  // ── Individual message handlers ────────────────────────────────────────────

  private _handleMeshSync(msg: MeshSyncMessageV2 | MeshSyncMessage): void {
    const { capIndex, meshSync } = this.deps

    for (const agent of msg.agents) {
      const isLocal = agent.hub === this.deps.hub
      const { added, capChanges } = capIndex.upsertAgent(agent, isLocal)

      if (added) {
        const full = capIndex.getAgent(agent.name, agent.hub)!
        this.emit('agent:join', full)
      } else if (capChanges.added.length > 0 || capChanges.removed.length > 0) {
        this.log(`Capability change for ${agent.name}@${agent.hub}`)
      }
    }

    capIndex.updateDarkCircles(msg.hub, msg.darkCircles)
    this.deps.peerRegistry.updateAgentCount(msg.hub, msg.agents.length)
    this.emit('mesh:sync', msg.hub)

    if ('version' in msg && msg.version) {
      meshSync.handleDeltaAck({ type: 'mesh_delta_ack', hub: msg.hub, version: msg.version })
    }
  }

  private _handleMeshDelta(msg: FederationMessage): void {
    const { capIndex, meshSync } = this.deps
    const delta = msg as any

    if (delta.agentDeltas) {
      for (const ad of delta.agentDeltas) {
        if (ad.op === 'upsert') {
          const isLocal = ad.agent.hub === this.deps.hub
          const { added, capChanges } = capIndex.upsertAgent(ad.agent, isLocal)
          if (added) {
            const full = capIndex.getAgent(ad.agent.name, ad.agent.hub)!
            this.emit('agent:join', full)
          } else if (capChanges.added.length > 0 || capChanges.removed.length > 0) {
            this.log(`Capability change for ${ad.agent.name}@${ad.agent.hub}`)
          }
        } else if (ad.op === 'remove') {
          capIndex.removeAgent(ad.agent.name, ad.agent.hub)
          this.emit('agent:leave', ad.agent)
        }
      }
      this.deps.rebuildBloom()
    }

    if (delta.darkCircleDeltas) {
      for (const dcd of delta.darkCircleDeltas) {
        if (dcd.op === 'upsert') {
          capIndex.updateDarkCircles(dcd.hub, [dcd.circle])
        }
      }
    }

    this.emit('mesh:delta', delta.hub)

    if (delta.toVersion) {
      meshSync.handleDeltaAck({ type: 'mesh_delta_ack', hub: delta.hub, version: delta.toVersion })
    }
  }

  private _handleMeshDeltaAck(msg: FederationMessage): void {
    const ack = msg as any
    this.deps.meshSync.handleDeltaAck({ type: 'mesh_delta_ack', hub: ack.hub, version: ack.version })
  }

  private _handleCapabilityQuery(msg: CapabilityQueryMessage, replyTo: WebSocket): void {
    const agents = this.deps.capIndex.findByCapability(msg.capability, msg.minPressure)

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

    this.deps.peerRegistry.broadcast(JSON.stringify({
      ...msg,
      requestId: uuid(),
    }))
  }

  private _handleAgentRequest(msg: AgentRequestMessage, replyTo: WebSocket): void {
    const { capIndex, peerRegistry, hub } = this.deps
    const [agentName, agentHub] = msg.target.includes('@')
      ? msg.target.split('@')
      : [msg.target, hub]

    const agent = capIndex.getAgent(agentName, agentHub ?? hub)

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
      const routed = peerRegistry.sendTo(agent.hub, JSON.stringify(msg))
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

  // ── Helpers ────────────────────────────────────────────────────────────────

  private log(msg: string): void {
    if (this.deps.debug) console.log(`[WebSocketHandler:${this.deps.hub}] ${msg}`)
  }
}
