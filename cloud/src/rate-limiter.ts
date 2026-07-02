// ── Rate limiting (sliding window via Redis or in-memory) ───────────

import type { Tier } from './types.js';
import { TIERS } from './types.js';

export interface RateLimiter {
  check(customerId: string, tier: Tier): Promise<{ allowed: boolean; remaining: number; resetMs: number }>;
}

// ── In-memory sliding window ────────────────────────────────────────

interface RateBucket {
  timestamps: number[];
}

export class MemoryRateLimiter implements RateLimiter {
  private buckets: Map<string, RateBucket> = new Map();
  private windowMs = 60_000; // 1 minute

  async check(
    customerId: string,
    tier: Tier,
  ): Promise<{ allowed: boolean; remaining: number; resetMs: number }> {
    const limit = TIERS[tier].rateLimitPerMin;
    if (limit === Infinity) {
      return { allowed: true, remaining: Infinity, resetMs: 0 };
    }

    const now = Date.now();
    const key = `${customerId}:${Math.floor(now / this.windowMs)}`;
    const bucket = this.buckets.get(key) ?? { timestamps: [] };

    // Prune old timestamps
    bucket.timestamps = bucket.timestamps.filter((t) => now - t < this.windowMs);

    if (bucket.timestamps.length >= limit) {
      const oldest = bucket.timestamps[0] ?? now;
      const resetMs = this.windowMs - (now - oldest);
      this.buckets.set(key, bucket);
      return { allowed: false, remaining: 0, resetMs: Math.max(resetMs, 0) };
    }

    bucket.timestamps.push(now);
    this.buckets.set(key, bucket);

    // Periodic cleanup
    if (this.buckets.size > 10_000) {
      for (const [k] of this.buckets) {
        if (now - parseInt(k.split(':')[1], 10) * this.windowMs > this.windowMs * 2) {
          this.buckets.delete(k);
        }
      }
    }

    return {
      allowed: true,
      remaining: limit - bucket.timestamps.length,
      resetMs: this.windowMs,
    };
  }
}

// ── Redis-backed rate limiter ───────────────────────────────────────

import type Redis from 'ioredis';

export class RedisRateLimiter implements RateLimiter {
  private redis: Redis;
  private windowMs = 60_000;

  constructor(redis: Redis) {
    this.redis = redis;
  }

  async check(
    customerId: string,
    tier: Tier,
  ): Promise<{ allowed: boolean; remaining: number; resetMs: number }> {
    const limit = TIERS[tier].rateLimitPerMin;
    if (limit === Infinity) {
      return { allowed: true, remaining: Infinity, resetMs: 0 };
    }

    const now = Date.now();
    const key = `ratelimit:${customerId}`;
    const windowStart = now - this.windowMs;

    // Sliding window via sorted set
    const pipe = this.redis.multi();
    pipe.zremrangebyscore(key, 0, windowStart);
    pipe.zadd(key, now, `${now}`);
    pipe.zcard(key);
    pipe.pexpire(key, this.windowMs);

    const results = await pipe.exec();
    if (!results) return { allowed: true, remaining: limit, resetMs: this.windowMs };

    const count = results[2]?.[1] as number;
    if (count > limit) {
      // Remove the entry we just added since we're denying
      await this.redis.zrem(key, `${now}`);
      const earliest = await this.redis.zrange(key, 0, 0, 'WITHSCORES');
      const earliestScore = earliest[1] ? parseFloat(earliest[1]) : now;
      const resetMs = this.windowMs - (now - earliestScore);
      return { allowed: false, remaining: 0, resetMs: Math.max(resetMs, 0) };
    }

    return {
      allowed: true,
      remaining: limit - count,
      resetMs: this.windowMs,
    };
  }
}
