// ── Hub Manager — federation hub lifecycle & auto-scaling ──────────

import { v4 as uuid } from 'uuid';
import type { HubInstance } from './types.js';

export interface HubManagerConfig {
  autoScale: boolean;
  maxInstances: number;
  healthIntervalMs: number;
  federationApiUrl: string;
  hubName: string;
}

export class HubManager {
  private hubs: Map<string, HubInstance> = new Map();
  private config: HubManagerConfig;
  private healthTimer: ReturnType<typeof setInterval> | null = null;

  constructor(config: Partial<HubManagerConfig> & { federationApiUrl: string; hubName: string }) {
    this.config = {
      autoScale: config.autoScale ?? process.env['HUB_AUTO_SCALE'] === 'true',
      maxInstances: config.maxInstances ?? parseInt(process.env['HUB_MAX_INSTANCES'] ?? '5', 10),
      healthIntervalMs: config.healthIntervalMs ?? parseInt(process.env['HUB_HEALTH_INTERVAL_MS'] ?? '30000', 10),
      federationApiUrl: config.federationApiUrl,
      hubName: config.hubName,
    };
  }

  // ── Hub lifecycle ─────────────────────────────────────────────────

  registerHub(url: string, name?: string): HubInstance {
    const id = uuid();
    const hub: HubInstance = {
      id,
      name: name ?? `${this.config.hubName}-${id.slice(0, 8)}`,
      url,
      status: 'starting',
      agentCount: 0,
      lastHealthCheck: 0,
      startedAt: Date.now(),
    };
    this.hubs.set(id, hub);
    console.log(`[hub-manager] Registered hub ${hub.name} at ${url}`);
    return hub;
  }

  deregisterHub(id: string): void {
    const hub = this.hubs.get(id);
    if (hub) {
      console.log(`[hub-manager] Deregistered hub ${hub.name}`);
      this.hubs.delete(id);
    }
  }

  // ── Health monitoring ─────────────────────────────────────────────

  async checkHealth(hubId: string): Promise<HubInstance> {
    const hub = this.hubs.get(hubId);
    if (!hub) throw new Error(`Hub ${hubId} not found`);

    try {
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 5000);

      const response = await fetch(`${hub.url}/status`, {
        signal: controller.signal,
      });
      clearTimeout(timeout);

      if (response.ok) {
        const data = (await response.json()) as { agents?: unknown[]; hub?: string };
        hub.status = 'healthy';
        hub.agentCount = Array.isArray(data.agents) ? data.agents.length : 0;
        hub.lastHealthCheck = Date.now();
      } else {
        hub.status = 'degraded';
        hub.lastHealthCheck = Date.now();
      }
    } catch {
      hub.status = 'down';
      hub.lastHealthCheck = Date.now();
      console.warn(`[hub-manager] Hub ${hub.name} is down`);
    }

    this.hubs.set(hubId, hub);
    return hub;
  }

  async checkAllHealth(): Promise<HubInstance[]> {
    const checks = Array.from(this.hubs.keys()).map((id) => this.checkHealth(id));
    return Promise.all(checks);
  }

  startHealthMonitoring(): void {
    if (this.healthTimer) return;
    this.healthTimer = setInterval(() => {
      this.checkAllHealth().catch((err) => console.error('[hub-manager] Health check error:', err));
    }, this.config.healthIntervalMs);
    console.log(`[hub-manager] Health monitoring started (${this.config.healthIntervalMs}ms interval)`);
  }

  stopHealthMonitoring(): void {
    if (this.healthTimer) {
      clearInterval(this.healthTimer);
      this.healthTimer = null;
    }
  }

  // ── Auto-scaling ──────────────────────────────────────────────────

  async evaluateScaling(): Promise<{ action: 'scale-up' | 'scale-down' | 'none'; reason: string }> {
    if (!this.config.autoScale) {
      return { action: 'none', reason: 'Auto-scaling disabled' };
    }

    const hubs = Array.from(this.hubs.values());
    const healthy = hubs.filter((h) => h.status === 'healthy');
    const totalAgents = healthy.reduce((sum, h) => sum + h.agentCount, 0);
    const avgAgentsPerHub = healthy.length > 0 ? totalAgents / healthy.length : 0;

    // Scale up if average agent count exceeds 50 per hub
    if (avgAgentsPerHub > 50 && hubs.length < this.config.maxInstances) {
      return {
        action: 'scale-up',
        reason: `Avg ${avgAgentsPerHub.toFixed(0)} agents/hub exceeds threshold (50). ${hubs.length}/${this.config.maxInstances} hubs active.`,
      };
    }

    // Scale down if we have multiple hubs with very low load
    if (healthy.length > 1 && avgAgentsPerHub < 5) {
      return {
        action: 'scale-down',
        reason: `Avg ${avgAgentsPerHub.toFixed(0)} agents/hub is low. Consider consolidating.`,
      };
    }

    return { action: 'none', reason: `Load normal (${avgAgentsPerHub.toFixed(0)} agents/hub avg)` };
  }

  // ── Discovery ─────────────────────────────────────────────────────

  async discoverHubs(seedUrls: string[]): Promise<HubInstance[]> {
    const discovered: HubInstance[] = [];

    for (const seedUrl of seedUrls) {
      try {
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), 5000);

        const response = await fetch(`${seedUrl}/peers`, {
          signal: controller.signal,
        });
        clearTimeout(timeout);

        if (response.ok) {
          const data = (await response.json()) as { peers?: { address?: string; hub?: string }[] };
          const peers = data.peers ?? [];

          for (const peer of peers) {
            if (peer.address && !this.hubs.has(peer.hub ?? peer.address)) {
              const hub = this.registerHub(peer.address, peer.hub);
              discovered.push(hub);
            }
          }
        }
      } catch {
        // Seed unreachable — skip
      }
    }

    return discovered;
  }

  // ── Query ─────────────────────────────────────────────────────────

  getHub(id: string): HubInstance | undefined {
    return this.hubs.get(id);
  }

  listHubs(): HubInstance[] {
    return Array.from(this.hubs.values());
  }

  getHealthyHubs(): HubInstance[] {
    return this.listHubs().filter((h) => h.status === 'healthy');
  }

  getPrimaryHub(): HubInstance | undefined {
    // Return the first healthy hub
    return this.getHealthyHubs()[0];
  }

  // ── Hub selection for task routing ────────────────────────────────

  selectHubForTask(capabilities?: string[]): HubInstance | null {
    const healthy = this.getHealthyHubs();
    if (healthy.length === 0) return null;

    // For now, round-robin-ish: pick the hub with the fewest agents (load balancing)
    // A more sophisticated version would match capabilities to hub specialty
    healthy.sort((a, b) => a.agentCount - b.agentCount);
    return healthy[0];
  }
}
