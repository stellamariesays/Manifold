import { readFile } from 'fs/promises'
import { watch } from 'fs'
import { EventEmitter } from 'events'
import type { AgentInfo, DarkCircle } from '../protocol/messages.js'

/**
 * Atlas format from the Python manifold.server.
 * This is what stella-atlas.json looks like — we parse it permissively.
 */
interface AtlasAgent {
  name?: string
  capabilities?: string[]
  seams?: string[]
  pressure?: number
  [key: string]: unknown
}

interface AtlasDarkCircle {
  name?: string
  pressure?: number
  [key: string]: unknown
}

interface Atlas {
  agents?: AtlasAgent[]
  dark_circles?: AtlasDarkCircle[]
  darkCircles?: AtlasDarkCircle[]
  [key: string]: unknown
}

export interface BridgeSnapshot {
  agents: AgentInfo[]
  darkCircles: DarkCircle[]
  timestamp: string
}

export interface PythonBridgeOptions {
  /** Path to atlas JSON file (e.g. data/manifold/stella-atlas.json) */
  atlasPath: string
  /** Hub name this bridge belongs to */
  hub: string
  /** Poll interval in ms (used as fallback if fs.watch not available). Default 15000. */
  pollInterval?: number
  debug?: boolean
}

/**
 * Reads state from the Python manifold.server via file polling.
 *
 * The Python server writes atlas.json periodically. We watch that file
 * and emit 'update' events whenever it changes.
 *
 * This is Phase 1 (simplest). Phase 2 will add a WebSocket bridge so we
 * can subscribe to real-time events from the Python server.
 */
export class PythonBridge extends EventEmitter {
  private readonly atlasPath: string
  private readonly hub: string
  private readonly pollInterval: number
  private readonly debug: boolean

  private pollTimer: ReturnType<typeof setInterval> | null = null
  private watcher: ReturnType<typeof watch> | null = null
  private lastMtime = 0
  private snapshot: BridgeSnapshot | null = null

  constructor(options: PythonBridgeOptions) {
    super()
    this.atlasPath = options.atlasPath
    this.hub = options.hub
    this.pollInterval = options.pollInterval ?? 15_000
    this.debug = options.debug ?? false
  }

  start(): void {
    // Initial load
    this._load().catch(err => this.log(`Initial load failed: ${err.message}`))

    // Try fs.watch first (event-driven, lower latency)
    try {
      this.watcher = watch(this.atlasPath, (_event) => {
        this._load().catch(() => {})
      })
    } catch {
      this.log('fs.watch unavailable, falling back to polling')
    }

    // Poll as a safety net regardless
    this.pollTimer = setInterval(() => {
      this._load().catch(() => {})
    }, this.pollInterval)
  }

  stop(): void {
    if (this.pollTimer) {
      clearInterval(this.pollTimer)
      this.pollTimer = null
    }
    if (this.watcher) {
      this.watcher.close()
      this.watcher = null
    }
  }

  getSnapshot(): BridgeSnapshot | null {
    return this.snapshot
  }

  private async _load(): Promise<void> {
    try {
      const stat = await import('fs/promises').then(m => m.stat(this.atlasPath))
      const mtime = stat.mtimeMs

      // Only re-parse if file actually changed
      if (mtime === this.lastMtime) return
      this.lastMtime = mtime

      const raw = await readFile(this.atlasPath, 'utf-8')
      const atlas = JSON.parse(raw) as Atlas

      const snapshot = this._parse(atlas)
      this.snapshot = snapshot
      this.emit('update', snapshot)
      this.log(`Loaded atlas: ${snapshot.agents.length} agents, ${snapshot.darkCircles.length} circles`)
    } catch (err) {
      this.log(`Load error: ${(err as Error).message}`)
    }
  }

  private _parse(atlas: Atlas): BridgeSnapshot {
    const rawAgents = atlas.agents ?? []
    const rawCircles = (atlas.dark_circles ?? atlas.darkCircles) ?? []

    const agents: AgentInfo[] = rawAgents
      .filter(a => a.name)
      .map(a => ({
        name: String(a.name),
        hub: this.hub,
        capabilities: Array.isArray(a.capabilities)
          ? a.capabilities.map(String)
          : [],
        seams: Array.isArray(a.seams) ? a.seams.map(String) : [],
        pressure: typeof a.pressure === 'number' ? a.pressure : undefined,
      }))

    const darkCircles: DarkCircle[] = rawCircles
      .filter(c => c.name)
      .map(c => ({
        name: String(c.name),
        pressure: typeof c.pressure === 'number' ? c.pressure : 0,
        hub: this.hub,
      }))

    return {
      agents,
      darkCircles,
      timestamp: new Date().toISOString(),
    }
  }

  private log(msg: string): void {
    if (this.debug) console.log(`[PythonBridge:${this.hub}] ${msg}`)
  }
}
