import type { AgentResult, DarkCircleInfo } from '../shared/types.js'
import type { AgentInfo, DarkCircle } from '../protocol/messages.js'

/**
 * In-memory capability index.
 * Tracks all agents across the federation and indexes them by capability.
 */
export class CapabilityIndex {
  /** Agent key → agent info. Key = "name@hub" */
  private agents: Map<string, AgentResult> = new Map()

  /** capability → Set of agent keys */
  private byCapability: Map<string, Set<string>> = new Map()

  /** Dark circle pressure, keyed by circle name */
  private darkCircles: Map<string, DarkCircleInfo> = new Map()

  /** Raw (unresolved) dark circle pressures per hub, keyed by "circleName:hub" */
  private rawPressures: Map<string, number> = new Map()

  // ── Agent management ────────────────────────────────────────────────────────

  upsertAgent(agent: AgentInfo, isLocal = false): { added: boolean; capChanges: { added: string[]; removed: string[] } } {
    const key = `${agent.name}@${agent.hub}`
    const prev = this.agents.get(key)

    const result: AgentResult = {
      name: agent.name,
      hub: agent.hub,
      capabilities: agent.capabilities,
      pressure: agent.pressure,
      seams: agent.seams,
      lastSeen: agent.lastSeen ?? new Date().toISOString(),
      isLocal,
    }

    let capChanges = { added: [] as string[], removed: [] as string[] }

    if (prev) {
      capChanges = {
        added: agent.capabilities.filter(c => !prev.capabilities.includes(c)),
        removed: prev.capabilities.filter(c => !agent.capabilities.includes(c)),
      }

      // Remove old capability mappings
      for (const cap of prev.capabilities) {
        this.byCapability.get(cap)?.delete(key)
      }
    }

    // Add new capability mappings
    for (const cap of agent.capabilities) {
      if (!this.byCapability.has(cap)) {
        this.byCapability.set(cap, new Set())
      }
      this.byCapability.get(cap)!.add(key)
    }

    this.agents.set(key, result)

    // If capabilities changed, re-resolve dark circles (new caps may cover gaps)
    if (capChanges.added.length > 0 || capChanges.removed.length > 0) {
      this.resolveDarkCircles()
    }

    return { added: !prev, capChanges }
  }

  removeAgent(name: string, hub: string): boolean {
    const key = `${name}@${hub}`
    const agent = this.agents.get(key)
    if (!agent) return false

    for (const cap of agent.capabilities) {
      this.byCapability.get(cap)?.delete(key)
    }

    this.agents.delete(key)
    return true
  }

  /**
   * Remove all agents from a given hub (peer disconnected).
   */
  removeHub(hub: string): string[] {
    const removed: string[] = []
    for (const [key, agent] of this.agents.entries()) {
      if (agent.hub === hub) {
        this.removeAgent(agent.name, hub)
        removed.push(key)
      }
    }
    return removed
  }

  getAgent(name: string, hub: string): AgentResult | undefined {
    return this.agents.get(`${name}@${hub}`)
  }

  getAgentByKey(key: string): AgentResult | undefined {
    return this.agents.get(key)
  }

  getAllAgents(): AgentResult[] {
    return Array.from(this.agents.values())
  }

  getLocalAgents(): AgentResult[] {
    return Array.from(this.agents.values()).filter(a => a.isLocal)
  }

  getAgentsByHub(hub: string): AgentResult[] {
    return Array.from(this.agents.values()).filter(a => a.hub === hub)
  }

  // ── Capability queries ───────────────────────────────────────────────────────

  /**
   * Find all agents that have a given capability.
   * Optionally filter by minimum pressure.
   */
  findByCapability(capability: string, minPressure?: number): AgentResult[] {
    const keys = this.byCapability.get(capability)
    if (!keys || keys.size === 0) return []

    const results: AgentResult[] = []
    for (const key of keys) {
      const agent = this.agents.get(key)
      if (!agent) continue
      if (minPressure !== undefined && (agent.pressure ?? 0) < minPressure) continue
      results.push(agent)
    }

    return results
  }

  /**
   * Get all known capabilities across the federation.
   */
  getAllCapabilities(): string[] {
    return Array.from(this.byCapability.keys()).filter(
      cap => (this.byCapability.get(cap)?.size ?? 0) > 0,
    )
  }

  // ── Dark circles ─────────────────────────────────────────────────────────────

  updateDarkCircles(hub: string, circles: DarkCircle[]): string[] {
    for (const dc of circles) {
      const key = dc.name

      // Store raw pressure before resolution
      this.rawPressures.set(`${key}:${hub}`, dc.pressure)

      const existing = this.darkCircles.get(key) ?? {
        name: dc.name,
        pressure: 0,
        byHub: {},
      }

      existing.byHub = existing.byHub ?? {}
      existing.byHub[hub] = dc.pressure  // track which hubs report this circle

      this.darkCircles.set(key, existing)
    }

    return this.resolveDarkCircles()
  }

  getDarkCircles(): DarkCircleInfo[] {
    return Array.from(this.darkCircles.values())
  }

  /**
   * Find agents whose capabilities cover a dark circle by prefix match.
   * A capability "detection" covers circles named "detection-modeling",
   * "detection-solar", etc. Also matches exact names.
   */
  private findCoveringAgents(circleName: string): AgentResult[] {
    const seen = new Set<string>()
    const results: AgentResult[] = []

    for (const [cap, keys] of this.byCapability.entries()) {
      if (circleName === cap || circleName.startsWith(cap + '-') || cap.startsWith(circleName + '-')) {
        for (const key of keys) {
          if (!seen.has(key)) {
            seen.add(key)
            const agent = this.agents.get(key)
            if (agent) results.push(agent)
          }
        }
      }
    }

    return results
  }

  /**
   * Resolve dark circles by matching agent capabilities against circle names.
   * A capability covers a circle if it exactly matches or is a prefix of
   * the circle name (e.g. "detection" covers "detection-modeling").
   * Covered circles have pressure reduced: raw × 1/(1 + coverCount).
   * Idempotent — always recalculates from raw pressures, so repeated calls
   * are stable.
   *
   * Returns list of circles whose resolved pressure changed.
   */
  resolveDarkCircles(): string[] {
    const changed: string[] = []

    for (const [circleName, circle] of this.darkCircles.entries()) {
      const coveringAgents = this.findCoveringAgents(circleName)
      const coverCount = coveringAgents.length
      const factor = 1 / (1 + coverCount)  // 0 agents → 1.0, 1 → 0.5, 2 → 0.33

      // Recompute per-hub resolved pressures from raw
      let maxResolved = 0
      if (!circle.byHub) circle.byHub = {}
      const hubs = Object.keys(circle.byHub)

      for (const hub of hubs) {
        const raw = this.rawPressures.get(`${circleName}:${hub}`) ?? 0
        const resolved = raw * factor
        circle.byHub[hub] = resolved
        if (resolved > maxResolved) maxResolved = resolved
      }

      const prevPressure = circle.pressure
      circle.pressure = maxResolved

      if (Math.abs(circle.pressure - prevPressure) > 0.001) {
        changed.push(circleName)
      }
    }

    return changed
  }

  getDarkCircle(name: string): DarkCircleInfo | undefined {
    return this.darkCircles.get(name)
  }

  // ── Stats ────────────────────────────────────────────────────────────────────

  stats(): { agents: number; capabilities: number; darkCircles: number; hubs: Set<string> } {
    const hubs = new Set<string>()
    for (const a of this.agents.values()) hubs.add(a.hub)
    return {
      agents: this.agents.size,
      capabilities: this.byCapability.size,
      darkCircles: this.darkCircles.size,
      hubs,
    }
  }
}
