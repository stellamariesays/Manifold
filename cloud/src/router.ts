// ── Model Router — routes tasks to best model by capability & cost ──

import type { ModelEntry, ModelCapability, RouteRequest, RouteDecision } from './types.js';

// ── Model registry ──────────────────────────────────────────────────

const MODEL_REGISTRY: ModelEntry[] = [
  // OpenAI
  {
    id: 'gpt-4o',
    provider: 'openai',
    contextWindow: 128_000,
    costPerMtokInput: 2.5,
    costPerMtokOutput: 10,
    capabilities: ['chat', 'code', 'vision', 'reasoning', 'tool-use'],
    priority: 10,
  },
  {
    id: 'gpt-4o-mini',
    provider: 'openai',
    contextWindow: 128_000,
    costPerMtokInput: 0.15,
    costPerMtokOutput: 0.6,
    capabilities: ['chat', 'code', 'vision', 'fast', 'tool-use'],
    priority: 5,
  },
  {
    id: 'o3-mini',
    provider: 'openai',
    contextWindow: 200_000,
    costPerMtokInput: 3,
    costPerMtokOutput: 12,
    capabilities: ['chat', 'code', 'reasoning', 'tool-use'],
    priority: 15,
  },

  // Anthropic
  {
    id: 'claude-sonnet-4-20250514',
    provider: 'anthropic',
    contextWindow: 200_000,
    costPerMtokInput: 3,
    costPerMtokOutput: 15,
    capabilities: ['chat', 'code', 'vision', 'reasoning', 'tool-use', 'long-context'],
    priority: 8,
  },
  {
    id: 'claude-3-5-haiku-20241022',
    provider: 'anthropic',
    contextWindow: 200_000,
    costPerMtokInput: 0.8,
    costPerMtokOutput: 4,
    capabilities: ['chat', 'code', 'fast', 'tool-use', 'long-context'],
    priority: 4,
  },

  // Google
  {
    id: 'gemini-2.5-pro',
    provider: 'google',
    contextWindow: 2_000_000,
    costPerMtokInput: 1.25,
    costPerMtokOutput: 5,
    capabilities: ['chat', 'code', 'vision', 'reasoning', 'tool-use', 'long-context'],
    priority: 7,
  },
  {
    id: 'gemini-2.5-flash',
    provider: 'google',
    contextWindow: 1_000_000,
    costPerMtokInput: 0.075,
    costPerMtokOutput: 0.3,
    capabilities: ['chat', 'code', 'vision', 'fast', 'tool-use', 'long-context'],
    priority: 3,
  },

  // Local (Ollama / vLLM / llama.cpp)
  {
    id: 'llama-3.3-70b',
    provider: 'local',
    contextWindow: 128_000,
    costPerMtokInput: 0,
    costPerMtokOutput: 0,
    capabilities: ['chat', 'code', 'reasoning'],
    priority: 20,
  },
  {
    id: 'qwen-2.5-coder-32b',
    provider: 'local',
    contextWindow: 32_000,
    costPerMtokInput: 0,
    costPerMtokOutput: 0,
    capabilities: ['chat', 'code'],
    priority: 25,
  },
];

// ── Provider health tracking ────────────────────────────────────────

interface ProviderHealth {
  name: string;
  available: boolean;
  avgLatencyMs: number;
  errorRate: number;
  lastChecked: number;
  consecutiveFailures: number;
}

export class ModelRouter {
  private health: Map<string, ProviderHealth> = new Map();
  private providerKeys: Map<string, string> = new Map();
  private localModelUrl: string | null;

  constructor(opts: {
    openaiKey?: string;
    anthropicKey?: string;
    googleKey?: string;
    localModelUrl?: string;
  }) {
    if (opts.openaiKey) this.providerKeys.set('openai', opts.openaiKey);
    if (opts.anthropicKey) this.providerKeys.set('anthropic', opts.anthropicKey);
    if (opts.googleKey) this.providerKeys.set('google', opts.googleKey);
    this.localModelUrl = opts.localModelUrl ?? null;

    // Initialize health for all providers
    for (const provider of ['openai', 'anthropic', 'google', 'local']) {
      this.health.set(provider, {
        name: provider,
        available: this.isProviderConfigured(provider),
        avgLatencyMs: 0,
        errorRate: 0,
        lastChecked: 0,
        consecutiveFailures: 0,
      });
    }
  }

  private isProviderConfigured(provider: string): boolean {
    if (provider === 'local') return this.localModelUrl !== null;
    return this.providerKeys.has(provider);
  }

  // ── Core routing logic ────────────────────────────────────────────

  route(request: RouteRequest): RouteDecision {
    const requiredCaps = request.capabilities ?? ['chat'];
    const maxTokens = request.maxTokens ?? 4096;
    const preferCheapest = request.preferCheapest ?? true;

    // Filter models that meet all required capabilities and context window
    const candidates = MODEL_REGISTRY.filter((model) => {
      const hasAllCaps = requiredCaps.every((cap) => model.capabilities.includes(cap));
      const fitsContext = model.contextWindow >= maxTokens * 2; // leave room
      const providerHealthy = this.health.get(model.provider)?.available ?? false;
      return hasAllCaps && fitsContext && providerHealthy;
    });

    if (candidates.length === 0) {
      // Fallback — relax to any available provider with chat
      const fallback = MODEL_REGISTRY.filter((model) => {
        const providerHealthy = this.health.get(model.provider)?.available ?? false;
        return model.capabilities.includes('chat') && providerHealthy;
      });

      if (fallback.length === 0) {
        // Last resort: return a default even if provider isn't confirmed available
        const defaultModel = MODEL_REGISTRY[0];
        return {
          provider: defaultModel.provider,
          model: defaultModel.id,
          estimatedCost: this.estimateCost(defaultModel, maxTokens),
          reasoning: 'No providers verified healthy — using default. All providers may be unconfigured.',
        };
      }

      const cheapest = fallback.sort((a, b) => a.costPerMtokInput + a.costPerMtokOutput - b.costPerMtokInput - b.costPerMtokOutput)[0];
      return {
        provider: cheapest.provider,
        model: cheapest.id,
        estimatedCost: this.estimateCost(cheapest, maxTokens),
        reasoning: `Relaxed match — no model met all capabilities. Selected cheapest available with chat.`,
      };
    }

    // Sort: cheapest first if preferCheapest, otherwise by priority (best quality first)
    let selected: ModelEntry;
    if (preferCheapest) {
      candidates.sort((a, b) => {
        const costA = a.costPerMtokInput + a.costPerMtokOutput;
        const costB = b.costPerMtokInput + b.costPerMtokOutput;
        if (costA !== costB) return costA - costB;
        return a.priority - b.priority;
      });
      selected = candidates[0];
    } else {
      candidates.sort((a, b) => a.priority - b.priority);
      selected = candidates[0];
    }

    return {
      provider: selected.provider,
      model: selected.id,
      estimatedCost: this.estimateCost(selected, maxTokens),
      reasoning: `Matched ${requiredCaps.join(', ')} — ${selected.provider}/${selected.id} @ $${selected.costPerMtokInput}/Mtok in`,
    };
  }

  private estimateCost(model: ModelEntry, maxTokens: number): number {
    const inputTokens = Math.ceil(maxTokens * 0.3); // rough estimate
    const outputTokens = Math.ceil(maxTokens * 0.7);
    return (inputTokens / 1_000_000) * model.costPerMtokInput + (outputTokens / 1_000_000) * model.costPerMtokOutput;
  }

  // ── Health checking ───────────────────────────────────────────────

  async checkProviderHealth(provider: string): Promise<ProviderHealth> {
    const current = this.health.get(provider) ?? {
      name: provider,
      available: false,
      avgLatencyMs: 0,
      errorRate: 0,
      lastChecked: 0,
      consecutiveFailures: 0,
    };

    if (!this.isProviderConfigured(provider)) {
      const updated = { ...current, available: false, lastChecked: Date.now() };
      this.health.set(provider, updated);
      return updated;
    }

    // For configured providers, we'd do a lightweight API ping.
    // Since this is infrastructure code, we mark available based on config.
    const updated: ProviderHealth = {
      ...current,
      available: true,
      lastChecked: Date.now(),
      consecutiveFailures: 0,
    };
    this.health.set(provider, updated);
    return updated;
  }

  async checkAllHealth(): Promise<ProviderHealth[]> {
    const providers = ['openai', 'anthropic', 'google', 'local'];
    return Promise.all(providers.map((p) => this.checkProviderHealth(p)));
  }

  // ── Failover ──────────────────────────────────────────────────────

  selectFailover(failedProvider: string, request: RouteRequest): RouteDecision | null {
    const requiredCaps = request.capabilities ?? ['chat'];
    const candidates = MODEL_REGISTRY.filter((model) => {
      if (model.provider === failedProvider) return false;
      const providerHealthy = this.health.get(model.provider)?.available ?? false;
      const hasAllCaps = requiredCaps.every((cap) => model.capabilities.includes(cap));
      return hasAllCaps && providerHealthy;
    });

    if (candidates.length === 0) return null;

    candidates.sort((a, b) => a.costPerMtokInput + a.costPerMtokOutput - b.costPerMtokInput - b.costPerMtokOutput);
    const selected = candidates[0];

    return {
      provider: selected.provider,
      model: selected.id,
      estimatedCost: this.estimateCost(selected, request.maxTokens ?? 4096),
      reasoning: `Failover from ${failedProvider} → ${selected.provider}/${selected.id}`,
    };
  }

  // ── List available models ─────────────────────────────────────────

  listModels(provider?: string): ModelEntry[] {
    if (provider) return MODEL_REGISTRY.filter((m) => m.provider === provider);
    return MODEL_REGISTRY;
  }

  getHealthStatus(): ProviderHealth[] {
    return Array.from(this.health.values());
  }
}
