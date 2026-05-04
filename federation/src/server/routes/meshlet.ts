/**
 * meshlet.ts — REST routes for ephemeral meshlet workshop.
 *
 * Endpoints:
 *   POST   /api/meshlet                         — Create meshlet
 *   GET    /api/meshlet/:id                     — Status
 *   DELETE /api/meshlet/:id                     — Destroy
 *   POST   /api/meshlet/:id/void/open           — Open a void
 *   GET    /api/meshlet/:id/void/query          — Query voids
 *   POST   /api/meshlet/:id/void/:void/pressure — Update pressure
 *   POST   /api/meshlet/:id/void/:void/name     — Name (graduate) a void
 *   POST   /api/meshlet/:id/agent/register      — Register agent
 *   GET    /api/meshlet/:id/agent/list           — List agents
 *   POST   /api/meshlet/:id/ssj2/scan            — Run SSJ2 reach scan
 *   GET    /api/meshlet/:id/beam/status           — BEAM status
 *   GET    /nexal/meshlet                        — Workshop UI
 */
import { type Request, type Response, type Router } from 'express'
import { readFileSync } from 'fs'
import { join, dirname } from 'path'
import { fileURLToPath } from 'url'
import { MeshletManager } from '../meshlet-manager.js'

export interface MeshletRouterDeps {
  meshletManager: MeshletManager
}

/** Coerce Express param (string | string[]) to string. */
function p(val: string | string[] | undefined): string {
  if (Array.isArray(val)) return val[0]
  return val ?? ''
}

export function buildMeshletRouter(router: Router, deps: MeshletRouterDeps): void {
  const mgr = deps.meshletManager

  // Workshop UI
  router.get('/nexal/meshlet', (_req: Request, res: Response) => {
    try {
      const __filename = fileURLToPath(import.meta.url)
      const __dirname = dirname(__filename)
      const filePath = join(__dirname, '../../../public/nexal/meshlet.html')
      const html = readFileSync(filePath, 'utf-8')
      res.setHeader('Content-Type', 'text/html; charset=utf-8')
      res.send(html)
    } catch (error) {
      console.error(`[meshlet] Failed to serve workshop UI: ${error}`)
      res.status(500).json({ error: 'Failed to load meshlet workshop' })
    }
  })

  // Create meshlet
  router.post('/api/meshlet', (req: Request, res: Response) => {
    try {
      const owner = req.headers['x-meshlet-owner'] as string || 'anonymous'
      const state = mgr.create(owner)
      res.status(201).json({
        id: state.id,
        mode: state.mode,
        status: state.status,
        expiresAt: state.expiresAt,
        wsUrl: `/ws/meshlet/${state.id}`,
      })
    } catch (err: any) {
      res.status(429).json({ error: err.message })
    }
  })

  // Get status
  router.get('/api/meshlet/:id', (req: Request, res: Response) => {
    const state = mgr.get(p(req.params.id))
    if (!state) return res.status(404).json({ error: 'Meshlet not found' })
    res.json({
      id: state.id,
      mode: state.mode,
      status: state.status,
      createdAt: state.createdAt,
      expiresAt: state.expiresAt,
      voidCount: state.voids.size,
      agentCount: state.agents.length,
      processCount: state.processCount,
      memoryMb: state.memoryMb,
      uptimeSec: state.uptimeSec,
    })
  })

  // Destroy
  router.delete('/api/meshlet/:id', (req: Request, res: Response) => {
    const ok = mgr.destroy(p(req.params.id))
    if (!ok) return res.status(404).json({ error: 'Meshlet not found' })
    res.json({ destroyed: true })
  })

  // ── Void Operations ──────────────────────────────────────────────────────────

  router.post('/api/meshlet/:id/void/open', (req: Request, res: Response) => {
    try {
      const { term, implied_by = [], pressure = 0.0 } = req.body
      if (!term) return res.status(400).json({ error: 'term is required' })
      const v = mgr.openVoid(p(req.params.id), term, implied_by, pressure)
      res.status(201).json(v)
    } catch (err: any) {
      res.status(400).json({ error: err.message })
    }
  })

  router.get('/api/meshlet/:id/void/query', (req: Request, res: Response) => {
    try {
      const voids = mgr.queryVoids(p(req.params.id))
      res.json(voids)
    } catch (err: any) {
      res.status(400).json({ error: err.message })
    }
  })

  router.post('/api/meshlet/:id/void/:void/pressure', (req: Request, res: Response) => {
    try {
      const { delta } = req.body
      if (typeof delta !== 'number') return res.status(400).json({ error: 'delta (number) is required' })
      const v = mgr.updatePressure(p(req.params.id), p(req.params['void']), delta)
      res.json(v)
    } catch (err: any) {
      res.status(400).json({ error: err.message })
    }
  })

  router.post('/api/meshlet/:id/void/:void/name', (req: Request, res: Response) => {
    try {
      const { agent } = req.body
      if (!agent) return res.status(400).json({ error: 'agent name is required' })
      const v = mgr.nameVoid(p(req.params.id), p(req.params['void']), agent)
      res.json(v)
    } catch (err: any) {
      res.status(400).json({ error: err.message })
    }
  })

  // ── Agent Operations ─────────────────────────────────────────────────────────

  router.post('/api/meshlet/:id/agent/register', (req: Request, res: Response) => {
    try {
      const { name, capabilities = [], seams = [], config = {} } = req.body
      if (!name) return res.status(400).json({ error: 'name is required' })
      mgr.registerAgent(p(req.params.id), { name, capabilities, seams, config })
      res.status(201).json({ registered: true, name })
    } catch (err: any) {
      res.status(400).json({ error: err.message })
    }
  })

  router.get('/api/meshlet/:id/agent/list', (req: Request, res: Response) => {
    try {
      const agents = mgr.getAgents(p(req.params.id))
      res.json(agents)
    } catch (err: any) {
      res.status(400).json({ error: err.message })
    }
  })

  // ── SSJ2 & BEAM ──────────────────────────────────────────────────────────────

  router.post('/api/meshlet/:id/ssj2/scan', (req: Request, res: Response) => {
    try {
      const result = mgr.reachScan(p(req.params.id))
      res.json(result)
    } catch (err: any) {
      res.status(400).json({ error: err.message })
    }
  })

  router.get('/api/meshlet/:id/beam/status', (req: Request, res: Response) => {
    try {
      const status = mgr.beamStatus(p(req.params.id))
      res.json(status)
    } catch (err: any) {
      res.status(400).json({ error: err.message })
    }
  })
}
