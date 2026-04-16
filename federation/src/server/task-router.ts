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
  sourceHub?: string           // originating hub for remote tasks
  replyTo: WebSocket | null    // null if from remote peer
  createdAt: number
  timeout: ReturnType<typeof setTimeout> | null
}

export interface TaskRouterOptions {
  hub: string
  /** Default task timeout in ms. Default 30000. */
  defaultTimeoutMs?: number
  /** How long to keep completed task records. Default 60000. */
  completedTtlMs?: number
  debug?: boolean
}

export class TaskRouter extends EventEmitter {
  private readonly hub: string
  private readonly defaultTimeoutMs: number
  private readonly completedTtlMs: number
  private readonly debug: boolean

  /** Pending tasks keyed by task ID */
  private pending = new Map<string, PendingTask>()

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
    this.log(`Routing task: ${task.command} -> ${task.target} (${task.id.substring(0, 8)}...) from=${sourceHub ?? 'local'}`)
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
    this.log(`Dedup check: ${task.id.substring(0, 8)}... exists=${this.pending.has(task.id)}`)
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

    // Route based on target hub
    if (resolvedHub === this.hub) {
      this.routeToLocal(task, agentName, replyTo, sourceHub)
    } else {
      this.routeToRemote(task, resolvedHub, replyTo)
    }
  }

  /**
   * Route to a local agent runner.
   */
  private routeToLocal(task: TaskRequest, agentName: string, replyTo: WebSocket | null, sourceHub?: string): void {
    // Find a runner that has this agent
    const runner = this.findRunnerForAgent(agentName)

    if (!runner) {
      const result: TaskResult = {
        id: task.id,
        status: 'not_found',
        error: `No runner available for agent: ${agentName}`,
        executed_by: `${agentName}@${this.hub}`,
        completed_at: new Date().toISOString(),
      }
      this.sendResult(result, replyTo)
      // Emit so REST handler can catch it too
      this.emit('task:complete', { result, task })
      return
    }

    // Set up pending task
    const timeoutMs = task.timeout_ms ?? this.defaultTimeoutMs
    const pending: PendingTask = {
      task,
      origin: replyTo ? 'local' : 'remote',
      sourceHub: sourceHub,
      replyTo,
      createdAt: Date.now(),
      timeout: setTimeout(() => {
        this.handleTimeout(task.id)
      }, timeoutMs),
    }
    this.pending.set(task.id, pending)

    // Forward to runner
    const msg: TaskRequestMessage = { type: 'task_request', task }
    runner.ws.send(JSON.stringify(msg))

    this.log(`Routed to local: ${agentName} ${task.command} (${task.id.substring(0, 8)}...)`)
    this.emit('task:routed', { task, target: 'local', agent: agentName })
  }

  /**
   * Route to a remote hub via federation.
   */
  private routeToRemote(task: TaskRequest, targetHub: string, replyTo: WebSocket | null): void {
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
      replyTo,
      createdAt: Date.now(),
      timeout: setTimeout(() => {
        this.handleTimeout(task.id)
      }, task.timeout_ms ?? this.defaultTimeoutMs),
    }
    this.pending.set(task.id, pending)

    this.log(`Routed to remote: ${targetHub} (${task.id.substring(0, 8)}...)`)
    this.emit('task:routed', { task, target: 'remote', hub: targetHub })
  }

  /**
   * Handle a task_result from a runner or remote peer.
   */
  handleResult(result: TaskResult): void {
    this.log(`Result: ${result.id.substring(0, 8)}... status=${result.status}${result.error ? ' error=' + result.error : ''}`)
    const pending = this.pending.get(result.id)

    if (!pending) {
      // Might be a result for a task we forwarded — check if origin is remote
      this.log(`Received result for unknown task: ${result.id.substring(0, 8)}...`)
      return
    }

    // Clear timeout
    if (pending.timeout) clearTimeout(pending.timeout)
    this.pending.delete(result.id)

    // Store completed
    this.completed.set(result.id, { result, completedAt: Date.now() })
    setTimeout(() => this.completed.delete(result.id), this.completedTtlMs)

    // Send result back to origin
    this.sendResult(result, pending.replyTo)

    // If task came from a remote hub and no local WS to reply to, forward via peer
    if (!pending.replyTo && pending.sourceHub) {
      this.peerRegistry.sendTo(pending.sourceHub, JSON.stringify({
        type: 'task_result',
        result,
      } as TaskResultMessage))
      this.log(`Forwarded result back to ${pending.sourceHub} for ${result.id.substring(0, 8)}...`)
    }

    this.log(`Result: ${result.status} for ${result.id.substring(0, 8)}... (${result.execution_ms ?? '?'}ms)`)
    this.log(`Emitting task:complete for ${result.id.substring(0, 8)}... status=${result.status}`)
    this.emit('task:complete', { result, task: pending.task })
  }

  private handleTimeout(taskId: string): void {
    const pending = this.pending.get(taskId)
    if (!pending) return

    this.pending.delete(taskId)

    const result: TaskResult = {
      id: taskId,
      status: 'timeout',
      error: `Task timed out`,
      completed_at: new Date().toISOString(),
    }

    this.sendResult(result, pending.replyTo)
    this.log(`Timeout: ${taskId.substring(0, 8)}...`)
    this.emit('task:timeout', { task: pending.task })
  }

  // ── Helpers ───────────────────────────────────────────────────────────────

  /** Normalize an agent entry to its name (handles both string and object format) */
  private static agentName(a: string | { name: string }): string {
    return typeof a === 'string' ? a : a.name
  }

  private findRunnerForAgent(agentName: string): { ws: WebSocket; agents: (string | { name: string })[] } | null {
    for (const [, runner] of this.runners) {
      for (const a of runner.agents) {
        if (TaskRouter.agentName(a) === agentName) return runner
      }
    }
    return null
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
      for (const a of runner.agents) agents.add(TaskRouter.agentName(a))
    }
    return Array.from(agents)
  }

  private log(msg: string): void {
    if (this.debug) console.log(`[TaskRouter:${this.hub}] ${msg}`)
  }
}
