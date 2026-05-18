/**
 * invites.ts — Public invite token routes for onboarding.
 *
 * Endpoints:
 *   POST /public/invites/redeem   — redeem an invite token
 *   POST /public/invites/create   — create a new invite token (admin)
 *   GET  /public/invites/:token   — check if a token is valid
 */
import { Router, Request, Response } from 'express';
import crypto from 'crypto';

export interface InviteToken {
  token: string;
  createdBy: string;
  createdAt: number;
  usedAt?: number;
  usedBy?: string;
  hubName?: string;
  maxUses: number;
  uses: number;
  expiresAt?: number;
}

// In-memory invite store — persists for the lifetime of the server process.
// For production, swap this with a database or file-backed store.
const invites = new Map<string, InviteToken>();

// Pre-seed a few tokens for initial onboarding
const seedTokens = ['NEXAL-2026-ALPHA', 'NEXAL-MESH-START', 'MANIFOLD-OPEN'];
seedTokens.forEach((t, i) => {
  invites.set(t, {
    token: t,
    createdBy: 'system',
    createdAt: Date.now(),
    maxUses: 100,
    uses: 0,
    expiresAt: Date.now() + 365 * 24 * 60 * 60 * 1000, // 1 year
  });
});

export function buildInviteRouter(deps: { adminApiKey?: string; hub?: string; log?: (msg: string) => void }): Router {
  const router = Router();

  // Redeem an invite token
  router.post('/public/invites/redeem', (req: Request, res: Response) => {
    const { token, hubName, claimedBy } = req.body || {};

    if (!token || typeof token !== 'string') {
      return res.status(400).json({ error: 'Token is required' });
    }

    const invite = invites.get(token.trim());
    if (!invite) {
      deps.log?.(`[invites] Invalid token attempt: ${token.slice(0, 8)}…`);
      return res.status(404).json({ error: 'Invalid invite token' });
    }

    // Check expiry
    if (invite.expiresAt && Date.now() > invite.expiresAt) {
      return res.status(410).json({ error: 'Token has expired' });
    }

    // Check usage limit
    if (invite.uses >= invite.maxUses) {
      return res.status(410).json({ error: 'Token has reached its usage limit' });
    }

    // Redeem
    invite.uses++;
    invite.usedAt = Date.now();
    invite.usedBy = claimedBy || 'anonymous';
    invite.hubName = hubName || invite.hubName;

    deps.log?.(`[invites] Token ${token.slice(0, 8)}… redeemed by ${invite.usedBy} (uses: ${invite.uses}/${invite.maxUses})`);

    return res.json({
      success: true,
      token: token,
      hubName: invite.hubName || hubName,
      message: 'Welcome to the Manifold Federation! Your hub is being provisioned.',
      nextSteps: [
        'Clone the repo: git clone https://github.com/stellamariesays/Manifold.git',
        'Copy config: cd Manifold/federation && cp config-example.json config.json',
        'Edit config.json with your hub name and settings',
        'Run: npm install && npm start',
        'Your hub will automatically connect to the federation mesh',
      ],
    });
  });

  // Check if a token is valid (GET, no side effects)
  router.get('/public/invites/:token', (req: Request, res: Response) => {
    const token = req.params.token?.trim();
    if (!token) {
      return res.status(400).json({ error: 'Token is required' });
    }

    const invite = invites.get(token);
    if (!invite) {
      return res.status(404).json({ valid: false, error: 'Token not found' });
    }

    if (invite.expiresAt && Date.now() > invite.expiresAt) {
      return res.json({ valid: false, reason: 'expired' });
    }

    if (invite.uses >= invite.maxUses) {
      return res.json({ valid: false, reason: 'max_uses_reached' });
    }

    return res.json({
      valid: true,
      usesRemaining: invite.maxUses - invite.uses,
      createdBy: invite.createdBy === 'system' ? 'system' : undefined,
    });
  });

  // Create a new invite token (admin, requires API key)
  router.post('/public/invites/create', (req: Request, res: Response) => {
    // Simple admin check — in production, use proper auth middleware
    const authHeader = req.headers.authorization;
    if (deps.adminApiKey && authHeader !== `Bearer ${deps.adminApiKey}`) {
      return res.status(403).json({ error: 'Admin access required' });
    }

    const { maxUses = 1, expiresInMs, createdBy = 'admin', hubName } = req.body || {};

    const token = `NEXAL-${crypto.randomBytes(4).toString('hex').toUpperCase()}`;
    const invite: InviteToken = {
      token,
      createdBy,
      createdAt: Date.now(),
      maxUses: typeof maxUses === 'number' ? maxUses : 1,
      uses: 0,
      hubName,
      expiresAt: expiresInMs ? Date.now() + expiresInMs : undefined,
    };

    invites.set(token, invite);
    deps.log?.(`[invites] Created token ${token} (${maxUses} uses, by ${createdBy})`);

    return res.status(201).json({
      token,
      maxUses: invite.maxUses,
      expiresAt: invite.expiresAt,
    });
  });

  // List all tokens (admin)
  router.get('/public/invites', (req: Request, res: Response) => {
    const authHeader = req.headers.authorization;
    if (deps.adminApiKey && authHeader !== `Bearer ${deps.adminApiKey}`) {
      return res.status(403).json({ error: 'Admin access required' });
    }

    const list = Array.from(invites.values()).map(inv => ({
      token: inv.token,
      createdBy: inv.createdBy,
      createdAt: inv.createdAt,
      uses: inv.uses,
      maxUses: inv.maxUses,
      expiresAt: inv.expiresAt,
      usedBy: inv.usedBy,
      hubName: inv.hubName,
    }));

    return res.json({ tokens: list, total: list.length });
  });

  return router;
}
