/**
 * Task History — append-only JSONL log of all task executions.
 *
 * Each entry: { id, target, command, status, execution_ms, timestamp, hub, error? }
 * Rotates daily. Survives restarts. Queryable via REST /task-history.
 */

import { appendFile, mkdir, readdir, readFile, stat } from 'fs/promises'
import { join } from 'path'
import type { TaskResult } from '../protocol/messages.js'

export interface TaskHistoryEntry {
  id: string
  target: string
  command: string
  status: string
  execution_ms?: number
  error?: string
  hub: string
  runner?: string
  timestamp: string
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
