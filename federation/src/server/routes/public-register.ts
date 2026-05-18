/**
 * public-register.ts — Public agent self-registration (invite-token gated).
 *
 * Endpoints:
 *   POST /public/agents/register  — register an agent with an invite token
 *
 * This is the "Bring Your Agent" flow for the onboarding pages.
 * Requires a valid invite token. Returns agent credentials.
 */
import { Router, type Request, type Response } from 'express'
import crypto from 'crypto'

export interface PublicAgentRegistration {
  agentId: string
  name: string
  hub: string
  token: string
  capabilities: string[]
  registeredAt: number
}

// In-memory store of publicly-registered agents
const registrations = new Map<string, PublicAgentRegistration>()

export interface PublicRegisterDeps {
  hub: string
  log?: (msg: string) => void
  /** Validate invite token — uses the invites module */
  validateToken: (token: string) => { valid: boolean; reason?: string }
}

export function buildPublicRegisterRouter(deps: PublicRegisterDeps): Router {
  const router = Router()

  router.post('/public/agents/register', (req: Request, res: Response) => {
    const { name, capabilities, inviteToken, type, webhookUrl, description } = req.body as {
      name?: string
      capabilities?: string[]
      inviteToken?: string
      type?: string
      webhookUrl?: string
      description?: string
    }

    // Validate required fields
    if (!name || typeof name !== 'string' || name.trim().length < 2) {
      return res.status(400).json({ error: 'Agent name is required (min 2 characters)' })
    }

    if (!capabilities || !Array.isArray(capabilities) || capabilities.length === 0) {
      return res.status(400).json({ error: 'At least one capability is required' })
    }

    // Validate invite token
    if (!inviteToken) {
      return res.status(400).json({ error: 'Invite token is required for registration' })
    }

    const tokenCheck = deps.validateToken(inviteToken.trim())
    if (!tokenCheck.valid) {
      deps.log?.(`[public-register] Rejected registration for "${name}": invalid token (${tokenCheck.reason || 'not found'})`)
      return res.status(403).json({ error: 'Invalid or expired invite token', reason: tokenCheck.reason })
    }

    // Sanitize name — alphanumeric, dashes, underscores only
    const safeName = name.trim().toLowerCase().replace(/[^a-z0-9\-_]/g, '-')
    const agentId = `${safeName}@${deps.hub}`

    // Check for duplicate
    if (registrations.has(agentId)) {
      return res.status(409).json({ error: 'An agent with this name is already registered' })
    }

    // Generate agent token
    const agentToken = `agent-${crypto.randomBytes(16).toString('hex')}`

    const registration: PublicAgentRegistration = {
      agentId,
      name: safeName,
      hub: deps.hub,
      token: agentToken,
      capabilities: capabilities.map((c: string) => c.trim()).filter(Boolean),
      registeredAt: Date.now(),
    }

    registrations.set(agentId, registration)

    deps.log?.(`[public-register] Agent "${safeName}" registered with ${capabilities.length} capabilities`)

    return res.status(201).json({
      success: true,
      agentId,
      name: safeName,
      hub: deps.hub,
      token: agentToken,
      capabilities: registration.capabilities,
      endpoints: {
        ws: '/ws/local',
        rest: '/agents/register',
        capabilities: `/agents/${safeName}`,
        discover: '/agents',
      },
      message: `Agent "${safeName}" registered on hub "${deps.hub}"`,
      nextSteps: [
        `Connect via WebSocket: wss://nexal.network/ws/local`,
        `Authenticate with your token: ${agentToken.slice(0, 12)}…`,
        `Register capabilities: POST /agents/${safeName}/capabilities`,
        `Discover peers: GET /agents`,
      ],
    })
  })

  // List registered agents (public, limited info)
  router.get('/public/agents', (_req: Request, res: Response) => {
    const agents = Array.from(registrations.values()).map(r => ({
      agentId: r.agentId,
      name: r.name,
      hub: r.hub,
      capabilities: r.capabilities,
      registeredAt: r.registeredAt,
    }))
    return res.json({ agents, count: agents.length })
  })

  return router
}

/** Get all public registrations (for wiring into capIndex) */
export function getPublicRegistrations(): PublicAgentRegistration[] {
  return Array.from(registrations.values())
}
