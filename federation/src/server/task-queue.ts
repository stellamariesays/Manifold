/**
 * Task Queue — manages pending/queued tasks, backpressure, and store-and-forward.
 */

import { EventEmitter } from 'events'
import type { TaskRequest, TaskResult } from '../protocol/messages.js'
import type { PendingTask, BackpressureConfig, TaskRouterOptions } from './task-router.js'
import type { PeerRegistry } from './peer-registry.js'
import type { TaskExecutor } from './task-executor.js'

export class TaskQueue extends EventEmitter {
  readonly hub: string
  readonly defaultTimeoutMs: number
  readonly completedTtlMs: number
  readonly debug: boolean

  /**
   * Pending tasks keyed by composite key "<originHub>:<taskId>".
   */
  pending = new Map<string, PendingTask>()

  /**
   * Reverse lookup: bare taskId → composite pending key.
   */
  taskIdToKey = new Map<string, string>()

  /** Queued tasks waiting for a runner slot */
  queue: Array<{ task: TaskRequest; agentName: string; replyTo: import('ws').WebSocket | null; sourceKey: string }> = []

  /** Per-source pending counts: sourceKey → count (dispatched only) */
  pendingPerSource = new Map<string, number>()

  /** Per-source queued counts: sourceKey → count */
  queuedPerSource = new Map<string, number>()

  /** Backpressure config (resolved) */
  readonly bp: {
    maxPendingTotal: number
    maxPendingPerSource: number
    maxQueueSize: number
    maxPerRunner: number
  }

  /** Completed task results (kept briefly for status queries) */
  completed = new Map<string, { result: TaskResult; completedAt: number }>()

  /** Store-and-forward queue */
  forwardQueue: Array<{
    task: TaskRequest
    targetHub: string
    replyTo: import('ws').WebSocket | null
    sourceKey: string
    enqueuedAt: number
    attempts: number
  }> = []

  readonly maxForwardQueueSize = 200
  readonly maxForwardHops = 6

  /** Forward queue drain interval */
  private forwardDrainInterval: ReturnType<typeof setInterval> | null = null

  private peerRegistry!: PeerRegistry
  private executor!: TaskExecutor

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

  init(peerRegistry: PeerRegistry, executor: TaskExecutor): void {
    this.peerRegistry = peerRegistry
    this.executor = executor
  }

  startDrain(): void {
    this.forwardDrainInterval = setInterval(() => this.drainForwardQueue(), 15_000)
  }

  stop(): void {
    if (this.forwardDrainInterval) clearInterval(this.forwardDrainInterval)
    for (const [, pending] of this.pending) {
      if (pending.timeout) clearTimeout(pending.timeout)
    }
    this.pending.clear()
    this.taskIdToKey.clear()
    this.queue = []
    this.pendingPerSource.clear()
    this.queuedPerSource.clear()
    this.forwardQueue = []
  }

  // ── Pending Key ────────────────────────────────────────────────────────

  pendingKey(task: TaskRequest): string {
    const origin = task.origin ?? this.hub
    return `${origin}:${task.id}`
  }

  // ── Backpressure Checks ────────────────────────────────────────────────

  isDuplicate(task: TaskRequest): boolean {
    return this.pending.has(this.pendingKey(task))
  }

  checkTotalBackpressure(): { rejected: boolean; totalInFlight: number } {
    const totalInFlight = this.pending.size + this.queue.length
    return { rejected: totalInFlight >= this.bp.maxPendingTotal, totalInFlight }
  }

  checkSourceBackpressure(sourceKey: string): { rejected: boolean; sourceCount: number } {
    const dispatched = this.pendingPerSource.get(sourceKey) ?? 0
    const queued = this.queuedPerSource.get(sourceKey) ?? 0
    const sourceCount = dispatched + queued
    return { rejected: sourceCount >= this.bp.maxPendingPerSource, sourceCount }
  }

  isQueueFull(): boolean {
    return this.queue.length >= this.bp.maxQueueSize
  }

  enqueue(task: TaskRequest, agentName: string, replyTo: import('ws').WebSocket | null, sourceKey: string): void {
    this.queue.push({ task, agentName, replyTo, sourceKey })
    this.queuedPerSource.set(sourceKey, (this.queuedPerSource.get(sourceKey) ?? 0) + 1)
    this.log(`Queued: ${agentName} (queue: ${this.queue.length})`)
    this.emit('task:queued', { task, queueSize: this.queue.length })
  }

  /** Remove a pending task and update counters. Returns the removed task or undefined. */
  removePending(pKey: string): PendingTask | undefined {
    const pending = this.pending.get(pKey)
    if (!pending) return undefined

    if (pending.timeout) clearTimeout(pending.timeout)
    this.pending.delete(pKey)
    this.taskIdToKey.delete(pending.task.id)

    // Decrement per-runner count
    if (pending.runnerId) {
      const rc = this.executor.pendingPerRunner.get(pending.runnerId) ?? 0
      if (rc > 0) this.executor.pendingPerRunner.set(pending.runnerId, rc - 1)
    }

    // Decrement per-source count
    const sc = this.pendingPerSource.get(pending.sourceKey) ?? 0
    if (sc > 0) this.pendingPerSource.set(pending.sourceKey, sc - 1)

    return pending
  }

  /** Store completed result with TTL */
  storeCompleted(result: TaskResult): void {
    this.completed.set(result.id, { result, completedAt: Date.now() })
    setTimeout(() => this.completed.delete(result.id), this.completedTtlMs)
  }

  // ── Drain Queue ────────────────────────────────────────────────────────

  drainQueue(): void {
    while (this.queue.length > 0) {
      if (this.pending.size >= this.bp.maxPendingTotal) break

      const entry = this.queue[0]
      const { task, agentName, replyTo, sourceKey } = entry

      const found = this.executor.findRunnerForAgentWithCapacity(agentName)
      if (!found) break

      const { runner, runnerId } = found

      // Remove from queue and update queued-per-source
      this.queue.shift()
      const qCount = this.queuedPerSource.get(sourceKey) ?? 0
      if (qCount > 0) this.queuedPerSource.set(sourceKey, qCount - 1)

      // Dispatch via executor
      this.executor.dispatchToRunner(task, runner, runnerId, replyTo, sourceKey)

      this.log(`Drained from queue: ${agentName} (${task.id.substring(0, 8)}...) queue:${this.queue.length}`)
      this.emit('task:dispatched', { task, fromQueue: true })
    }
  }

  // ── Store-and-Forward ──────────────────────────────────────────────────

  enqueueForward(task: TaskRequest, targetHub: string, replyTo: import('ws').WebSocket | null, sourceKey: string): void {
    if (this.forwardQueue.length >= this.maxForwardQueueSize) return
    this.forwardQueue.push({ task, targetHub, replyTo, sourceKey, enqueuedAt: Date.now(), attempts: 0 })
    this.log(`Queued for store-and-forward: ${targetHub} (${task.id.substring(0, 8)}...) queue=${this.forwardQueue.length}`)
    this.emit('task:forward_queued', { task, targetHub })
  }

  drainForwardQueue(): void {
    if (this.forwardQueue.length === 0) return

    const remaining: typeof this.forwardQueue = []
    for (const entry of this.forwardQueue) {
      const elapsed = Date.now() - entry.enqueuedAt
      const taskTtl = entry.task.timeout_ms ?? this.defaultTimeoutMs

      if (elapsed >= taskTtl) {
        const result: TaskResult = {
          id: entry.task.id,
          status: 'timeout',
          error: `Task expired in forward queue (${Math.round(elapsed / 1000)}s)`,
          completed_at: new Date().toISOString(),
        }
        this.executor.sendResult(result, entry.replyTo)
        this.emit('task:complete', { result, task: entry.task })
        continue
      }

      const sent = this.peerRegistry.sendTo(entry.targetHub, JSON.stringify({
        type: 'task_request',
        task: entry.task,
      }))
      if (sent) {
        const fwdPKey = this.pendingKey(entry.task)
        const pending: PendingTask = {
          task: entry.task,
          origin: 'local',
          sourceKey: entry.sourceKey,
          replyTo: entry.replyTo,
          createdAt: entry.enqueuedAt,
          timeout: setTimeout(() => this.executor.handleTimeout(entry.task.id, fwdPKey), taskTtl - elapsed),
        }
        this.pending.set(fwdPKey, pending)
        this.taskIdToKey.set(entry.task.id, fwdPKey)
        this.pendingPerSource.set(entry.sourceKey, (this.pendingPerSource.get(entry.sourceKey) ?? 0) + 1)
        this.log(`Forward queue delivered: ${entry.targetHub} (${entry.task.id.substring(0, 8)}...)`)
        this.emit('task:forward_delivered', { task: entry.task, targetHub: entry.targetHub })
        continue
      }

      entry.attempts++
      remaining.push(entry)
    }
    this.forwardQueue = remaining
  }

  getForwardQueueStats(): { size: number; maxSize: number; oldestAgeMs: number } {
    const oldest = this.forwardQueue.length > 0
      ? Date.now() - this.forwardQueue[0].enqueuedAt
      : 0
    return { size: this.forwardQueue.length, maxSize: this.maxForwardQueueSize, oldestAgeMs: oldest }
  }

  // ── Status Queries ─────────────────────────────────────────────────────

  getTaskStatus(taskId: string): 'pending' | 'completed' | 'unknown' {
    if (this.taskIdToKey.has(taskId)) return 'pending'
    if (this.completed.has(taskId)) return 'completed'
    return 'unknown'
  }

  getPendingTasks(): Array<{ id: string; target: string; command: string; age_ms: number }> {
    const now = Date.now()
    return Array.from(this.pending.values()).map(p => ({
      id: p.task.id,
      target: p.task.target,
      command: p.task.command,
      age_ms: now - p.createdAt,
    }))
  }

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
      perRunner: Object.fromEntries(this.executor.pendingPerRunner),
    }
  }

  private log(msg: string): void {
    if (this.debug) console.log(`[TaskRouter:${this.hub}] ${msg}`)
  }
}
