/**
 * Metrics — runtime stats for the federation mesh.
 *
 * Tracks: runner health, per-agent task counts, mesh topology,
 * latency between hubs, uptime, throughput.
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
  tasksTotal: number
  tasksSuccess: number
  tasksError: number
  successRate: string
  avgExecutionMs: number
  perAgent: Record<string, AgentMetrics>
  perRunner: RunnerMetrics[]
  timestamp: string
}

export class MetricsCollector extends EventEmitter {
  private readonly hub: string
  private startTime = Date.now()

  private perAgent = new Map<string, {
    tasksTotal: number; tasksSuccess: number; tasksError: number; tasksTimeout: number
    totalMs: number; lastSeen: string | null
  }>()

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

    // Listen for task completions
    this.taskRouter.on('task:complete', ({ result }) => {
      this._recordTask(result)
    })

    this.taskRouter.on('task:timeout', ({ task }) => {
      const key = `${task.target}`
      const m = this._getOrCreate(key)
      m.tasksTotal++
      m.tasksTimeout++
    })
  }

  getSnapshot(): MeshMetrics {
    const historyStats = this.taskHistory.getStats()
    const stats = this.capIndex.stats()
    const pending = this.taskRouter.getPendingTasks()

    // Calculate overall avg execution time
    let totalMs = 0
    let totalCount = 0
    for (const [, m] of this.perAgent) {
      totalMs += m.totalMs
      totalCount += m.tasksSuccess
    }

    // Per-agent metrics
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

    return {
      hub: this.hub,
      uptime: Math.floor((Date.now() - this.startTime) / 1000),
      peers: this.peerRegistry.getPeers().length,
      agents: stats.agents,
      capabilities: stats.capabilities,
      darkCircles: stats.darkCircles,
      runnersConnected: this.taskRouter.runnerCount,
      tasksPending: pending.length,
      tasksTotal: historyStats.totalTasks,
      tasksSuccess: historyStats.totalSuccess,
      tasksError: historyStats.totalErrors,
      successRate: historyStats.successRate,
      avgExecutionMs: totalCount > 0 ? Math.round(totalMs / totalCount) : 0,
      perAgent,
      perRunner: [], // Filled by dashboard if needed
      timestamp: new Date().toISOString(),
    }
  }

  private _recordTask(result: TaskResult): void {
    const key = result.executed_by ?? 'unknown'
    const m = this._getOrCreate(key)
    m.tasksTotal++
    m.lastSeen = result.completed_at

    if (result.status === 'success') {
      m.tasksSuccess++
      m.totalMs += result.execution_ms ?? 0
    } else if (result.status === 'error') {
      m.tasksError++
    } else if (result.status === 'timeout') {
      m.tasksTimeout++
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
