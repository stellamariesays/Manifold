/**
 * Pre-computed Metrics — incrementally maintained counters and gauges.
 *
 * Instead of computing stats on-demand (which gets expensive at 1000+ nodes),
 * counters update on every event and the snapshot is a cheap O(1) read.
 *
 * All counters are atomic-friendly (simple increments) for future concurrency.
 */

import { EventEmitter } from 'events'
import type { TaskResult } from '../protocol/messages.js'
import type { TaskRouter } from './task-router.js'
import type { PeerRegistry } from './peer-registry.js'
import type { CapabilityIndex } from './capability-index.js'
import type { TaskHistory } from './task-history.js'

export interface AgentMetrics {
  name: string
  hub: string
  tasksTotal: number
  tasksSuccess: number
  tasksError: number
  tasksTimeout: number
  avgExecutionMs: number
  lastSeen: string | null
}

export interface RunnerMetrics {
  id: string
  connected: boolean
  agents: string[]
  tasksHandled: number
  connectedAt: string | null
  lastHeartbeat: string | null
}

export interface MeshMetrics {
  hub: string
  uptime: number
  peers: number
  agents: number
  capabilities: number
  darkCircles: number
  runnersConnected: number
  tasksPending: number
  tasksQueued: number
  tasksTotal: number
  tasksSuccess: number
  tasksError: number
  successRate: string
  avgExecutionMs: number
  perAgent: Record<string, AgentMetrics>
  perRunner: RunnerMetrics[]
  /** Pre-computed throughput (tasks/min over last 60s) */
  throughputPerMin: number
  /** Backpressure stats */
  backpressure?: {
    pendingTotal: number
    pendingLimit: number
    queueSize: number
    queueLimit: number
  }
  timestamp: string
}

/** Sliding window counter for throughput measurement */
class SlidingWindow {
  private buckets: number[] = []
  private readonly windowMs: number
  private readonly bucketMs: number
  private lastBucket = 0

  constructor(windowMs = 60_000, bucketMs = 5_000) {
    this.windowMs = windowMs
    this.bucketMs = bucketMs
    this.buckets = new Array(Math.ceil(windowMs / bucketMs)).fill(0)
    this.lastBucket = Math.floor(Date.now() / bucketMs)
  }

  /** Record an event. */
  record(count = 1): void {
    const now = Math.floor(Date.now() / this.bucketMs)
    this._advance(now)
    this.buckets[now % this.buckets.length] += count
  }

  /** Get total events in the window. */
  get total(): number {
    this._advance(Math.floor(Date.now() / this.bucketMs))
    return this.buckets.reduce((a, b) => a + b, 0)
  }

  private _advance(now: number): void {
    const elapsed = now - this.lastBucket
    if (elapsed >= this.buckets.length) {
      this.buckets.fill(0)
    } else {
      for (let i = 1; i <= elapsed; i++) {
        this.buckets[(now - i) % this.buckets.length] = 0
      }
    }
    this.lastBucket = now
  }
}

export class MetricsCollector extends EventEmitter {
  private readonly hub: string
  private startTime = Date.now()

  // ── Pre-computed counters (updated on events) ──────────────────────────────
  private totalTasks = 0
  private totalSuccess = 0
  private totalError = 0
  private totalTimeout = 0
  private totalExecutionMs = 0

  private perAgent = new Map<string, {
    tasksTotal: number; tasksSuccess: number; tasksError: number; tasksTimeout: number
    totalMs: number; lastSeen: string | null
  }>()

  // Sliding windows for throughput
  private successWindow = new SlidingWindow(60_000, 5_000)
  private taskWindow = new SlidingWindow(60_000, 5_000)

  private taskRouter!: TaskRouter
  private peerRegistry!: PeerRegistry
  private capIndex!: CapabilityIndex
  private taskHistory!: TaskHistory

  constructor(hub: string) {
    super()
    this.hub = hub
  }

  start(
    taskRouter: TaskRouter,
    peerRegistry: PeerRegistry,
    capIndex: CapabilityIndex,
    taskHistory: TaskHistory,
  ): void {
    this.taskRouter = taskRouter
    this.peerRegistry = peerRegistry
    this.capIndex = capIndex
    this.taskHistory = taskHistory

    this.taskRouter.on('task:complete', ({ result }) => {
      this._recordTask(result)
    })

    this.taskRouter.on('task:timeout', ({ task }) => {
      const key = `${task.target}`
      const m = this._getOrCreate(key)
      m.tasksTotal++
      m.tasksTimeout++
      this.totalTasks++
      this.totalTimeout++
      this.taskWindow.record()
    })
  }

  /**
   * Get a pre-computed snapshot. O(1) for global stats, O(n) for per-agent
   * only if per-agent details are needed.
   */
  getSnapshot(): MeshMetrics {
    const stats = this.capIndex.stats()
    const pending = this.taskRouter.getPendingTasks()
    const bpStats = this.taskRouter.getBackpressureStats()

    const perAgent: Record<string, AgentMetrics> = {}
    for (const [key, m] of this.perAgent) {
      const [name, hub] = key.split('@')
      perAgent[key] = {
        name,
        hub: hub ?? this.hub,
        tasksTotal: m.tasksTotal,
        tasksSuccess: m.tasksSuccess,
        tasksError: m.tasksError,
        tasksTimeout: m.tasksTimeout,
        avgExecutionMs: m.tasksSuccess > 0 ? Math.round(m.totalMs / m.tasksSuccess) : 0,
        lastSeen: m.lastSeen,
      }
    }

    const successRate = this.totalTasks > 0
      ? (this.totalSuccess / this.totalTasks * 100).toFixed(1) + '%'
      : 'N/A'

    return {
      hub: this.hub,
      uptime: Math.floor((Date.now() - this.startTime) / 1000),
      peers: this.peerRegistry.getPeers().length,
      agents: stats.agents,
      capabilities: stats.capabilities,
      darkCircles: stats.darkCircles,
      runnersConnected: this.taskRouter.runnerCount,
      tasksPending: pending.length,
      tasksQueued: bpStats.queueSize,
      tasksTotal: this.totalTasks,
      tasksSuccess: this.totalSuccess,
      tasksError: this.totalError,
      successRate,
      avgExecutionMs: this.totalSuccess > 0 ? Math.round(this.totalExecutionMs / this.totalSuccess) : 0,
      perAgent,
      perRunner: [],
      throughputPerMin: this.successWindow.total,
      backpressure: {
        pendingTotal: bpStats.pendingTotal,
        pendingLimit: bpStats.pendingLimit,
        queueSize: bpStats.queueSize,
        queueLimit: bpStats.queueLimit,
      },
      timestamp: new Date().toISOString(),
    }
  }

  /** Get lightweight global counters (O(1), no per-agent). */
  getCounters(): {
    totalTasks: number; totalSuccess: number; totalError: number; totalTimeout: number
    avgExecutionMs: number; throughputPerMin: number; successRate: string
  } {
    return {
      totalTasks: this.totalTasks,
      totalSuccess: this.totalSuccess,
      totalError: this.totalError,
      totalTimeout: this.totalTimeout,
      avgExecutionMs: this.totalSuccess > 0 ? Math.round(this.totalExecutionMs / this.totalSuccess) : 0,
      throughputPerMin: this.successWindow.total,
      successRate: this.totalTasks > 0
        ? (this.totalSuccess / this.totalTasks * 100).toFixed(1) + '%'
        : 'N/A',
    }
  }

  private _recordTask(result: TaskResult): void {
    const key = result.executed_by ?? 'unknown'
    const m = this._getOrCreate(key)
    m.tasksTotal++
    m.lastSeen = result.completed_at

    this.totalTasks++
    this.taskWindow.record()

    if (result.status === 'success') {
      m.tasksSuccess++
      m.totalMs += result.execution_ms ?? 0
      this.totalSuccess++
      this.totalExecutionMs += result.execution_ms ?? 0
      this.successWindow.record()
    } else if (result.status === 'error') {
      m.tasksError++
      this.totalError++
    } else if (result.status === 'timeout') {
      m.tasksTimeout++
      this.totalTimeout++
    }
  }

  private _getOrCreate(key: string) {
    if (!this.perAgent.has(key)) {
      this.perAgent.set(key, {
        tasksTotal: 0, tasksSuccess: 0, tasksError: 0, tasksTimeout: 0,
        totalMs: 0, lastSeen: null,
      })
    }
    return this.perAgent.get(key)!
  }
}
