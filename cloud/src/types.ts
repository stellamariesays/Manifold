// ── Shared types for Manifold Cloud ─────────────────────────────────

export type Tier = 'free' | 'pro' | 'enterprise';

export interface TierConfig {
  name: Tier;
  price: number;
  requestLimitMonthly: number;
  rateLimitPerMin: number;
  features: string[];
}

export const TIERS: Record<Tier, TierConfig> = {
  free: {
    name: 'free',
    price: 0,
    requestLimitMonthly: 100,
    rateLimitPerMin: 10,
    features: ['Community support', 'Single hub', 'Basic routing'],
  },
  pro: {
    name: 'pro',
    price: 29,
    requestLimitMonthly: 10_000,
    rateLimitPerMin: 100,
    features: ['Priority support', 'Multi-hub federation', 'Advanced routing', 'Usage analytics'],
  },
  enterprise: {
    name: 'enterprise',
    price: 299,
    requestLimitMonthly: 100_000,
    rateLimitPerMin: Infinity,
    features: ['Dedicated support', 'Unlimited hubs', 'Custom routing', 'SLA guarantee', 'On-prem option'],
  },
};

export interface Customer {
  id: string;
  email: string;
  apiKey: string;
  tier: Tier;
  stripeCustomerId: string | null;
  createdAt: number;
}

export interface UsageRecord {
  customerId: string;
  month: string; // YYYY-MM
  requestCount: number;
  tokensRouted: number;
}

export interface ModelProvider {
  name: string;
  models: ModelEntry[];
  apiKeyEnv: string;
  baseUrl: string;
}

export interface ModelEntry {
  id: string;
  provider: string;
  contextWindow: number;
  costPerMtokInput: number;
  costPerMtokOutput: number;
  capabilities: ModelCapability[];
  priority: number; // lower = preferred
}

export type ModelCapability =
  | 'chat'
  | 'code'
  | 'vision'
  | 'reasoning'
  | 'tool-use'
  | 'long-context'
  | 'fast';

export interface RouteRequest {
  prompt: string;
  capabilities?: ModelCapability[];
  maxTokens?: number;
  preferCheapest?: boolean;
}

export interface RouteDecision {
  provider: string;
  model: string;
  estimatedCost: number;
  reasoning: string;
}

export interface HubInstance {
  id: string;
  name: string;
  url: string;
  status: 'healthy' | 'degraded' | 'down' | 'starting';
  agentCount: number;
  lastHealthCheck: number;
  startedAt: number;
}

export interface ApiResponse<T> {
  success: boolean;
  data?: T;
  error?: string;
  requestId?: string;
}
