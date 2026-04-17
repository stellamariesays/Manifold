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

  /** Dark circle pressure, keyed by "name@hub" or "name" for aggregate */
  private darkCircles: Map<string, DarkCircleInfo> = new Map()

  // ── Agent management ────────────────────────────────────────────────────────

  upsertAgent(agent: AgentInfo, isLocal = false): { added: boolean; capChanges: { added: string[]; removed: string[] } } {
    const key = `${agent.name}@${agent.hub}`
    const prev = this.agents.get(key)

    // Merge capabilities: union of existing + new (never removes caps added by other sources)
    const mergedCaps = prev
      ? [...new Set([...prev.capabilities, ...agent.capabilities])]
      : agent.capabilities

    const result: AgentResult = {
      name: agent.name,
      hub: agent.hub,
      capabilities: mergedCaps,
      pressure: agent.pressure ?? prev?.pressure ?? 0.5,
      seams: agent.seams ?? prev?.seams ?? [],
      lastSeen: agent.lastSeen ?? new Date().toISOString(),
      isLocal,
    }

    let capChanges = { added: [] as string[], removed: [] as string[] }

    if (prev) {
      capChanges = {
        added: mergedCaps.filter(c => !prev.capabilities.includes(c)),
        removed: [], // union merge never removes
      }

      // Remove old capability mappings for caps no longer present
      for (const cap of prev.capabilities) {
        if (!mergedCaps.includes(cap)) {
          this.byCapability.get(cap)?.delete(key)
        }
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

  updateDarkCircles(hub: string, circles: DarkCircle[]): void {
    for (const dc of circles) {
      const key = dc.name

      const existing = this.darkCircles.get(key) ?? {
        name: dc.name,
        pressure: 0,
        byHub: {},
      }

      existing.byHub = existing.byHub ?? {}
      existing.byHub[hub] = dc.pressure

      // Aggregate pressure: max across hubs (alternatively could be avg or sum)
      existing.pressure = Math.max(...Object.values(existing.byHub))

      this.darkCircles.set(key, existing)
    }
  }

  getDarkCircles(): DarkCircleInfo[] {
    return Array.from(this.darkCircles.values())
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
