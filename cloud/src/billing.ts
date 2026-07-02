// ── Billing service — Stripe integration scaffold ──────────────────

import type { Express, Request, Response, NextFunction } from 'express';
import { TIERS, type Tier, type Customer, type ApiResponse } from './types.js';
import type { CustomerStore } from './customers.js';
import type { UsageStore } from './usage.js';

// Conditional Stripe import — works without keys installed
interface StripeLike {
  customers: {
    create(params: { email: string; metadata?: Record<string, string> }): Promise<{ id: string }>;
    retrieve(id: string): Promise<{ deleted?: boolean; email?: string }>;
  };
  checkout: {
    sessions: {
      create(params: {
        mode: 'subscription';
        customer: string;
        line_items: { price: string; quantity: number }[];
        success_url: string;
        cancel_url: string;
        metadata?: Record<string, string>;
      }): Promise<{ url: string }>;
    };
  };
  webhooks: {
    constructEvent(payload: string | Buffer, signature: string, secret: string): StripeEvent;
  };
  subscriptions: {
    retrieve(id: string): Promise<{ status: string; current_period_end: number }>;
  };
}

interface StripeEvent {
  id: string;
  type: string;
  data: { object: Record<string, unknown> };
}

export class BillingService {
  private stripe: StripeLike | null = null;
  private customerStore: CustomerStore;
  private usageStore: UsageStore;
  private webhookSecret: string;
  public stripeEnabled: boolean;

  constructor(opts: {
    customerStore: CustomerStore;
    usageStore: UsageStore;
    stripeSecretKey: string | undefined;
    webhookSecret: string | undefined;
  }) {
    this.customerStore = opts.customerStore;
    this.usageStore = opts.usageStore;
    this.webhookSecret = opts.webhookSecret ?? '';

    if (opts.stripeSecretKey && opts.stripeSecretKey.startsWith('sk_')) {
      // Dynamically import Stripe only when configured
      this.stripeEnabled = true;
      // We'll lazy-load the actual Stripe SDK in _initStripe
      this._initStripe(opts.stripeSecretKey).catch((err) => {
        console.error('[billing] Failed to init Stripe:', err);
        this.stripeEnabled = false;
      });
    } else {
      this.stripeEnabled = false;
      console.log('[billing] Stripe not configured — running in mock mode');
    }
  }

  private async _initStripe(apiKey: string): Promise<void> {
    const mod = await import('stripe');
    const Stripe = mod.default;
    this.stripe = new Stripe(apiKey) as unknown as StripeLike;
  }

  // ── Registration endpoint ─────────────────────────────────────────

  async registerCustomer(req: Request, res: Response, next: NextFunction): Promise<void> {
    try {
      const { email, tier = 'free' as Tier } = req.body as { email: string; tier?: Tier };

      if (!email || !email.includes('@')) {
        res.status(400).json({
          success: false,
          error: 'Valid email required',
        } satisfies ApiResponse<never>);
        return;
      }

      if (!TIERS[tier]) {
        res.status(400).json({
          success: false,
          error: `Invalid tier: ${tier}. Must be free, pro, or enterprise`,
        } satisfies ApiResponse<never>);
        return;
      }

      let stripeCustomerId: string | undefined;

      // Create Stripe customer if Stripe is active and tier is paid
      if (this.stripeEnabled && this.stripe && tier !== 'free') {
        try {
          const customer = await this.stripe.customers.create({
            email,
            metadata: { tier, registeredVia: 'manifold-cloud' },
          });
          stripeCustomerId = customer.id;
        } catch (err) {
          console.error('[billing] Stripe customer creation failed:', err);
          // Continue without Stripe — they can upgrade later
        }
      }

      const customer = await this.customerStore.create(email, tier, stripeCustomerId);

      // If paid tier and Stripe is set up, initiate checkout
      let checkoutUrl: string | undefined;
      if (this.stripeEnabled && this.stripe && tier !== 'free' && stripeCustomerId) {
        try {
          const priceKey = tier === 'pro' ? 'STRIPE_PRICE_PRO' : 'STRIPE_PRICE_ENTERPRISE';
          const priceId = process.env[priceKey] ?? '';
          if (priceId) {
            const session = await this.stripe.checkout.sessions.create({
              mode: 'subscription',
              customer: stripeCustomerId,
              line_items: [{ price: priceId, quantity: 1 }],
              success_url: `${req.protocol}://${req.get('host')}/dashboard?upgraded=1`,
              cancel_url: `${req.protocol}://${req.get('host')}/?canceled=1`,
              metadata: { customerId: customer.id, tier },
            });
            checkoutUrl = session.url;
          }
        } catch (err) {
          console.error('[billing] Checkout session creation failed:', err);
        }
      }

      res.status(201).json({
        success: true,
        data: {
          customerId: customer.id,
          apiKey: customer.apiKey, // plaintext — only returned once
          tier: customer.tier,
          stripeCustomerId: customer.stripeCustomerId,
          checkoutUrl,
          message: this.stripeEnabled
            ? 'Registration successful. Save your API key — it won\'t be shown again.'
            : 'Registration successful (mock mode — no payment required). Save your API key.',
        },
      } satisfies ApiResponse<unknown>);
    } catch (err) {
      next(err);
    }
  }

  // ── Stripe webhook handler ────────────────────────────────────────

  async handleWebhook(req: Request, res: Response): Promise<void> {
    if (!this.stripeEnabled || !this.stripe) {
      res.status(503).json({ error: 'Stripe not configured' });
      return;
    }

    const sig = req.headers['stripe-signature'] as string | undefined;
    if (!sig) {
      res.status(400).json({ error: 'Missing stripe-signature header' });
      return;
    }

    let event: StripeEvent;
    try {
      event = this.stripe.webhooks.constructEvent(req.body, sig, this.webhookSecret);
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Unknown error';
      console.error('[billing] Webhook signature verification failed:', msg);
      res.status(400).json({ error: `Webhook Error: ${msg}` });
      return;
    }

    console.log(`[billing] Stripe webhook: ${event.type}`);

    switch (event.type) {
      case 'checkout.session.completed': {
        const obj = event.data.object as {
          customer?: string;
          metadata?: { customerId?: string; tier?: string };
        };
        const customerId = obj.metadata?.customerId;
        const tier = obj.metadata?.tier as Tier | undefined;
        if (customerId && tier) {
          await this.customerStore.updateTier(customerId, tier);
          console.log(`[billing] Upgraded ${customerId} → ${tier}`);
        }
        break;
      }

      case 'customer.subscription.deleted': {
        const obj = event.data.object as { customer?: string };
        // Downgrade to free on cancellation
        const customers = await this.customerStore.list();
        const match = customers.find((c) => c.stripeCustomerId === obj.customer);
        if (match) {
          await this.customerStore.updateTier(match.id, 'free');
          console.log(`[billing] Downgraded ${match.id} → free (subscription canceled)`);
        }
        break;
      }

      case 'invoice.paid': {
        // Reset usage at start of billing cycle
        const obj = event.data.object as { customer?: string };
        const customers = await this.customerStore.list();
        const match = customers.find((c) => c.stripeCustomerId === obj.customer);
        if (match) {
          const month = new Date().toISOString().slice(0, 7);
          await this.usageStore.resetMonth(match.id, month);
          console.log(`[billing] Reset usage for ${match.id} (new billing cycle)`);
        }
        break;
      }

      default:
        // Unhandled event — log and continue
        break;
    }

    res.json({ received: true });
  }

  // ── Usage endpoint ────────────────────────────────────────────────

  async getUsage(req: Request, res: Response, next: NextFunction): Promise<void> {
    try {
      const customer = req.customer as Customer;
      const usage = await this.usageStore.getMonthly(customer.id);
      const tierConfig = TIERS[customer.tier];

      res.json({
        success: true,
        data: {
          tier: customer.tier,
          monthlyLimit: tierConfig.requestLimitMonthly,
          requestsUsed: usage.requestCount,
          tokensRouted: usage.tokensRouted,
          remaining:
            tierConfig.requestLimitMonthly === Infinity
              ? Infinity
              : Math.max(tierConfig.requestLimitMonthly - usage.requestCount, 0),
          resetDate: new Date(
            Date.UTC(
              new Date().getUTCFullYear(),
              new Date().getUTCMonth() + 1,
              1,
            ),
          ).toISOString(),
        },
      } satisfies ApiResponse<unknown>);
    } catch (err) {
      next(err);
    }
  }

  // ── Upgrade endpoint ──────────────────────────────────────────────

  async upgrade(req: Request, res: Response, next: NextFunction): Promise<void> {
    try {
      const customer = req.customer as Customer;
      const { tier } = req.body as { tier: Tier };

      if (!TIERS[tier]) {
        res.status(400).json({ success: false, error: 'Invalid tier' });
        return;
      }

      if (!this.stripeEnabled || !this.stripe) {
        // Mock mode — just update
        await this.customerStore.updateTier(customer.id, tier);
        res.json({
          success: true,
          data: { tier, message: 'Upgraded (mock mode)' },
        });
        return;
      }

      // Real Stripe flow — create checkout session
      const priceKey = tier === 'pro' ? 'STRIPE_PRICE_PRO' : 'STRIPE_PRICE_ENTERPRISE';
      const priceId = process.env[priceKey] ?? '';

      if (!priceId) {
        res.status(500).json({ success: false, error: 'Price ID not configured' });
        return;
      }

      if (!customer.stripeCustomerId) {
        res.status(400).json({
          success: false,
          error: 'No Stripe customer record. Contact support.',
        });
        return;
      }

      const session = await this.stripe.checkout.sessions.create({
        mode: 'subscription',
        customer: customer.stripeCustomerId,
        line_items: [{ price: priceId, quantity: 1 }],
        success_url: `${req.protocol}://${req.get('host')}/dashboard?upgraded=1`,
        cancel_url: `${req.protocol}://${req.get('host')}/dashboard`,
        metadata: { customerId: customer.id, tier },
      });

      res.json({
        success: true,
        data: { checkoutUrl: session.url },
      });
    } catch (err) {
      next(err);
    }
  }
}

// ── Express type augmentation ───────────────────────────────────────

declare module 'express-serve-static-core' {
  interface Request {
    customer?: Customer;
  }
}
