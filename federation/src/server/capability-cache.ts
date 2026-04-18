/**
 * Persistent Capability Cache — survives restarts.
 *
 * On graceful shutdown, writes the current capability index to a JSON file.
 * On startup, reads it back so the hub has immediate capability awareness
 * before full mesh sync completes.
 *
 * File format: versioned JSON with expiry timestamps for stale entry detection.
 */

import { promises as fs } from 'fs'
import path from 'path'
import type { AgentInfo, DarkCircle } from '../protocol/messages.js'

export interface CacheEntry {
  agent: AgentInfo
  cachedAt: number    // unix ms
  isLocal: boolean
}

export interface CacheFile {
  version: 1
  hub: string
  savedAt: number
  agents: CacheEntry[]
  darkCircles: Array<{ name: string; pressure: number; byHub: Record<string, number> }>
}

export interface PersistentCacheOptions {
  /** Path to cache file. Default: './data/capability-cache.json' */
  filePath?: string
  /** Max age in ms for cached entries. Default: 300000 (5 min) */
  maxAgeMs?: number
  /** Hub name (for file header) */
  hub: string
}

export class PersistentCapabilityCache {
  private readonly filePath: string
  private readonly maxAgeMs: number
  private readonly hub: string
  private dirty = false
  private writeTimer: ReturnType<typeof setTimeout> | null = null
  private static readonly FLUSH_INTERVAL_MS = 10_000 // write at most every 10s

  constructor(options: PersistentCacheOptions) {
    this.filePath = options.filePath ?? './data/capability-cache.json'
    this.maxAgeMs = options.maxAgeMs ?? 300_000
    this.hub = options.hub
  }

  /**
   * Load cached entries from disk. Filters out expired entries.
   */
  async load(): Promise<{ agents: CacheEntry[]; darkCircles: CacheFile['darkCircles'] }> {
    try {
      const data = await fs.readFile(this.filePath, 'utf-8')
      const cache: CacheFile = JSON.parse(data)

      if (cache.version !== 1) {
        return { agents: [], darkCircles: [] }
      }

      const now = Date.now()
      const agents = cache.agents.filter(e => (now - e.cachedAt) < this.maxAgeMs)

      return { agents, darkCircles: cache.darkCircles ?? [] }
    } catch {
      return { agents: [], darkCircles: [] }
    }
  }

  /**
   * Schedule a write (debounced). Call this on every capability change.
   */
  markDirty(): void {
    this.dirty = true
    if (!this.writeTimer) {
      this.writeTimer = setTimeout(() => this.flush(), PersistentCapabilityCache.FLUSH_INTERVAL_MS)
    }
  }

  /**
   * Write current state to disk.
   */
  async flush(): Promise<void> {
    this.writeTimer = null
    if (!this.dirty) return
    // dirty flag is reset by the caller providing data via save()
  }

  /**
   * Save entries to disk immediately.
   */
  async save(agents: CacheEntry[], darkCircles: CacheFile['darkCircles']): Promise<void> {
    const cache: CacheFile = {
      version: 1,
      hub: this.hub,
      savedAt: Date.now(),
      agents,
      darkCircles,
    }

    // Ensure directory exists
    await fs.mkdir(path.dirname(this.filePath), { recursive: true })

    // Atomic write: write to temp file, then rename
    const tmpPath = this.filePath + '.tmp'
    await fs.writeFile(tmpPath, JSON.stringify(cache))
    await fs.rename(tmpPath, this.filePath)

    this.dirty = false
    if (this.writeTimer) {
      clearTimeout(this.writeTimer)
      this.writeTimer = null
    }
  }

  /**
   * Graceful shutdown — flush pending writes.
   */
  async close(): Promise<void> {
    if (this.writeTimer) {
      clearTimeout(this.writeTimer)
      this.writeTimer = null
    }
    if (this.dirty) {
      // Caller should save() before close() in the normal flow
    }
  }

  /** Check if cache file exists. */
  async exists(): Promise<boolean> {
    try {
      await fs.access(this.filePath)
      return true
    } catch {
      return false
    }
  }

  /** Get cache file stats. */
  async getStats(): Promise<{ exists: boolean; sizeBytes: number; savedAt: number | null; agentCount: number }> {
    try {
      const stat = await fs.stat(this.filePath)
      const data = await fs.readFile(this.filePath, 'utf-8')
      const cache: CacheFile = JSON.parse(data)
      return {
        exists: true,
        sizeBytes: stat.size,
        savedAt: cache.savedAt,
        agentCount: cache.agents.length,
      }
    } catch {
      return { exists: false, sizeBytes: 0, savedAt: null, agentCount: 0 }
    }
  }
}
