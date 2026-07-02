// ── API Gateway — the commercial layer over federation ──────────────

import express, { type Request, type Response, type NextFunction } from 'express';
import { v4 as uuid } from 'uuid';
import type { ApiResponse, Customer } from './types.js';
import { TIERS } from './types.js';
import { MemoryCustomerStore, type CustomerStore } from './customers.js';
import {
  MemoryUsageStore,
  RedisUsageStore,
  type UsageStore,
} from './usage.js';
import { MemoryRateLimiter, RedisRateLimiter, type RateLimiter as IRateLimiter } from './rate-limiter.js';
import { BillingService } from './billing.js';
import { ModelRouter } from './router.js';
import { HubManager } from './hub-manager.js';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import fs from 'node:fs';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// ── Paths that don't require auth ───────────────────────────────────

const PUBLIC_PATHS = new Set([
  '/',
  '/health',
  '/v1/register',
  '/webhook/stripe',
  '/pricing',
  '/docs',
]);

// ── Federation proxy endpoints (proxied under /v1/) ─────────────────

const FEDERATION_ENDPOINTS: Record<string, Method> = {
  'GET /status': 'GET',
  'GET /peers': 'GET',
  'GET /agents': 'GET',
  'GET /capabilities': 'GET',
  'GET /mesh': 'GET',
  'GET /metrics': 'GET',
  'POST /agents/register': 'POST',
  'POST /task': 'POST',
  'POST /route': 'POST',
  'POST /query': 'POST',
  'GET /task/': 'GET', // :id
  'GET /tasks': 'GET',
  'GET /agents/': 'GET', // :name
  // Phase 2
  'POST /attestation/challenge': 'POST',
  'POST /attestation/proof': 'POST',
  'POST /attestation/attest': 'POST',
  'GET /attestation/status/': 'GET',
  'POST /registration/challenge': 'POST',
  'POST /registration/verify': 'POST',
  // Phase 3
  'GET /detections': 'GET',
  'GET /detections/stats': 'GET',
  'GET /detections/': 'GET', // :id
  'GET /trust': 'GET',
  'GET /gossip': 'GET',
  'POST /detection/claim': 'POST',
};

type Method = 'GET' | 'POST' | 'PUT' | 'DELETE';

export class CloudGateway {
  private app: express.Application;
  private port: number;
  private federationApiUrl: string;
  private customerStore: CustomerStore;
  private usageStore!: UsageStore;
  private rateLimiter!: IRateLimiter;
  private billing: BillingService;
  private router: ModelRouter;
  private hubManager: HubManager;
  private server: ReturnType<express.Application['listen']> | null = null;

  constructor(config: {
    port: number;
    federationApiUrl: string;
    hubName: string;
    customerStore?: CustomerStore;
    usageStore?: UsageStore;
    rateLimiter?: IRateLimiter;
    stripeSecretKey?: string;
    stripeWebhookSecret?: string;
    openaiKey?: string;
    anthropicKey?: string;
    googleKey?: string;
    localModelUrl?: string;
  }) {
    this.port = config.port;
    this.federationApiUrl = config.federationApiUrl;
    this.app = express();

    // Stores — use provided or default to memory
    this.customerStore = config.customerStore ?? new MemoryCustomerStore();

    // Redis-backed stores if Redis URL is available
    const redisUrl = process.env['REDIS_URL'];
    if (redisUrl && !config.usageStore) {
      // Lazy import ioredis
      import('ioredis').then(({ default: Redis }) => {
        const redis = new Redis(redisUrl);
        this.usageStore = new RedisUsageStore(redisUrl);
        this.rateLimiter = config.rateLimiter ?? new RedisRateLimiter(redis);
        console.log('[gateway] Using Redis for usage tracking and rate limiting');
      }).catch(() => {
        console.warn('[gateway] Redis unavailable — falling back to in-memory');
        this.usageStore = config.usageStore ?? new MemoryUsageStore();
        this.rateLimiter = config.rateLimiter ?? new MemoryRateLimiter();
      });
    } else {
      this.usageStore = config.usageStore ?? new MemoryUsageStore();
      this.rateLimiter = config.rateLimiter ?? new MemoryRateLimiter();
    }

    this.billing = new BillingService({
      customerStore: this.customerStore,
      usageStore: this.usageStore,
      stripeSecretKey: config.stripeSecretKey,
      webhookSecret: config.stripeWebhookSecret,
    });

    this.router = new ModelRouter({
      openaiKey: config.openaiKey,
      anthropicKey: config.anthropicKey,
      googleKey: config.googleKey,
      localModelUrl: config.localModelUrl,
    });

    this.hubManager = new HubManager({
      federationApiUrl: config.federationApiUrl,
      hubName: config.hubName,
    });

    this._setupMiddleware();
    this._setupRoutes();
  }

  // ── Middleware ────────────────────────────────────────────────────

  private _setupMiddleware(): void {
    // JSON parsing (higher limit for task payloads)
    this.app.use(express.json({ limit: '10mb' }));

    // CORS
    this.app.use((_req: Request, res: Response, next: NextFunction) => {
      res.setHeader('Access-Control-Allow-Origin', '*');
      res.setHeader('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS');
      res.setHeader('Access-Control-Allow-Headers', 'Content-Type, Authorization, X-API-Key');
      if (_req.method === 'OPTIONS') {
        res.sendStatus(204);
        return;
      }
      next();
    });

    // Request ID injection
    this.app.use((req: Request, _res: Response, next: NextFunction) => {
      req.requestId = (req.headers['x-request-id'] as string) ?? uuid();
      _res.setHeader('X-Request-Id', req.requestId);
      next();
    });

    // Request logging
    this.app.use((req: Request, _res: Response, next: NextFunction) => {
      const start = Date.now();
      _res.on('finish', () => {
        const ms = Date.now() - start;
        console.log(`[gateway] ${req.method} ${req.path} → ${_res.statusCode} (${ms}ms)`);
      });
      next();
    });
  }

  // ── Auth middleware ───────────────────────────────────────────────

  private _authMiddleware = async (req: Request, res: Response, next: NextFunction): Promise<void> => {
    // Skip auth for public paths
    if (PUBLIC_PATHS.has(req.path) || req.path.startsWith('/public/') || req.path.match(/\.(html|css|js|png|svg|ico)$/)) {
      next();
      return;
    }

    // API key can come from Authorization: Bearer or X-API-Key header
    const authHeader = req.headers['authorization'] as string | undefined;
    const xApiKey = req.headers['x-api-key'] as string | undefined;

    let apiKey: string | undefined;
    if (authHeader?.startsWith('Bearer ')) {
      apiKey = authHeader.slice(7).trim();
    } else if (xApiKey) {
      apiKey = xApiKey.trim();
    }

    if (!apiKey) {
      res.status(401).json({
        success: false,
        error: 'Missing API key. Provide via Authorization: Bearer <key> or X-API-Key header.',
      } satisfies ApiResponse<never>);
      return;
    }

    // Validate key format
    if (!apiKey.startsWith('mk_live_') && !apiKey.startsWith('mk_test_')) {
      res.status(401).json({
        success: false,
        error: 'Invalid API key format. Keys start with mk_live_ or mk_test_.',
      } satisfies ApiResponse<never>);
      return;
    }

    const customer = await this.customerStore.getByApiKey(apiKey);
    if (!customer) {
      res.status(401).json({
        success: false,
        error: 'Invalid or revoked API key.',
      } satisfies ApiResponse<never>);
      return;
    }

    // Attach customer to request
    req.customer = customer;

    // Rate limiting
    const rateResult = await this.rateLimiter.check(customer.id, customer.tier);
    if (!rateResult.allowed) {
      res.setHeader('X-RateLimit-Limit', String(TIERS[customer.tier].rateLimitPerMin));
      res.setHeader('X-RateLimit-Remaining', '0');
      res.setHeader('X-RateLimit-Reset', String(Date.now() + rateResult.resetMs));
      res.setHeader('Retry-After', String(Math.ceil(rateResult.resetMs / 1000)));

      res.status(429).json({
        success: false,
        error: 'Rate limit exceeded. Upgrade your plan for higher limits.',
        requestId: req.requestId,
      } satisfies ApiResponse<never>);
      return;
    }

    // Usage limit check (monthly)
    const withinLimit = await this.usageStore.checkLimit(customer.id, customer.tier);
    if (!withinLimit) {
      res.status(429).json({
        success: false,
        error: `Monthly request limit reached for ${customer.tier} tier. Upgrade at /v1/upgrade.`,
        requestId: req.requestId,
      } satisfies ApiResponse<never>);
      return;
    }

    // Set rate limit headers
    res.setHeader('X-RateLimit-Limit', String(TIERS[customer.tier].rateLimitPerMin));
    res.setHeader('X-RateLimit-Remaining', String(rateResult.remaining));

    next();
  };

  // ── Usage tracking middleware ─────────────────────────────────────

  private _usageMiddleware = async (req: Request, _res: Response, next: NextFunction): Promise<void> => {
    if (req.customer) {
      // Estimate tokens from request body (rough: chars / 4)
      const body = JSON.stringify(req.body ?? {});
      const estimatedTokens = Math.ceil(body.length / 4);
      this.usageStore.increment(req.customer.id, estimatedTokens).catch((err) => {
        console.error('[gateway] Usage tracking error:', err);
      });
    }
    next();
  };

  // ── Federation proxy ──────────────────────────────────────────────

  private async _proxyToFederation(
    method: Method,
    federationPath: string,
    body: unknown,
    res: Response,
  ): Promise<void> {
    try {
      const url = `${this.federationApiUrl}${federationPath}`;
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 30_000);

      const fetchOpts: RequestInit = {
        method,
        headers: { 'Content-Type': 'application/json' },
        signal: controller.signal,
      };
      if (method !== 'GET' && body) {
        fetchOpts.body = JSON.stringify(body);
      }

      const response = await fetch(url, fetchOpts);
      clearTimeout(timeout);

      const data = await response.json().catch(() => ({}));

      if (!response.ok) {
        res.status(response.status).json({
          success: false,
          error: `Federation error: ${(data as { error?: string }).error ?? response.statusText}`,
        } satisfies ApiResponse<never>);
        return;
      }

      res.json({
        success: true,
        data,
      } satisfies ApiResponse<unknown>);
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Unknown error';
      if (err instanceof Error && err.name === 'AbortError') {
        res.status(504).json({
          success: false,
          error: 'Federation hub timeout (30s)',
        } satisfies ApiResponse<never>);
      } else {
        res.status(502).json({
          success: false,
          error: `Cannot reach federation hub: ${msg}`,
        } satisfies ApiResponse<never>);
      }
    }
  }

  // ── Routes ────────────────────────────────────────────────────────

  private _setupRoutes(): void {
    // ── Static landing page ──────────────────────────────────────
    const publicDir = path.resolve(__dirname, '..', 'public');
    this.app.use(express.static(publicDir));

    // ── Health check ─────────────────────────────────────────────
    this.app.get('/health', (_req: Request, res: Response) => {
      res.json({
        status: 'ok',
        service: 'manifold-cloud',
        version: '1.0.0',
        stripeEnabled: this.billing.stripeEnabled,
        hubs: this.hubManager.listHubs().length,
        models: this.router.listModels().length,
        timestamp: Date.now(),
      });
    });

    // ── Registration (no auth) ───────────────────────────────────
    this.app.post('/v1/register', (req, res, next) => this.billing.registerCustomer(req, res, next));

    // ── Stripe webhook (raw body — registered before json parsing in prod) ──
    this.app.post('/webhook/stripe', express.raw({ type: 'application/json' }), (req, res) =>
      this.billing.handleWebhook(req, res),
    );

    // ── Apply auth to everything below ──────────────────────────
    this.app.use(this._authMiddleware);

    // ── Usage tracking middleware (after auth, before routes) ───
    this.app.use(this._usageMiddleware);

    // ── Account & billing ───────────────────────────────────────
    this.app.get('/v1/usage', (req, res, next) => this.billing.getUsage(req, res, next));
    this.app.post('/v1/upgrade', (req, res, next) => this.billing.upgrade(req, res, next));

    // ── Model router endpoints ──────────────────────────────────
    this.app.get('/v1/models', (req: Request, res: Response) => {
      const provider = req.query['provider'] as string | undefined;
      res.json({
        success: true,
        data: {
          models: this.router.listModels(provider),
          health: this.router.getHealthStatus(),
        },
      } satisfies ApiResponse<unknown>);
    });

    this.app.post('/v1/route', (req: Request, res: Response) => {
      const body = req.body as { prompt?: string; capabilities?: string[]; maxTokens?: number; preferCheapest?: boolean };
      if (!body.prompt) {
        res.status(400).json({ success: false, error: 'prompt required' });
        return;
      }
      const decision = this.router.route({
        prompt: body.prompt,
        capabilities: body.capabilities as never[],
        maxTokens: body.maxTokens,
        preferCheapest: body.preferCheapest,
      });
      res.json({ success: true, data: decision } satisfies ApiResponse<unknown>);
    });

    // ── Hub management ──────────────────────────────────────────
    this.app.get('/v1/hubs', (_req: Request, res: Response) => {
      res.json({
        success: true,
        data: {
          hubs: this.hubManager.listHubs(),
          primary: this.hubManager.getPrimaryHub(),
        },
      } satisfies ApiResponse<unknown>);
    });

    this.app.post('/v1/hubs/register', (req: Request, res: Response) => {
      const { url, name } = req.body as { url: string; name?: string };
      if (!url) {
        res.status(400).json({ success: false, error: 'url required' });
        return;
      }
      const hub = this.hubManager.registerHub(url, name);
      res.status(201).json({ success: true, data: hub } satisfies ApiResponse<unknown>);
    });

    this.app.delete('/v1/hubs/:id', (req: Request, res: Response) => {
      this.hubManager.deregisterHub(String(req.params['id']));
      res.json({ success: true, data: { deregistered: true } } satisfies ApiResponse<unknown>);
    });

    this.app.post('/v1/hubs/scale', async (_req: Request, res: Response) => {
      const evaluation = await this.hubManager.evaluateScaling();
      res.json({ success: true, data: evaluation } satisfies ApiResponse<unknown>);
    });

    // ── Federation proxy endpoints (under /v1/) ─────────────────
    // Status
    this.app.get('/v1/status', async (_req, res) => this._proxyToFederation('GET', '/status', null, res));
    this.app.get('/v1/peers', async (_req, res) => this._proxyToFederation('GET', '/peers', null, res));
    this.app.get('/v1/agents', async (_req, res) => this._proxyToFederation('GET', '/agents', null, res));
    this.app.get('/v1/capabilities', async (_req, res) => this._proxyToFederation('GET', '/capabilities', null, res));
    this.app.get('/v1/mesh', async (_req, res) => this._proxyToFederation('GET', '/mesh', null, res));
    this.app.get('/v1/metrics', async (_req, res) => this._proxyToFederation('GET', '/metrics', null, res));
    this.app.get('/v1/tasks', async (_req, res) => this._proxyToFederation('GET', '/tasks', null, res));
    this.app.get('/v1/task/:id', async (req, res) => this._proxyToFederation('GET', `/task/${req.params['id']}`, null, res));
    this.app.get('/v1/agents/:name', async (req, res) => this._proxyToFederation('GET', `/agents/${req.params['name']}`, null, res));

    // POST endpoints
    this.app.post('/v1/agents/register', async (req, res) => this._proxyToFederation('POST', '/agents/register', req.body, res));
    this.app.post('/v1/task', async (req, res) => this._proxyToFederation('POST', '/task', req.body, res));
    this.app.post('/v1/query', async (req, res) => this._proxyToFederation('POST', '/query', req.body, res));

    // Phase 2: Attestation
    this.app.post('/v1/attestation/challenge', async (req, res) => this._proxyToFederation('POST', '/attestation/challenge', req.body, res));
    this.app.post('/v1/attestation/proof', async (req, res) => this._proxyToFederation('POST', '/attestation/proof', req.body, res));
    this.app.post('/v1/attestation/attest', async (req, res) => this._proxyToFederation('POST', '/attestation/attest', req.body, res));
    this.app.get('/v1/attestation/status/:agentId/:capability', async (req, res) =>
      this._proxyToFederation('GET', `/attestation/status/${req.params['agentId']}/${req.params['capability']}`, null, res),
    );
    this.app.post('/v1/registration/challenge', async (req, res) => this._proxyToFederation('POST', '/registration/challenge', req.body, res));
    this.app.post('/v1/registration/verify', async (req, res) => this._proxyToFederation('POST', '/registration/verify', req.body, res));

    // Phase 3: Detection
    this.app.get('/v1/detections', async (_req, res) => this._proxyToFederation('GET', '/detections', null, res));
    this.app.get('/v1/detections/stats', async (_req, res) => this._proxyToFederation('GET', '/detections/stats', null, res));
    this.app.get('/v1/detections/:id', async (req, res) => this._proxyToFederation('GET', `/detections/${req.params['id']}`, null, res));
    this.app.get('/v1/trust', async (_req, res) => this._proxyToFederation('GET', '/trust', null, res));
    this.app.get('/v1/gossip', async (_req, res) => this._proxyToFederation('GET', '/gossip', null, res));
    this.app.post('/v1/detection/claim', async (req, res) => this._proxyToFederation('POST', '/detection/claim', req.body, res));

    // ── 404 handler ─────────────────────────────────────────────
    this.app.use((_req: Request, res: Response) => {
      res.status(404).json({
        success: false,
        error: 'Not found. See /docs for API documentation.',
      } satisfies ApiResponse<never>);
    });

    // ── Error handler ───────────────────────────────────────────
    this.app.use((err: Error, _req: Request, res: Response, _next: NextFunction) => {
      console.error('[gateway] Unhandled error:', err);
      res.status(500).json({
        success: false,
        error: 'Internal server error',
      } satisfies ApiResponse<never>);
    });
  }

  // ── Lifecycle ─────────────────────────────────────────────────────

  async start(): Promise<void> {
    // Register the primary federation hub
    this.hubManager.registerHub(this.federationApiUrl, 'primary');

    // Start health monitoring
    this.hubManager.startHealthMonitoring();

    return new Promise((resolve) => {
      this.server = this.app.listen(this.port, () => {
        console.log(`\n╔══════════════════════════════════════════════════╗`);
        console.log(`║  🚀 Manifold Cloud — Gateway listening on :${this.port}  ║`);
        console.log(`║  Federation: ${this.federationApiUrl.padEnd(34)}║`);
        console.log(`║  Stripe: ${this.billing.stripeEnabled ? 'active' : 'mock mode'}${' '.repeat(37 - (this.billing.stripeEnabled ? 6 : 10))}║`);
        console.log(`║  Landing:  http://localhost:${this.port}${' '.repeat(Math.max(0, 22 - String(this.port).length))}║`);
        console.log(`╚══════════════════════════════════════════════════╝\n`);
        resolve();
      });
    });
  }

  async stop(): Promise<void> {
    this.hubManager.stopHealthMonitoring();
    return new Promise((resolve) => {
      if (!this.server) return resolve();
      this.server.close(() => resolve());
    });
  }

  get app_(): express.Application {
    return this.app;
  }
}

// ── Request augmentation ────────────────────────────────────────────

declare module 'express-serve-static-core' {
  interface Request {
    requestId: string;
    customer?: Customer;
  }
}
