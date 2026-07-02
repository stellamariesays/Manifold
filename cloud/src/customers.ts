// ── Customer store & API key management ─────────────────────────────

import { createHash, randomBytes } from 'node:crypto';
import type { Customer, Tier } from './types.js';

export interface CustomerStore {
  create(email: string, tier: Tier, stripeCustomerId?: string): Promise<Customer>;
  getByApiKey(key: string): Promise<Customer | null>;
  getById(id: string): Promise<Customer | null>;
  updateTier(id: string, tier: Tier): Promise<void>;
  list(): Promise<Customer[]>;
}

// ── Generate Manifold API keys ──────────────────────────────────────

export function generateApiKey(tier: Tier): string {
  const prefix = tier === 'free' ? 'mk_test_' : 'mk_live_';
  const rand = randomBytes(24).toString('hex');
  return `${prefix}${rand}`;
}

export function hashApiKey(key: string): string {
  return createHash('sha256').update(key).digest('hex');
}

// ── In-memory store (production: swap for Redis or Postgres) ────────

export class MemoryCustomerStore implements CustomerStore {
  private customers: Map<string, Customer> = new Map();
  private apiKeyIndex: Map<string, string> = new Map(); // hash → customerId

  async create(email: string, tier: Tier, stripeCustomerId?: string): Promise<Customer> {
    const { v4: uuid } = await import('uuid');
    const apiKey = generateApiKey(tier);
    const id = uuid();

    const customer: Customer = {
      id,
      email: email.toLowerCase(),
      apiKey: hashApiKey(apiKey),
      tier,
      stripeCustomerId: stripeCustomerId ?? null,
      createdAt: Date.now(),
    };

    this.customers.set(id, customer);
    this.apiKeyIndex.set(customer.apiKey, id);

    // Return with the plaintext key — only time it's visible
    return { ...customer, apiKey };
  }

  async getByApiKey(key: string): Promise<Customer | null> {
    const hashed = hashApiKey(key);
    const id = this.apiKeyIndex.get(hashed);
    if (!id) return null;
    return this.customers.get(id) ?? null;
  }

  async getById(id: string): Promise<Customer | null> {
    return this.customers.get(id) ?? null;
  }

  async updateTier(id: string, tier: Tier): Promise<void> {
    const c = this.customers.get(id);
    if (c) {
      // Reissue key with correct prefix on tier change
      const newKey = generateApiKey(tier);
      this.apiKeyIndex.delete(c.apiKey);
      c.apiKey = hashApiKey(newKey);
      c.tier = tier;
      this.apiKeyIndex.set(c.apiKey, id);
      this.customers.set(id, c);
    }
  }

  async list(): Promise<Customer[]> {
    return Array.from(this.customers.values());
  }
}
