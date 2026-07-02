// ── Usage tracking via Redis ────────────────────────────────────────

import type { Tier, UsageRecord } from './types.js';

export interface UsageStore {
  increment(customerId: string, tokens: number): Promise<UsageRecord>;
  getMonthly(customerId: string, month?: string): Promise<UsageRecord>;
  checkLimit(customerId: string, tier: Tier): Promise<boolean>;
  resetMonth(customerId: string, month: string): Promise<void>;
}

// ── Redis-backed implementation ─────────────────────────────────────

import Redis from 'ioredis';

export class RedisUsageStore implements UsageStore {
  private redis: Redis;

  constructor(redisUrl: string) {
    this.redis = new Redis(redisUrl, { maxRetriesPerRequest: 3 });
  }

  private monthKey(customerId: string, month?: string): string {
    const m = month ?? new Date().toISOString().slice(0, 7);
    return `usage:${customerId}:${m}`;
  }

  async increment(customerId: string, tokens: number): Promise<UsageRecord> {
    const month = new Date().toISOString().slice(0, 7);
    const key = this.monthKey(customerId, month);
    const field = month;

    const [reqCount, tokCount] = await this.redis
      .multi()
      .hincrby(key, 'requests', 1)
      .hincrby(key, 'tokens', tokens)
      .hset(key, 'month', month)
      .hset(key, 'customerId', customerId)
      .exec()
      .then((results) => {
        if (!results) return [0, 0];
        return [results[0]?.[1] as number, results[1]?.[1] as number];
      });

    return {
      customerId,
      month,
      requestCount: reqCount,
      tokensRouted: tokCount,
    };
  }

  async getMonthly(customerId: string, month?: string): Promise<UsageRecord> {
    const m = month ?? new Date().toISOString().slice(0, 7);
    const key = this.monthKey(customerId, m);
    const data = await this.redis.hgetall(key);

    return {
      customerId,
      month: m,
      requestCount: parseInt(data['requests'] ?? '0', 10),
      tokensRouted: parseInt(data['tokens'] ?? '0', 10),
    };
  }

  async checkLimit(customerId: string, tier: Tier): Promise<boolean> {
    const { TIERS } = require('./types.js') as typeof import('./types.js');
    const limit = TIERS[tier].requestLimitMonthly;
    if (limit === Infinity) return true;
    const usage = await this.getMonthly(customerId);
    return usage.requestCount < limit;
  }

  async resetMonth(customerId: string, month: string): Promise<void> {
    const key = this.monthKey(customerId, month);
    await this.redis.del(key);
  }

  async close(): Promise<void> {
    await this.redis.quit();
  }
}

// ── In-memory implementation (dev / no Redis) ───────────────────────

export class MemoryUsageStore implements UsageStore {
  private records = new Map<string, UsageRecord>();

  private monthKey(customerId: string, month?: string): string {
    const m = month ?? new Date().toISOString().slice(0, 7);
    return `${customerId}:${m}`;
  }

  async increment(customerId: string, tokens: number): Promise<UsageRecord> {
    const month = new Date().toISOString().slice(0, 7);
    const key = this.monthKey(customerId, month);
    const existing = this.records.get(key);

    const updated: UsageRecord = {
      customerId,
      month,
      requestCount: (existing?.requestCount ?? 0) + 1,
      tokensRouted: (existing?.tokensRouted ?? 0) + tokens,
    };
    this.records.set(key, updated);
    return updated;
  }

  async getMonthly(customerId: string, month?: string): Promise<UsageRecord> {
    const m = month ?? new Date().toISOString().slice(0, 7);
    const key = this.monthKey(customerId, m);
    return this.records.get(key) ?? { customerId, month: m, requestCount: 0, tokensRouted: 0 };
  }

  async checkLimit(customerId: string, tier: Tier): Promise<boolean> {
    const { TIERS } = await import('./types.js');
    const limit = TIERS[tier].requestLimitMonthly;
    if (limit === Infinity) return true;
    const usage = await this.getMonthly(customerId);
    return usage.requestCount < limit;
  }

  async resetMonth(customerId: string, month: string): Promise<void> {
    const key = this.monthKey(customerId, month);
    this.records.delete(key);
  }
}
