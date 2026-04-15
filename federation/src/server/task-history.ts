/**
 * Task History — append-only JSONL log of all task executions.
 *
 * Each entry: { id, target, command, status, execution_ms, timestamp, hub, error?, teacup? }
 *
 * The teacup: the concrete moment — what the agent was looking at,
 * what triggered the action, what the ground state was. Not a summary.
 * The door, not the insight.
 *
 * Rotates daily. Survives restarts. Queryable via REST /task-history.
 */

import { appendFile, mkdir, readdir, readFile, stat } from 'fs/promises'
import { join } from 'path'
import type { TaskResult } from '../protocol/messages.js'

/**
 * The concrete moment that grounded a decision or action.
 * Not a summary — the specific thing the agent was holding when it acted.
 */
export interface Teacup {
  /** What triggered this action — the specific signal, not the abstraction */
  trigger: string
  /** What the agent was observing when it acted */
  ground_state?: string
  /** Raw output or observation — the actual data, not processed */
  observation?: string
  /** Outcome scored after the fact: +1 good, -1 bad, 0 neutral, null unscored */
  outcome_score?: number | null
  /** Who scored the outcome (human name, 'auto', 'terrain-delta') */
  scored_by?: string
  /** Timestamp when outcome was scored */
  scored_at?: string
}

export interface TaskHistoryEntry {
  id: string
  target: string
  command: string
  args?: Record<string, any>
  status: string
  execution_ms?: number
  error?: string
  hub: string
  runner?: string
  timestamp: string
  /** The teacup — concrete context for this action */
  teacup?: Teacup
}

export interface TaskHistoryOptions {
  /** Directory for JSONL files. Default: ./data/task-history */
  dataDir?: string
  /** Max days to keep history. Default: 30 */
  maxDays?: number
  debug?: boolean
}

export class TaskHistory {
  private readonly dataDir: string
  private readonly maxDays: number
  private readonly debug: boolean
  private totalTasks = 0
  private totalErrors = 0
  private totalSuccess = 0

  constructor(options: TaskHistoryOptions = {}) {
    this.dataDir = options.dataDir ?? './data/task-history'
    this.maxDays = options.maxDays ?? 30
    this.debug = options.debug ?? false
  }

  async start(): Promise<void> {
    await mkdir(this.dataDir, { recursive: true })
    // Load counts from existing files
    await this._loadCounts()
    this.log(`Started. ${this.totalTasks} historical tasks (${this.totalErrors} errors)`)
  }

  /** Record a completed task */
  async record(entry: TaskHistoryEntry): Promise<void> {
    const line = JSON.stringify(entry) + '\n'
    const file = this._filePath(entry.timestamp)

    try {
      await mkdir(this.dataDir, { recursive: true })
      await appendFile(file, line, 'utf-8')
    } catch (err) {
      this.log(`Write error: ${err}`)
      return
    }

    this.totalTasks++
    if (entry.status === 'success') this.totalSuccess++
    else if (entry.status === 'error' || entry.status === 'timeout') this.totalErrors++

    this.emit('recorded', entry)
  }

  /** Get recent task history */
  async getRecent(limit: number = 50, offset: number = 0): Promise<TaskHistoryEntry[]> {
    const files = await this._getLogFiles()
    const entries: TaskHistoryEntry[] = []

    // Read files newest-first
    for (const file of files.reverse()) {
      try {
        const content = await readFile(join(this.dataDir, file), 'utf-8')
        for (const line of content.trim().split('\n').filter(Boolean)) {
          try {
            entries.push(JSON.parse(line))
          } catch { /* skip malformed */ }
        }
      } catch { /* skip unreadable */ }
    }

    // Sort by timestamp descending
    entries.sort((a, b) => b.timestamp.localeCompare(a.timestamp))

    return entries.slice(offset, offset + limit)
  }

  /** Get aggregated stats */
  getStats(): {
    totalTasks: number
    totalSuccess: number
    totalErrors: number
    successRate: string
  } {
    const rate = this.totalTasks > 0
      ? ((this.totalSuccess / this.totalTasks) * 100).toFixed(1)
      : '0.0'
    return {
      totalTasks: this.totalTasks,
      totalSuccess: this.totalSuccess,
      totalErrors: this.totalErrors,
      successRate: `${rate}%`,
    }
  }

  /** Score an existing task's outcome after the fact */
  async scoreOutcome(taskId: string, score: number, scoredBy: string): Promise<boolean> {
    const files = await this._getLogFiles()
    // Search most recent files first
    for (const file of files.reverse()) {
      const filePath = join(this.dataDir, file)
      try {
        const content = await readFile(filePath, 'utf-8')
        const lines = content.trim().split('\n')
        let found = false
        const updated = lines.map(line => {
          try {
            const entry = JSON.parse(line)
            if (entry.id === taskId && !entry.teacup?.outcome_score) {
              entry.teacup = entry.teacup ?? { trigger: '(recorded without teacup)' }
              entry.teacup.outcome_score = score
              entry.teacup.scored_by = scoredBy
              entry.teacup.scored_at = new Date().toISOString()
              found = true
            }
            return JSON.stringify(entry)
          } catch { return line }
        }).join('\n') + '\n'

        if (found) {
          const { writeFile } = await import('fs/promises')
          await writeFile(filePath, updated, 'utf-8')
          return true
        }
      } catch { /* skip */ }
    }
    return false
  }

  /** Get teacups — entries with teacup context, sorted by most recent */
  async getTeacups(limit: number = 20): Promise<Array<TaskHistoryEntry & { teacup: Teacup }>> {
    const entries = await this.getRecent(limit * 3) // overfetch since not all have teacups
    return entries
      .filter((e): e is TaskHistoryEntry & { teacup: Teacup } => e.teacup != null)
      .slice(0, limit)
  }

  /** Clean old log files beyond retention */
  async clean(): Promise<number> {
    const files = await this._getLogFiles()
    const cutoff = new Date()
    cutoff.setDate(cutoff.getDate() - this.maxDays)
    const cutoffStr = cutoff.toISOString().slice(0, 10)

    let removed = 0
    for (const file of files) {
      const dateStr = file.replace('tasks-', '').replace('.jsonl', '')
      if (dateStr < cutoffStr) {
        const { unlink } = await import('fs/promises')
        await unlink(join(this.dataDir, file))
        removed++
      }
    }

    if (removed > 0) this.log(`Cleaned ${removed} old log files`)
    return removed
  }

  // ── Internal ────────────────────────────────────────────────────────────

  private _filePath(timestamp: string): string {
    const date = timestamp.slice(0, 10)
    return join(this.dataDir, `tasks-${date}.jsonl`)
  }

  private async _getLogFiles(): Promise<string[]> {
    try {
      const files = await readdir(this.dataDir)
      return files.filter(f => f.startsWith('tasks-') && f.endsWith('.jsonl')).sort()
    } catch {
      return []
    }
  }

  private async _loadCounts(): Promise<void> {
    const files = await this._getLogFiles()
    for (const file of files) {
      try {
        const content = await readFile(join(this.dataDir, file), 'utf-8')
        for (const line of content.trim().split('\n').filter(Boolean)) {
          try {
            const entry = JSON.parse(line)
            this.totalTasks++
            if (entry.status === 'success') this.totalSuccess++
            else if (entry.status === 'error' || entry.status === 'timeout') this.totalErrors++
          } catch { /* skip */ }
        }
      } catch { /* skip */ }
    }
  }

  private log(msg: string): void {
    if (this.debug) console.log(`[TaskHistory] ${msg}`)
  }

  // Minimal EventEmitter
  private listeners: Array<(entry: TaskHistoryEntry) => void> = []
  on(event: 'recorded', fn: (entry: TaskHistoryEntry) => void): void {
    this.listeners.push(fn)
  }
  private emit(event: 'recorded', entry: TaskHistoryEntry): void {
    for (const fn of this.listeners) fn(entry)
  }
}
