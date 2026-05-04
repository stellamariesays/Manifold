/**
 * meshlet-manager.ts — Ephemeral meshlet lifecycle manager.
 *
 * Spawns, tracks, and destroys temporary meshlet instances. Each meshlet is
 * an isolated sandbox for agent development — either a real Elixir/BEAM node
 * or a TypeScript-simulated equivalent.
 *
 * Meshlets expose the void/beam/ssj2 tooling surface so users can develop
 * agents before promoting them to the full Manifold federation.
 */
import { randomUUID } from 'crypto'
import { EventEmitter } from 'events'
import { ChildProcess, spawn } from 'child_process'

// ── Types ──────────────────────────────────────────────────────────────────────

export interface VoidState {
  term: string
  impliedBy: string[]
  pressure: number
  bornAt: number
  named?: string   // agent name if graduated
}

export interface MeshletState {
  id: string
  owner: string          // access code or user id
  createdAt: number
  expiresAt: number
  mode: 'beam' | 'simulated'
  voids: Map<string, VoidState>
  agents: RegisteredAgent[]
  processCount: number
  memoryMb: number
  uptimeSec: number
  status: 'starting' | 'running' | 'expired' | 'destroyed'
}

export interface RegisteredAgent {
  name: string
  capabilities: string[]
  seams: string[]
  config: Record<string, unknown>
}

export interface MeshletEvent {
  meshletId: string
  type: string
  payload: Record<string, unknown>
}

export interface MeshletManagerConfig {
  /** Max concurrent meshlets per owner. Default 3. */
  maxPerOwner?: number
  /** Default TTL in ms. Default 2h. */
  defaultTtlMs?: number
  /** Max BEAM memory per meshlet in MB. Default 64. */
  maxMemoryMb?: number
  /** Whether Elixir runtime is available. Auto-detected if unset. */
  elixirAvailable?: boolean
  debug?: boolean
}

// ── Manager ────────────────────────────────────────────────────────────────────

export class MeshletManager extends EventEmitter {
  private readonly meshlets = new Map<string, MeshletState>()
  private readonly processes = new Map<string, ChildProcess>()
  private readonly ownerCounts = new Map<string, number>()
  private readonly config: Required<MeshletManagerConfig>
  private cleanupTimer: ReturnType<typeof setInterval> | null = null

  constructor(config?: MeshletManagerConfig) {
    super()
    this.config = {
      maxPerOwner: config?.maxPerOwner ?? 3,
      defaultTtlMs: config?.defaultTtlMs ?? 2 * 60 * 60 * 1000,
      maxMemoryMb: config?.maxMemoryMb ?? 64,
      elixirAvailable: config?.elixirAvailable ?? false,
      debug: config?.debug ?? false,
    }
  }

  start(): void {
    // Run cleanup every 60s
    this.cleanupTimer = setInterval(() => this._cleanup(), 60_000)
    this.log('Started')
  }

  stop(): void {
    if (this.cleanupTimer) clearInterval(this.cleanupTimer)
    for (const [id, proc] of this.processes) {
      proc.kill('SIGTERM')
      this.processes.delete(id)
    }
    this.meshlets.clear()
    this.log('Stopped')
  }

  // ── CRUD ─────────────────────────────────────────────────────────────────────

  /** Create a new meshlet for the given owner. */
  create(owner: string): MeshletState {
    const currentCount = this.ownerCounts.get(owner) ?? 0
    if (currentCount >= this.config.maxPerOwner) {
      throw new Error(`Meshlet limit reached (${this.config.maxPerOwner} per user)`)
    }

    const id = randomUUID()
    const now = Date.now()
    const mode: 'beam' | 'simulated' = this.config.elixirAvailable ? 'beam' : 'simulated'

    const state: MeshletState = {
      id,
      owner,
      createdAt: now,
      expiresAt: now + this.config.defaultTtlMs,
      mode,
      voids: new Map(),
      agents: [],
      processCount: 1, // main supervisor
      memoryMb: 0,
      uptimeSec: 0,
      status: 'starting',
    }

    this.meshlets.set(id, state)
    this.ownerCounts.set(owner, currentCount + 1)

    if (mode === 'beam') {
      this._spawnElixirNode(id)
    }

    // Simulated mode: mark running immediately
    if (mode === 'simulated') {
      state.status = 'running'
      state.memoryMb = 4.2
      state.processCount = 3 // Field + Scout + Memory
    }

    this._emit(id, 'meshlet:created', { mode, expiresAt: state.expiresAt })
    this.log(`Created meshlet ${id.slice(0, 8)} (${mode}) for ${owner}`)
    return this._snapshot(state)
  }

  /** Get meshlet status. */
  get(id: string): MeshletState | null {
    const state = this.meshlets.get(id)
    return state ? this._snapshot(state) : null
  }

  /** List all meshlets for an owner. */
  list(owner: string): MeshletState[] {
    const result: MeshletState[] = []
    for (const state of this.meshlets.values()) {
      if (state.owner === owner) {
        result.push(this._snapshot(state))
      }
    }
    return result
  }

  /** Destroy a meshlet. */
  destroy(id: string): boolean {
    const state = this.meshlets.get(id)
    if (!state) return false

    const proc = this.processes.get(id)
    if (proc) {
      proc.kill('SIGTERM')
      this.processes.delete(id)
    }

    state.status = 'destroyed'
    this.meshlets.delete(id)
    const count = this.ownerCounts.get(state.owner) ?? 1
    this.ownerCounts.set(state.owner, Math.max(0, count - 1))

    this._emit(id, 'meshlet:destroyed', {})
    this.log(`Destroyed meshlet ${id.slice(0, 8)}`)
    return true
  }

  // ── Void Operations ──────────────────────────────────────────────────────────

  /** Open a void in the meshlet. */
  openVoid(meshletId: string, term: string, impliedBy: string[] = [], pressure = 0.0): VoidState {
    const state = this._getRunning(meshletId)
    if (state.voids.has(term)) {
      throw new Error(`Void "${term}" already exists`)
    }

    const voidState: VoidState = {
      term,
      impliedBy,
      pressure,
      bornAt: Date.now(),
    }

    state.voids.set(term, voidState)
    this._emit(meshletId, 'void:opened', { term, pressure })

    // In simulated mode, update process count
    if (state.mode === 'simulated') {
      state.processCount++
      state.memoryMb += 0.3
    }

    return { ...voidState }
  }

  /** Query all active voids. */
  queryVoids(meshletId: string): VoidState[] {
    const state = this._getRunning(meshletId)
    return Array.from(state.voids.values()).map(v => ({ ...v }))
  }

  /** Update void pressure. */
  updatePressure(meshletId: string, term: string, delta: number): VoidState {
    const state = this._getRunning(meshletId)
    const v = state.voids.get(term)
    if (!v) throw new Error(`Void "${term}" not found`)
    if (v.named) throw new Error(`Void "${term}" already named — graduated to agent "${v.named}"`)

    v.pressure = Math.max(0, Math.min(1, v.pressure + delta))
    this._emit(meshletId, 'void:pressure', { term, pressure: v.pressure })
    return { ...v }
  }

  /** Name a void — graduates it to a named agent. */
  nameVoid(meshletId: string, term: string, agentName: string): VoidState {
    const state = this._getRunning(meshletId)
    const v = state.voids.get(term)
    if (!v) throw new Error(`Void "${term}" not found`)
    if (v.named) throw new Error(`Void "${term}" already named`)

    v.named = agentName
    this._emit(meshletId, 'void:named', { term, agent: agentName })
    return { ...v }
  }

  // ── Agent Operations ─────────────────────────────────────────────────────────

  /** Register an agent in the meshlet. */
  registerAgent(meshletId: string, agent: RegisteredAgent): void {
    const state = this._getRunning(meshletId)
    if (state.agents.some(a => a.name === agent.name)) {
      throw new Error(`Agent "${agent.name}" already registered`)
    }
    state.agents.push(agent)
    this._emit(meshletId, 'agent:registered', { name: agent.name, capabilities: agent.capabilities })
  }

  /** Get all registered agents. */
  getAgents(meshletId: string): RegisteredAgent[] {
    const state = this._getRunning(meshletId)
    return [...state.agents]
  }

  // ── SSJ2 Operations ──────────────────────────────────────────────────────────

  /** Run a reach scan — detect implied terms from void surroundings. */
  reachScan(meshletId: string): { terms: string[]; signals: Array<{ seam: string; strength: number }> } {
    const state = this._getRunning(meshletId)
    const voids = Array.from(state.voids.values())

    // Simulated SSJ2: derive signals from void relationships
    const allImplied = new Set<string>()
    for (const v of voids) {
      if (!v.named) {
        for (const imp of v.impliedBy) {
          allImplied.add(imp)
        }
      }
    }

    // Find unnamed voids that are implied by other voids' terms
    const voidTerms = new Set(voids.filter(v => !v.named).map(v => v.term))
    const signals: Array<{ seam: string; strength: number }> = []

    for (const v of voids) {
      if (v.named) continue
      const overlap = v.impliedBy.filter(imp => voidTerms.has(imp)).length
      if (overlap > 0) {
        signals.push({
          seam: v.term,
          strength: Math.min(1, v.pressure + overlap * 0.15),
        })
      }
    }

    // Sort by strength descending
    signals.sort((a, b) => b.strength - a.strength)

    return {
      terms: Array.from(allImplied),
      signals,
    }
  }

  /** Get BEAM status. */
  beamStatus(meshletId: string): { processes: number; memoryMb: number; uptimeSec: number } {
    const state = this._getRunning(meshletId)
    state.uptimeSec = Math.floor((Date.now() - state.createdAt) / 1000)
    return {
      processes: state.processCount,
      memoryMb: state.memoryMb,
      uptimeSec: state.uptimeSec,
    }
  }

  // ── Stats ────────────────────────────────────────────────────────────────────

  get totalMeshlets(): number {
    return this.meshlets.size
  }

  // ── Private ──────────────────────────────────────────────────────────────────

  private _getRunning(id: string): MeshletState {
    const state = this.meshlets.get(id)
    if (!state) throw new Error(`Meshlet ${id} not found`)
    if (state.status !== 'running' && state.status !== 'starting') {
      throw new Error(`Meshlet ${id} is ${state.status}`)
    }
    // Auto-transition starting → running after 2s (simulated)
    if (state.status === 'starting' && state.mode === 'simulated') {
      state.status = 'running'
    }
    return state
  }

  private _snapshot(state: MeshletState): MeshletState {
    return {
      ...state,
      voids: new Map(state.voids),
      agents: [...state.agents],
    }
  }

  private _spawnElixirNode(id: string): void {
    // Spawn an isolated Elixir node running Numinous.Application
    const proc = spawn('elixir', [
      '--sname', `meshlet_${id.slice(0, 8)}`,
      '-S', 'mix', 'numinous.open',
    ], {
      cwd: process.env.NUMINOUS_PATH || '../numinous/elixir',
      stdio: ['pipe', 'pipe', 'pipe'],
      env: {
        ...process.env,
        MESHLET_ID: id,
        BEAM_MAX_MEMORY: `${this.config.maxMemoryMb * 1024 * 1024}`,
      },
    })

    this.processes.set(id, proc)

    proc.stdout?.on('data', (data: Buffer) => {
      const line = data.toString().trim()
      if (line.includes('void:')) {
        // Parse Elixir void events and emit
        this.log(`[beam:${id.slice(0, 8)}] ${line}`)
      }
    })

    proc.stderr?.on('data', (data: Buffer) => {
      this.log(`[beam:${id.slice(0, 8)}] ERR: ${data.toString().trim()}`)
    })

    proc.on('exit', (code) => {
      this.log(`[beam:${id.slice(0, 8)}] exited with code ${code}`)
      const state = this.meshlets.get(id)
      if (state && state.status !== 'destroyed') {
        state.status = 'expired'
        this._emit(id, 'meshlet:expired', { exitCode: code })
      }
      this.processes.delete(id)
    })
  }

  private _cleanup(): void {
    const now = Date.now()
    for (const [id, state] of this.meshlets) {
      if (now >= state.expiresAt && state.status !== 'destroyed') {
        this.log(`Expiring meshlet ${id.slice(0, 8)} (TTL)`)
        state.status = 'expired'
        this.destroy(id)
      }
    }
  }

  private _emit(meshletId: string, type: string, payload: Record<string, unknown>): void {
    this.emit('meshlet-event', { meshletId, type, payload } as MeshletEvent)
  }

  private log(msg: string): void {
    if (this.config.debug) console.log(`[MeshletManager] ${msg}`)
  }
}
