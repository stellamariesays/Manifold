/**
 * Task Executor — routes tasks to local/remote runners and handles execution.
 */

import { EventEmitter } from 'events'
import { v4 as uuid } from 'uuid'
import type { WebSocket } from 'ws'
import type {
  TaskRequest,
  TaskResult,
  TaskRequestMessage,
  TaskResultMessage,
} from '../protocol/messages.js'
import type { CapabilityIndex } from './capability-index.js'
import type { PeerRegistry } from './peer-registry.js'
import type { PendingTask, TaskRouterOptions } from './task-router.js'
import type { TaskQueue } from './task-queue.js'
import type { TaskAllowlist, RateLimiter } from './security.js'

export class TaskExecutor extends EventEmitter {
  readonly hub: string
  readonly defaultTimeoutMs: number
  readonly debug: boolean

  /** Connected local agent runners, keyed by runner session ID */
  runners = new Map<string, { ws: WebSocket; agents: string[] }>()

  /** Per-runner pending counts: runnerId → count */
  pendingPerRunner = new Map<string, number>()

  readonly maxForwardHops = 6

  private capIndex!: CapabilityIndex
  private peerRegistry!: PeerRegistry
  private allowlist!: TaskAllowlist | null
  private rateLimiter!: RateLimiter | null
  private queue!: TaskQueue

  constructor(options: TaskRouterOptions) {
    super()
    this.hub = options.hub
    this.defaultTimeoutMs = options.defaultTimeoutMs ?? 30_000
    this.debug = options.debug ?? false
  }

  init(capIndex: CapabilityIndex, peerRegistry: PeerRegistry, allowlist: TaskAllowlist | null, rateLimiter: RateLimiter | null, queue: TaskQueue): void {
    this.capIndex = capIndex
    this.peerRegistry = peerRegistry
    this.allowlist = allowlist
    this.rateLimiter = rateLimiter
    this.queue = queue
  }

  stop(): void {
    this.runners.clear()
    this.pendingPerRunner.clear()
  }

  // ── Runner Management ─────────────────────────────────────────────────

  registerRunner(ws: WebSocket, agents: string[]): void {
    const runnerId = uuid()
    this.runners.set(runnerId, { ws, agents })
    this.log(`Runner registered: ${agents.length} agents (${runnerId.substring(0, 8)}...)`)

    ws.on('close', () => {
      this.runners.delete(runnerId)
      this.emit('runner:disconnect', { runnerId, agents })
      this.log(`Runner disconnected: ${runnerId.substring(0, 8)}...`)
    })
  }

  get runnerCount(): number {
    return this.runners.size
  }

  hasRunnerForAgent(agentName: string): boolean {
    return this.findRunnerForAgent(agentName) !== null
  }

  getRunnableAgents(): string[] {
    const agents = new Set<string>()
    for (const [, runner] of this.runners) {
      for (const a of runner.agents) agents.add(a)
    }
    return Array.from(agents)
  }

  // ── Runner Discovery ──────────────────────────────────────────────────

  findRunnerForAgent(agentName: string): { ws: WebSocket; agents: string[] } | null {
    for (const [, runner] of this.runners) {
      if (runner.agents.includes(agentName)) return runner
    }
    return null
  }

  findRunnerForAgentWithCapacity(agentName: string): { runner: { ws: WebSocket; agents: string[] }; runnerId: string } | null {
    for (const [runnerId, runner] of this.runners) {
      if (runner.agents.includes(agentName)) {
        const count = this.pendingPerRunner.get(runnerId) ?? 0
        if (count < this.queue.bp.maxPerRunner) {
          return { runner, runnerId }
        }
      }
    }
    return null
  }

  // ── Security Checks ───────────────────────────────────────────────────

  checkAllowlist(sourceHub: string | undefined, target: string): string | null {
    if (sourceHub && this.allowlist) {
      if (!this.allowlist.isAllowed(sourceHub, target)) {
        return `Hub ${sourceHub} is not allowed to target ${target}`
      }
    }
    return null
  }

  checkRateLimit(rateKey: string): boolean {
    if (this.rateLimiter && !this.rateLimiter.check(rateKey)) return false
    return true
  }

  // ── Local Routing ─────────────────────────────────────────────────────

  routeToLocal(task: TaskRequest, agentName: string, replyTo: WebSocket | null, sourceKey: string, router: { emit: EventEmitter['emit'] }): void {
    const found = this.findRunnerForAgentWithCapacity(agentName)

    if (!found) {
      const anyRunner = this.findRunnerForAgent(agentName)
      if (anyRunner) {
        // Runner exists but at capacity — queue
        if (this.queue.isQueueFull()) {
          const result: TaskResult = {
            id: task.id,
            status: 'rejected',
            error: `Task queue full (${this.queue.queue.length}/${this.queue.bp.maxQueueSize})`,
            completed_at: new Date().toISOString(),
          }
          this.sendResult(result, replyTo)
          router.emit('task:complete', { result, task })
          router.emit('task:backpressure', { reason: 'queue_full', queueSize: this.queue.queue.length })
          return
        }
        this.queue.enqueue(task, agentName, replyTo, sourceKey)
        return
      }

      // No runner at all
      const result: TaskResult = {
        id: task.id,
        status: 'not_found',
        error: `No runner available for agent: ${agentName}`,
        executed_by: `${agentName}@${this.hub}`,
        completed_at: new Date().toISOString(),
      }
      this.sendResult(result, replyTo)
      router.emit('task:complete', { result, task })
      return
    }

    this.dispatchToRunner(task, found.runner, found.runnerId, replyTo, sourceKey)
    this.log(`Routed to local: ${agentName} ${task.command} (${task.id.substring(0, 8)}...) runner:${found.runnerId.substring(0, 8)} [${(this.pendingPerRunner.get(found.runnerId) ?? 0)}/${this.queue.bp.maxPerRunner}]`)
    router.emit('task:routed', { task, target: 'local', agent: agentName })
  }

  /** Dispatch a task to a specific runner, setting up pending tracking. */
  dispatchToRunner(task: TaskRequest, runner: { ws: WebSocket; agents: string[] }, runnerId: string, replyTo: WebSocket | null, sourceKey: string): void {
    const timeoutMs = task.timeout_ms ?? this.defaultTimeoutMs
    const pKey = this.queue.pendingKey(task)
    const pending: PendingTask = {
      task,
      origin: replyTo ? 'local' : 'remote',
      originHub: replyTo ? undefined : (task.origin || undefined),
      sourceKey,
      runnerId,
      replyTo,
      createdAt: Date.now(),
      timeout: setTimeout(() => {
        this.handleTimeout(task.id, pKey)
      }, timeoutMs),
    }
    this.queue.pending.set(pKey, pending)
    this.queue.taskIdToKey.set(task.id, pKey)

    const rCount = (this.pendingPerRunner.get(runnerId) ?? 0) + 1
    this.pendingPerRunner.set(runnerId, rCount)

    this.queue.pendingPerSource.set(sourceKey, (this.queue.pendingPerSource.get(sourceKey) ?? 0) + 1)

    const msg: TaskRequestMessage = { type: 'task_request', task }
    runner.ws.send(JSON.stringify(msg))
  }

  // ── Remote Routing ────────────────────────────────────────────────────

  routeToRemote(task: TaskRequest, targetHub: string, replyTo: WebSocket | null, sourceKey: string, router: { emit: EventEmitter['emit'] }): void {
    if (!task.origin) task.origin = this.hub
    if (!task.caller) task.caller = `${this.hub}`

    const sent = this.peerRegistry.sendTo(targetHub, JSON.stringify({
      type: 'task_request',
      task,
    } as TaskRequestMessage))

    if (!sent) {
      const forwarded = this.tryForwardViaMesh(task, targetHub)
      if (!forwarded) {
        if (this.queue.forwardQueue.length >= this.queue.maxForwardQueueSize) {
          const result: TaskResult = {
            id: task.id,
            status: 'rejected',
            error: `Hub ${targetHub} unreachable and forward queue full`,
            completed_at: new Date().toISOString(),
          }
          this.sendResult(result, replyTo)
          router.emit('task:complete', { result, task })
          return
        }
        this.queue.enqueueForward(task, targetHub, replyTo, sourceKey)
        return
      }
    }

    // Track pending
    const remotePKey = this.queue.pendingKey(task)
    const pending: PendingTask = {
      task,
      origin: 'local',
      sourceKey,
      replyTo,
      createdAt: Date.now(),
      timeout: setTimeout(() => {
        this.handleTimeout(task.id, remotePKey)
      }, task.timeout_ms ?? this.defaultTimeoutMs),
    }
    this.queue.pending.set(remotePKey, pending)
    this.queue.taskIdToKey.set(task.id, remotePKey)
    this.queue.pendingPerSource.set(sourceKey, (this.queue.pendingPerSource.get(sourceKey) ?? 0) + 1)

    this.log(`Routed to remote: ${targetHub} (${task.id.substring(0, 8)}...)`)
    router.emit('task:routed', { task, target: 'remote', hub: targetHub })
  }

  // ── Result / Timeout Handling ──────────────────────────────────────────

  handleResult(result: TaskResult, router: { emit: EventEmitter['emit'] }): void {
    const pKey = this.queue.taskIdToKey.get(result.id)
    const pending = pKey ? this.queue.pending.get(pKey) : undefined

    if (!pending || !pKey) {
      this.log(`Received result for unknown task: ${result.id.substring(0, 8)}...`)
      return
    }

    this.queue.removePending(pKey)
    this.queue.storeCompleted(result)

    this.sendResult(result, pending.replyTo, pending.originHub)
    this.log(`Result: ${result.status} for ${result.id.substring(0, 8)}... (${result.execution_ms ?? '?'}ms)`)
    router.emit('task:complete', { result, task: pending.task })

    this.queue.drainQueue()
  }

  handleTimeout(taskId: string, pKey: string): void {
    const pending = this.queue.removePending(pKey)
    if (!pending) return

    const result: TaskResult = {
      id: taskId,
      status: 'timeout',
      error: `Task timed out`,
      completed_at: new Date().toISOString(),
    }

    this.sendResult(result, pending.replyTo)
    this.log(`Timeout: ${taskId.substring(0, 8)}...`)
    // Emit on queue so router can listen
    this.queue.emit('task:timeout', { task: pending.task })

    this.queue.drainQueue()
  }

  // ── Send Result ────────────────────────────────────────────────────────

  sendResult(result: TaskResult, ws: WebSocket | null, originHub?: string): void {
    const msg: TaskResultMessage = { type: 'task_result', result }

    if (ws && ws.readyState === 1) {
      ws.send(JSON.stringify(msg))
    } else if (originHub && originHub !== this.hub) {
      const sent = this.peerRegistry.sendTo(originHub, JSON.stringify(msg))
      if (!sent) {
        this.log(`Failed to send result back to ${originHub} for task ${result.id.substring(0, 8)}...`)
      }
    }
  }

  // ── Store-and-Forward Mesh ─────────────────────────────────────────────

  tryForwardViaMesh(task: TaskRequest, targetHub: string): boolean {
    const peers = this.peerRegistry.getPeers()
    if (peers.length === 0) return false

    const forwardMsg = {
      type: 'task_forward' as const,
      task,
      hopCount: 1,
      maxHops: this.maxForwardHops,
      originHub: this.hub,
    }

    let sent = false
    for (const peer of peers) {
      if (peer.hub === targetHub) continue
      if (this.peerRegistry.sendTo(peer.hub, JSON.stringify(forwardMsg))) {
        sent = true
      }
    }
    return sent
  }

  handleForward(msg: { task: TaskRequest; hopCount: number; maxHops: number; originHub: string }, router: TaskRouter): void {
    const { task, hopCount, maxHops, originHub } = msg

    if (task.origin === this.hub || this.queue.taskIdToKey.has(task.id)) return

    const [, targetHub] = task.target.includes('@')
      ? task.target.split('@')
      : [task.target, this.hub]

    if (targetHub === this.hub) {
      router.routeTask(task, null, originHub)
      return
    }

    const sent = this.peerRegistry.sendTo(targetHub, JSON.stringify({
      type: 'task_forward',
      task,
      hopCount: hopCount + 1,
      maxHops,
      originHub,
    }))
    if (sent) {
      this.log(`Forwarded task ${task.id.substring(0, 8)}... to ${targetHub} (hop ${hopCount})`)
      return
    }

    if (hopCount >= maxHops) {
      this.log(`Dropping forward for ${task.id.substring(0, 8)}... — max hops reached`)
      return
    }

    const forwardMsg = {
      type: 'task_forward' as const,
      task,
      hopCount: hopCount + 1,
      maxHops,
      originHub,
    }

    const peers = this.peerRegistry.getPeers()
    for (const peer of peers) {
      if (peer.hub === originHub) continue
      this.peerRegistry.sendTo(peer.hub, JSON.stringify(forwardMsg))
    }
  }

  private log(msg: string): void {
    if (this.debug) console.log(`[TaskRouter:${this.hub}] ${msg}`)
  }
}

// Avoid circular — import TaskRouter as type-only at bottom where needed
import type { TaskRouter } from './task-router.js'
