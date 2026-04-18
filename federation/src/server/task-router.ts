/**
 * Task Router — routes task requests to agent runners and manages execution.
 *
 * Responsibilities:
 * - Accept task_request from local clients or remote peers
 * - Forward to local agent runner if target is on this hub
 * - Forward to remote hub if target is elsewhere
 * - Track pending tasks and deliver results back to origin
 * - Handle timeouts for tasks that never return results
 */

import { EventEmitter } from 'events'
import { v4 as uuid } from 'uuid'
import type { WebSocket } from 'ws'
import type {
  TaskRequest,
  TaskResult,
  TaskRequestMessage,
  TaskResultMessage,
  TaskAckMessage,
} from '../protocol/messages.js'
import type { CapabilityIndex } from './capability-index.js'
import type { PeerRegistry } from './peer-registry.js'
import type { TaskAllowlist } from './security.js'
import type { RateLimiter } from './security.js'

export interface PendingTask {
  task: TaskRequest
  origin: 'local' | 'remote'
  sourceKey: string       // for backpressure tracking
  runnerId?: string       // local runner handling this task
  replyTo: WebSocket | null    // null if from remote peer
  createdAt: number
  timeout: ReturnType<typeof setTimeout> | null
}

export interface BackpressureConfig {
  /** Max concurrent pending tasks across all sources. Default 1000. */
  maxPendingTotal?: number
  /** Max concurrent pending tasks per source hub. Default 100. */
  maxPendingPerSource?: number
  /** Max queued tasks waiting for a runner (beyond pending). Default 500. */
  maxQueueSize?: number
  /** Max concurrent tasks per runner. Default 50. */
  maxPerRunner?: number
}

export interface TaskRouterOptions {
  hub: string
  /** Default task timeout in ms. Default 30000. */
  defaultTimeoutMs?: number
  /** How long to keep completed task records. Default 60000. */
  completedTtlMs?: number
  /** Backpressure limits. */
  backpressure?: BackpressureConfig
  debug?: boolean
}

export class TaskRouter extends EventEmitter {
  private readonly hub: string
  private readonly defaultTimeoutMs: number
  private readonly completedTtlMs: number
  private readonly debug: boolean

  /** Pending tasks keyed by task ID */
  private pending = new Map<string, PendingTask>()

  /** Queued tasks waiting for a runner slot */
  private queue: Array<{ task: TaskRequest; agentName: string; replyTo: WebSocket | null; sourceKey: string }> = []

  /** Per-source pending counts: sourceKey → count (dispatched only) */
  private pendingPerSource = new Map<string, number>()

  /** Per-source queued counts: sourceKey → count */
  private queuedPerSource = new Map<string, number>()

  /** Per-runner pending counts: runnerId → count */
  private pendingPerRunner = new Map<string, number>()

  /** Backpressure config (resolved) */
  private readonly bp: {
    maxPendingTotal: number
    maxPendingPerSource: number
    maxQueueSize: number
    maxPerRunner: number
  }

  /** Completed task results (kept briefly for status queries) */
  private completed = new Map<string, { result: TaskResult; completedAt: number }>()

  /** Connected local agent runners, keyed by runner session ID */
  private runners = new Map<string, { ws: WebSocket; agents: string[] }>()

  private capIndex!: CapabilityIndex
  private peerRegistry!: PeerRegistry
  private allowlist!: TaskAllowlist | null
  private rateLimiter!: RateLimiter | null

  constructor(options: TaskRouterOptions) {
    super()
    this.hub = options.hub
    this.defaultTimeoutMs = options.defaultTimeoutMs ?? 30_000
    this.completedTtlMs = options.completedTtlMs ?? 60_000
    this.debug = options.debug ?? false
    const bp = options.backpressure ?? {}
    this.bp = {
      maxPendingTotal: bp.maxPendingTotal ?? 1000,
      maxPendingPerSource: bp.maxPendingPerSource ?? 100,
      maxQueueSize: bp.maxQueueSize ?? 500,
      maxPerRunner: bp.maxPerRunner ?? 50,
    }
  }

  start(capIndex: CapabilityIndex, peerRegistry: PeerRegistry, allowlist?: TaskAllowlist, rateLimiter?: RateLimiter): void {
    this.capIndex = capIndex
    this.peerRegistry = peerRegistry
    this.allowlist = allowlist ?? null
    this.rateLimiter = rateLimiter ?? null
    this.log('Task router started')
  }

  stop(): void {
    for (const [, pending] of this.pending) {
      if (pending.timeout) clearTimeout(pending.timeout)
    }
    this.pending.clear()
    this.queue = []
    this.pendingPerSource.clear()
    this.queuedPerSource.clear()
    this.pendingPerRunner.clear()
    this.runners.clear()
  }

  // ── Runner Management ─────────────────────────────────────────────────────

  /**
   * Register a local agent runner connection.
   * Runner sends agent_runner_ready with its agent list.
   */
  registerRunner(ws: WebSocket, agents: string[]): void {
    const runnerId = uuid()
    this.runners.set(runnerId, { ws, agents })
    this.log(`Runner registered: ${agents.length} agents (${runnerId.substring(0, 8)}...)`)

    ws.on('close', () => {
      this.runners.delete(runnerId)
      this.log(`Runner disconnected: ${runnerId.substring(0, 8)}...`)
    })
  }

  // ── Task Routing ──────────────────────────────────────────────────────────

  /**
   * Route a task_request. Called when the server receives one from any source.
   */
  routeTask(task: TaskRequest, replyTo: WebSocket | null, sourceHub?: string): void {
    // Parse target
    const [agentName, targetHub] = task.target.includes('@')
      ? task.target.split('@')
      : [task.target, this.hub]

    const resolvedHub = targetHub ?? this.hub

    // Security: check allowlist for remote tasks
    if (sourceHub && this.allowlist) {
      if (!this.allowlist.isAllowed(sourceHub, task.target)) {
        const result: TaskResult = {
          id: task.id,
          status: 'rejected',
          error: `Hub ${sourceHub} is not allowed to target ${task.target}`,
          completed_at: new Date().toISOString(),
        }
        this.sendResult(result, replyTo)
        this.emit('task:complete', { result, task })
        return
      }
    }

    // Security: rate limit check
    const rateKey = sourceHub ?? 'local'
    if (this.rateLimiter && !this.rateLimiter.check(rateKey)) {
      const result: TaskResult = {
        id: task.id,
        status: 'rejected',
        error: `Rate limit exceeded for ${rateKey}`,
        completed_at: new Date().toISOString(),
      }
      this.sendResult(result, replyTo)
      this.emit('task:complete', { result, task })
      return
    }

    // Check if we already have this task (dedup)
    if (this.pending.has(task.id)) {
      const result: TaskResult = {
        id: task.id,
        status: 'rejected',
        error: 'Duplicate task ID',
        completed_at: new Date().toISOString(),
      }
      this.sendResult(result, replyTo)
      this.emit('task:complete', { result, task })
      return
    }

    // Backpressure: total pending limit (includes queued)
    const totalInFlight = this.pending.size + this.queue.length
    if (totalInFlight >= this.bp.maxPendingTotal) {
      const result: TaskResult = {
        id: task.id,
        status: 'rejected',
        error: `Too many tasks in flight (${totalInFlight}/${this.bp.maxPendingTotal})`,
        completed_at: new Date().toISOString(),
      }
      this.sendResult(result, replyTo)
      this.emit('task:complete', { result, task })
      this.emit('task:backpressure', { reason: 'pending_total', pendingCount: totalInFlight })
      return
    }

    // Backpressure: per-source limit (includes dispatched + queued)
    const sourceKey = sourceHub ?? 'local'
    const dispatched = this.pendingPerSource.get(sourceKey) ?? 0
    const queued = this.queuedPerSource.get(sourceKey) ?? 0
    const sourceCount = dispatched + queued
    if (sourceCount >= this.bp.maxPendingPerSource) {
      const result: TaskResult = {
        id: task.id,
        status: 'rejected',
        error: `Source ${sourceKey} has too many pending tasks (${sourceCount}/${this.bp.maxPendingPerSource})`,
        completed_at: new Date().toISOString(),
      }
      this.sendResult(result, replyTo)
      this.emit('task:complete', { result, task })
      this.emit('task:backpressure', { reason: 'per_source', source: sourceKey, count: sourceCount })
      return
    }

    // Route based on target hub
    if (resolvedHub === this.hub) {
      this.routeToLocal(task, agentName, replyTo, sourceKey)
    } else {
      this.routeToRemote(task, resolvedHub, replyTo, sourceKey)
    }
  }

  /**
   * Route to a local agent runner.
   */
  private routeToLocal(task: TaskRequest, agentName: string, replyTo: WebSocket | null, sourceKey: string): void {
    // Find a runner that has this agent with capacity
    const found = this.findRunnerForAgentWithCapacity(agentName)

    if (!found) {
      // Check if any runner exists for this agent at all
      const anyRunner = this.findRunnerForAgent(agentName)
      if (anyRunner) {
        // Runner exists but at capacity — queue the task
        if (this.queue.length >= this.bp.maxQueueSize) {
          const result: TaskResult = {
            id: task.id,
            status: 'rejected',
            error: `Task queue full (${this.queue.length}/${this.bp.maxQueueSize})`,
            completed_at: new Date().toISOString(),
          }
          this.sendResult(result, replyTo)
          this.emit('task:complete', { result, task })
          this.emit('task:backpressure', { reason: 'queue_full', queueSize: this.queue.length })
          return
        }
        this.queue.push({ task, agentName, replyTo, sourceKey })
        this.queuedPerSource.set(sourceKey, (this.queuedPerSource.get(sourceKey) ?? 0) + 1)
        this.log(`Queued: ${agentName} (queue: ${this.queue.length})`)
        this.emit('task:queued', { task, queueSize: this.queue.length })
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
      this.emit('task:complete', { result, task })
      return
    }

    const { runner, runnerId } = found

    // Set up pending task
    const timeoutMs = task.timeout_ms ?? this.defaultTimeoutMs
    const pending: PendingTask = {
      task,
      origin: replyTo ? 'local' : 'remote',
      sourceKey,
      runnerId,
      replyTo,
      createdAt: Date.now(),
      timeout: setTimeout(() => {
        this.handleTimeout(task.id)
      }, timeoutMs),
    }
    this.pending.set(task.id, pending)

    // Track per-runner count
    const rCount = (this.pendingPerRunner.get(runnerId) ?? 0) + 1
    this.pendingPerRunner.set(runnerId, rCount)

    // Track per-source count
    this.pendingPerSource.set(sourceKey, (this.pendingPerSource.get(sourceKey) ?? 0) + 1)

    // Forward to runner
    const msg: TaskRequestMessage = { type: 'task_request', task }
    runner.ws.send(JSON.stringify(msg))

    this.log(`Routed to local: ${agentName} ${task.command} (${task.id.substring(0, 8)}...) runner:${runnerId.substring(0, 8)} [${rCount}/${this.bp.maxPerRunner}]`)
    this.emit('task:routed', { task, target: 'local', agent: agentName })
  }

  /**
   * Route to a remote hub via federation.
   */
  private routeToRemote(task: TaskRequest, targetHub: string, replyTo: WebSocket | null, sourceKey: string): void {
    // Set origin if not set
    if (!task.origin) task.origin = this.hub
    if (!task.caller) task.caller = `${this.hub}`

    const sent = this.peerRegistry.sendTo(targetHub, JSON.stringify({
      type: 'task_request',
      task,
    } as TaskRequestMessage))

    if (!sent) {
      const result: TaskResult = {
        id: task.id,
        status: 'not_found',
        error: `Peer hub ${targetHub} not connected`,
        completed_at: new Date().toISOString(),
      }
      this.sendResult(result, replyTo)
      this.emit('task:complete', { result, task })
      return
    }

    // Track pending (waiting for result from remote hub)
    const pending: PendingTask = {
      task,
      origin: 'local',
      sourceKey,
      replyTo,
      createdAt: Date.now(),
      timeout: setTimeout(() => {
        this.handleTimeout(task.id)
      }, task.timeout_ms ?? this.defaultTimeoutMs),
    }
    this.pending.set(task.id, pending)

    // Track per-source count
    this.pendingPerSource.set(sourceKey, (this.pendingPerSource.get(sourceKey) ?? 0) + 1)

    this.log(`Routed to remote: ${targetHub} (${task.id.substring(0, 8)}...)`)
    this.emit('task:routed', { task, target: 'remote', hub: targetHub })
  }

  /**
   * Handle a task_result from a runner or remote peer.
   */
  handleResult(result: TaskResult): void {
    const pending = this.pending.get(result.id)

    if (!pending) {
      this.log(`Received result for unknown task: ${result.id.substring(0, 8)}...`)
      return
    }

    // Clear timeout and remove from pending
    if (pending.timeout) clearTimeout(pending.timeout)
    this.pending.delete(result.id)

    // Decrement per-runner count
    if (pending.runnerId) {
      const rc = this.pendingPerRunner.get(pending.runnerId) ?? 0
      if (rc > 0) this.pendingPerRunner.set(pending.runnerId, rc - 1)
    }

    // Decrement per-source count
    const sourceKey = pending.sourceKey
    const sc = this.pendingPerSource.get(sourceKey) ?? 0
    if (sc > 0) this.pendingPerSource.set(sourceKey, sc - 1)

    // Store completed
    this.completed.set(result.id, { result, completedAt: Date.now() })
    setTimeout(() => this.completed.delete(result.id), this.completedTtlMs)

    // Send result back to origin
    this.sendResult(result, pending.replyTo)

    this.log(`Result: ${result.status} for ${result.id.substring(0, 8)}... (${result.execution_ms ?? '?'}ms)`)
    this.emit('task:complete', { result, task: pending.task })

    // Drain queue — try to dispatch next queued task
    this._drainQueue()
  }

  private handleTimeout(taskId: string): void {
    const pending = this.pending.get(taskId)
    if (!pending) return

    this.pending.delete(taskId)

    // Decrement per-runner count
    if (pending.runnerId) {
      const rc = this.pendingPerRunner.get(pending.runnerId) ?? 0
      if (rc > 0) this.pendingPerRunner.set(pending.runnerId, rc - 1)
    }

    // Decrement per-source
    const sourceKey = pending.sourceKey
    const sc = this.pendingPerSource.get(sourceKey) ?? 0
    if (sc > 0) this.pendingPerSource.set(sourceKey, sc - 1)

    const result: TaskResult = {
      id: taskId,
      status: 'timeout',
      error: `Task timed out`,
      completed_at: new Date().toISOString(),
    }

    this.sendResult(result, pending.replyTo)
    this.log(`Timeout: ${taskId.substring(0, 8)}...`)
    this.emit('task:timeout', { task: pending.task })

    // Drain queue
    this._drainQueue()
  }

  // ── Helpers ───────────────────────────────────────────────────────────────

  private findRunnerForAgent(agentName: string): { ws: WebSocket; agents: string[] } | null {
    for (const [, runner] of this.runners) {
      if (runner.agents.includes(agentName)) {
        return runner
      }
    }
    return null
  }

  private findRunnerForAgentWithCapacity(agentName: string): { runner: { ws: WebSocket; agents: string[] }; runnerId: string } | null {
    // Find runner with capacity for this agent
    for (const [runnerId, runner] of this.runners) {
      if (runner.agents.includes(agentName)) {
        const count = this.pendingPerRunner.get(runnerId) ?? 0
        if (count < this.bp.maxPerRunner) {
          return { runner, runnerId }
        }
      }
    }
    return null
  }

  /**
   * Drain the queue — dispatch tasks waiting for runner capacity.
   */
  private _drainQueue(): void {
    while (this.queue.length > 0) {
      // Check total pending limit
      if (this.pending.size >= this.bp.maxPendingTotal) break

      const entry = this.queue[0]
      const { task, agentName, replyTo, sourceKey } = entry
      const found = this.findRunnerForAgentWithCapacity(agentName)

      if (!found) break // No runner with capacity yet

      const { runner, runnerId } = found

      // Remove from queue and update queued-per-source
      this.queue.shift()
      const qCount = this.queuedPerSource.get(sourceKey) ?? 0
      if (qCount > 0) this.queuedPerSource.set(sourceKey, qCount - 1)

      // Dispatch
      const timeoutMs = task.timeout_ms ?? this.defaultTimeoutMs
      const pending: PendingTask = {
        task,
        origin: replyTo ? 'local' : 'remote',
        sourceKey,
        runnerId,
        replyTo,
        createdAt: Date.now(),
        timeout: setTimeout(() => {
          this.handleTimeout(task.id)
        }, timeoutMs),
      }
      this.pending.set(task.id, pending)

      const rCount = (this.pendingPerRunner.get(runnerId) ?? 0) + 1
      this.pendingPerRunner.set(runnerId, rCount)

      // Track per-source (dispatched)
      this.pendingPerSource.set(sourceKey, (this.pendingPerSource.get(sourceKey) ?? 0) + 1)

      const msg: TaskRequestMessage = { type: 'task_request', task }
      runner.ws.send(JSON.stringify(msg))

      this.log(`Drained from queue: ${agentName} (${task.id.substring(0, 8)}...) queue:${this.queue.length}`)
      this.emit('task:dispatched', { task, fromQueue: true })
    }
  }

  private sendResult(result: TaskResult, ws: WebSocket | null): void {
    const msg: TaskResultMessage = { type: 'task_result', result }

    if (ws && ws.readyState === 1) { // WebSocket.OPEN
      ws.send(JSON.stringify(msg))
    }
    // If no ws (remote origin), the remote hub's router will deliver it
  }

  /** Get status of a task by ID */
  getTaskStatus(taskId: string): 'pending' | 'completed' | 'unknown' {
    if (this.pending.has(taskId)) return 'pending'
    if (this.completed.has(taskId)) return 'completed'
    return 'unknown'
  }

  /** Get all pending tasks */
  getPendingTasks(): Array<{ id: string; target: string; command: string; age_ms: number }> {
    const now = Date.now()
    return Array.from(this.pending.values()).map(p => ({
      id: p.task.id,
      target: p.task.target,
      command: p.task.command,
      age_ms: now - p.createdAt,
    }))
  }

  /** Get backpressure stats */
  getBackpressureStats(): {
    pendingTotal: number
    pendingLimit: number
    queueSize: number
    queueLimit: number
    perSource: Record<string, number>
    perRunner: Record<string, number>
  } {
    return {
      pendingTotal: this.pending.size,
      pendingLimit: this.bp.maxPendingTotal,
      queueSize: this.queue.length,
      queueLimit: this.bp.maxQueueSize,
      perSource: Object.fromEntries(this.pendingPerSource),
      perRunner: Object.fromEntries(this.pendingPerRunner),
    }
  }

  /** Number of connected runners */
  get runnerCount(): number {
    return this.runners.size
  }

  /** Check if a runner is available for a given agent name */
  hasRunnerForAgent(agentName: string): boolean {
    return this.findRunnerForAgent(agentName) !== null
  }

  /** Get list of all agent names that have runners */
  getRunnableAgents(): string[] {
    const agents = new Set<string>()
    for (const [, runner] of this.runners) {
      for (const a of runner.agents) agents.add(a)
    }
    return Array.from(agents)
  }

  private log(msg: string): void {
    if (this.debug) console.log(`[TaskRouter:${this.hub}] ${msg}`)
  }
}
