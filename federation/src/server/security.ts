/**
 * Security — API key auth, cross-hub allowlists, rate limiting.
 *
 * Config via ManifoldServerConfig.security:
 * {
 *   apiKey: "..." | null,           // REST API key (null = no auth)
 *   allowedTargets: {               // Which agents remote hubs can target
 *     "bobiverse": ["solar-detect"],
 *     "*": ["*"]                    // default: allow all
 *   },
 *   rateLimitPerHub: 100,           // Max tasks per hub per minute
 *   maxConcurrentPerRunner: 5,      // Max concurrent tasks per runner
 * }
 */

import type { Request, Response, NextFunction } from 'express'

// ── Types ────────────────────────────────────────────────────────────────────

export interface SecurityConfig {
  /** API key for REST endpoints. null/undefined = no auth required. */
  apiKey?: string | null

  /**
   * Cross-hub task allowlist.
   * Key = hub name, value = array of allowed agent targets (or ["*"] for all).
   * Use "*" as key for default policy.
   */
  allowedTargets?: Record<string, string[]>

  /** Max task requests per hub per minute. Default: 60. */
  rateLimitPerHub?: number

  /** Max concurrent tasks per runner. Default: 5. */
  maxConcurrentPerRunner?: number
}

// ── Auth Middleware ───────────────────────────────────────────────────────────

export function createAuthMiddleware(config: SecurityConfig) {
  const apiKey = config.apiKey

  if (!apiKey) {
    // No auth — pass through
    return (_req: Request, _res: Response, next: NextFunction) => next()
  }

  return (req: Request, res: Response, next: NextFunction) => {
    // Check Authorization header or api_key query param
    const headerKey = req.headers['authorization']?.replace('Bearer ', '')
    const queryKey = req.query['api_key'] as string | undefined
    const provided = headerKey || queryKey

    if (!provided || provided !== apiKey) {
      res.status(401).json({ error: 'Unauthorized — invalid or missing API key' })
      return
    }

    next()
  }
}

// ── Cross-hub Allowlist ──────────────────────────────────────────────────────

export class TaskAllowlist {
  private readonly rules: Map<string, Set<string>>
  private readonly defaultRule: Set<string>

  constructor(config: Record<string, string[]> = {}) {
    this.rules = new Map()
    let defaultRule: string[] = ['*'] // default: allow all

    for (const [hub, targets] of Object.entries(config)) {
      if (hub === '*') {
        defaultRule = targets
      } else {
        this.rules.set(hub, new Set(targets))
      }
    }

    this.defaultRule = new Set(defaultRule)
  }

  /** Check if a hub is allowed to target a specific agent */
  isAllowed(sourceHub: string, targetAgent: string): boolean {
    const rules = this.rules.get(sourceHub) ?? this.defaultRule

    // Wildcard allows everything
    if (rules.has('*')) return true

    // Check exact match
    if (rules.has(targetAgent)) return true

    // Check "name@hub" format
    const [name, hub] = targetAgent.includes('@')
      ? targetAgent.split('@')
      : [targetAgent, undefined]

    if (hub && rules.has(`${name}@*`)) return true
    if (rules.has(name)) return true

    return false
  }
}

// ── Rate Limiter ─────────────────────────────────────────────────────────────

export class RateLimiter {
  private readonly limit: number
  private readonly windowMs: number
  private readonly counts = new Map<string, { count: number; resetAt: number }>()

  constructor(limit: number = 60, windowMs: number = 60_000) {
    this.limit = limit
    this.windowMs = windowMs
  }

  /** Check and increment. Returns true if allowed. */
  check(key: string): boolean {
    const now = Date.now()
    let entry = this.counts.get(key)

    if (!entry || now >= entry.resetAt) {
      entry = { count: 0, resetAt: now + this.windowMs }
      this.counts.set(key, entry)
    }

    entry.count++
    return entry.count <= this.limit
  }

  /** Get remaining quota for a key */
  remaining(key: string): number {
    const entry = this.counts.get(key)
    if (!entry || Date.now() >= entry.resetAt) return this.limit
    return Math.max(0, this.limit - entry.count)
  }

  /** Clean expired entries */
  clean(): void {
    const now = Date.now()
    for (const [key, entry] of this.counts) {
      if (now >= entry.resetAt) this.counts.delete(key)
    }
  }
}
