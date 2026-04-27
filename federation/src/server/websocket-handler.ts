import WebSocket from 'ws'
import { v4 as uuid } from 'uuid'
import type {
  FederationMessage,
  CapabilityQueryMessage,
  AgentRequestMessage,
  MeshSyncMessageV2,
  MeshSyncMessage,
  TaskRequest,
  TaskResult,
} from '../protocol/messages.js'
import type { CapabilityIndex } from './capability-index.js'
import type { PeerRegistry } from './peer-registry.js'
import type { MeshSync } from './mesh-sync.js'
import type { TaskRouter } from './task-router.js'
import type { DetectionCoord } from './detection-coord.js'
import type { ServerEvents } from '../shared/types.js'
import type { EventEmitter } from 'events'

export interface WebSocketHandlerDeps {
  hub: string
  capIndex: CapabilityIndex
  peerRegistry: PeerRegistry
  meshSync: MeshSync
  taskRouter: TaskRouter
  detectionCoord: DetectionCoord
  emitter: EventEmitter & { emit<K extends keyof ServerEvents>(event: K, ...args: Parameters<ServerEvents[K]>): boolean }
  registerAgent: (name: string, capabilities: string[], seams?: string[]) => void
  rebuildBloom: () => void
  log: (msg: string) => void
}

export class WebSocketHandler {
  private readonly deps: WebSocketHandlerDeps

  constructor(deps: WebSocketHandlerDeps) {
    this.deps = deps
  }

  /**
   * Handle an inbound message from a WebSocket client (local or federation).
   */
  handleClientMessage(msg: FederationMessage | Record<string, any>, ws: WebSocket): void {
    const msgType = (msg as Record<string, any>).type as string

    // Phase 2 task messages
    if (msgType === 'task_request') {
      const task = (msg as any).task as TaskRequest
      this.deps.taskRouter.routeTask(task, ws)
      return
    }

    if (msgType === 'task_result') {
      const result = (msg as any).result as TaskResult
      this.deps.taskRouter.handleResult(result)
      return
    }

    if (msgType === 'task_forward') {
      this.deps.taskRouter.handleForward(msg as any)
      return
    }

    if (msgType === 'agent_runner_ready') {
      this._handleAgentRunnerReady(msg as any, ws)
      return
    }

    if (msgType === 'agent_register') {
      this._handleAgentRegister(msg as any, ws)
      return
    }

    // Phase 3: Detection messages
    if (msgType === 'detection_claim' || msgType === 'detection_verify' ||
        msgType === 'detection_challenge' || msgType === 'detection_outcome') {
      this.deps.detectionCoord.handleMessage(msg as any)
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

  /**
   * Handle an inbound message from a remote peer.
   */
  handlePeerMessage(msg: FederationMessage | Record<string, any>, peerHub: string): void {
    const msgType = (msg as Record<string, any>).type as string

    // Phase 2 task messages from remote peers
    if (msgType === 'task_request') {
      const task = (msg as any).task as TaskRequest
      this.deps.taskRouter.routeTask(task, null, peerHub)
      return
    }

    if (msgType === 'task_result') {
      const result = (msg as any).result as TaskResult
      this.deps.taskRouter.handleResult(result)
      return
    }

    if (msgType === 'task_forward') {
      this.deps.taskRouter.handleForward(msg as any)
      return
    }

    // Phase 3: Detection messages from remote peers
    if (msgType === 'detection_claim' || msgType === 'detection_verify' ||
        msgType === 'detection_challenge' || msgType === 'detection_outcome') {
      this.deps.detectionCoord.handleMessage(msg as any)
      return
    }

    if (msgType === 'mesh_sync') {
      this._handleMeshSync(msg as MeshSyncMessageV2 | MeshSyncMessage)
    }
  }

  // ── Private handlers ──────────────────────────────────────────────────────

  private _handleAgentRunnerReady(msg: any, ws: WebSocket): void {
    const rawAgents = msg.agents
    const agents: string[] = rawAgents.map((a: any) => typeof a === 'string' ? a : a.name)
    this.deps.taskRouter.registerRunner(ws, agents)
    for (let i = 0; i < agents.length; i++) {
      const agentName = agents[i]
      const rawAgent = rawAgents[i]
      const newCaps = (typeof rawAgent === 'object' && Array.isArray(rawAgent.capabilities))
        ? rawAgent.capabilities
        : [agentName]
      const existing = this.deps.capIndex.getAgent(agentName, this.deps.hub)
      const capabilities = (existing && existing.capabilities.length > newCaps.length)
        ? existing.capabilities
        : newCaps
      this.deps.capIndex.upsertAgent({
        name: agentName,
        hub: this.deps.hub,
        capabilities,
        pressure: 0,
        isLocal: true,
      }, true)
    }
    this.deps.rebuildBloom()
    this.deps.log(`Runner agents registered in mesh: ${agents.join(', ')}`)
  }

  private _handleAgentRegister(msg: any, ws: WebSocket): void {
    const { name, capabilities, seams } = msg
    if (name && capabilities) {
      this.deps.registerAgent(name, capabilities, seams)
      this.deps.rebuildBloom()
      const payload = JSON.stringify({ type: 'agent_register_ack', name, status: 'ok' })
      ws.send(payload)
    }
  }

  private _handleMeshSync(msg: MeshSyncMessageV2 | MeshSyncMessage): void {
    for (const agent of msg.agents) {
      const isLocal = agent.hub === this.deps.hub
      const { added, capChanges } = this.deps.capIndex.upsertAgent(agent, isLocal)

      if (added) {
        const full = this.deps.capIndex.getAgent(agent.name, agent.hub)!
        this.deps.emitter.emit('agent:join', full)
      } else if (capChanges.added.length > 0 || capChanges.removed.length > 0) {
        this.deps.log(`Capability change for ${agent.name}@${agent.hub}`)
      }
    }

    this.deps.capIndex.updateDarkCircles(msg.hub, msg.darkCircles)
    this.deps.peerRegistry.updateAgentCount(msg.hub, msg.agents.length)
    this.deps.emitter.emit('mesh:sync', msg.hub)

    if ('version' in msg && msg.version) {
      this.deps.meshSync.handleDeltaAck({ type: 'mesh_delta_ack', hub: msg.hub, version: msg.version })
    }
  }

  private _handleMeshDelta(msg: FederationMessage): void {
    const delta = msg as any
    if (delta.agentDeltas) {
      for (const ad of delta.agentDeltas) {
        if (ad.op === 'upsert') {
          const isLocal = ad.agent.hub === this.deps.hub
          const { added, capChanges } = this.deps.capIndex.upsertAgent(ad.agent, isLocal)
          if (added) {
            const full = this.deps.capIndex.getAgent(ad.agent.name, ad.agent.hub)!
            this.deps.emitter.emit('agent:join', full)
          } else if (capChanges.added.length > 0 || capChanges.removed.length > 0) {
            this.deps.log(`Capability change for ${ad.agent.name}@${ad.agent.hub}`)
          }
        } else if (ad.op === 'remove') {
          this.deps.capIndex.removeAgent(ad.agent.name, ad.agent.hub)
          this.deps.emitter.emit('agent:leave', ad.agent)
        }
      }
      this.deps.rebuildBloom()
    }

    if (delta.darkCircleDeltas) {
      for (const dcd of delta.darkCircleDeltas) {
        if (dcd.op === 'upsert') {
          this.deps.capIndex.updateDarkCircles(dcd.hub, [dcd.circle])
        }
      }
    }

    this.deps.emitter.emit('mesh:delta', delta.hub)

    if (delta.toVersion) {
      this.deps.meshSync.handleDeltaAck({ type: 'mesh_delta_ack', hub: delta.hub, version: delta.toVersion })
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
    const [agentName, agentHub] = msg.target.includes('@')
      ? msg.target.split('@')
      : [msg.target, this.deps.hub]

    const agent = this.deps.capIndex.getAgent(agentName, agentHub ?? this.deps.hub)

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
      const routed = this.deps.peerRegistry.sendTo(agent.hub, JSON.stringify(msg))
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
}
