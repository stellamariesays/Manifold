import express, { type Request, type Response, type Router } from 'express'
import type { CapabilityIndex } from './capability-index.js'
import type { PeerRegistry } from './peer-registry.js'
import type { MeshSync } from './mesh-sync.js'

export interface RestApiOptions {
  hub: string
  port: number
  debug?: boolean
}

export class RestApi {
  private readonly hub: string
  private readonly port: number
  private readonly debug: boolean

  private app = express()
  private server: ReturnType<typeof this.app.listen> | null = null

  private capIndex!: CapabilityIndex
  private peerRegistry!: PeerRegistry
  private meshSync!: MeshSync
  private startTime = Date.now()

  constructor(options: RestApiOptions) {
    this.hub = options.hub
    this.port = options.port
    this.debug = options.debug ?? false
    this._setup()
  }

  start(capIndex: CapabilityIndex, peerRegistry: PeerRegistry, meshSync: MeshSync): Promise<void> {
    this.capIndex = capIndex
    this.peerRegistry = peerRegistry
    this.meshSync = meshSync

    return new Promise((resolve, reject) => {
      this.server = this.app.listen(this.port, () => {
        this.log(`REST API listening on port ${this.port}`)
        resolve()
      })
      this.server.on('error', reject)
    })
  }

  stop(): Promise<void> {
    return new Promise((resolve) => {
      if (!this.server) return resolve()
      this.server.close(() => resolve())
    })
  }

  private _setup(): void {
    this.app.use(express.json())

    // CORS for MRI visualization
    this.app.use((_req, res, next) => {
      res.setHeader('Access-Control-Allow-Origin', '*')
      res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
      res.setHeader('Access-Control-Allow-Headers', 'Content-Type')
      next()
    })

    const router: Router = express.Router()

    router.get('/status', this._status.bind(this))
    router.get('/peers', this._peers.bind(this))
    router.get('/agents', this._agents.bind(this))
    router.get('/agents/:name', this._agent.bind(this))
    router.get('/capabilities', this._capabilities.bind(this))
    router.get('/dark-circles', this._darkCircles.bind(this))
    router.get('/mesh', this._mesh.bind(this))
    router.post('/query', this._query.bind(this))
    router.post('/route', this._route.bind(this))

    this.app.use('/', router)
  }

  // ── Handlers ────────────────────────────────────────────────────────────────

  private _status(_req: Request, res: Response): void {
    const stats = this.capIndex.stats()
    res.json({
      hub: this.hub,
      status: 'ok',
      uptime: Math.floor((Date.now() - this.startTime) / 1000),
      peers: this.peerRegistry.getPeers().length,
      agents: stats.agents,
      capabilities: stats.capabilities,
      darkCircles: stats.darkCircles,
      timestamp: new Date().toISOString(),
    })
  }

  private _peers(_req: Request, res: Response): void {
    res.json({
      hub: this.hub,
      peers: this.peerRegistry.getPeers(),
    })
  }

  private _agents(req: Request, res: Response): void {
    const { hub, capability } = req.query as Record<string, string>
    let agents = this.capIndex.getAllAgents()

    if (hub) agents = agents.filter(a => a.hub === hub)
    if (capability) agents = agents.filter(a => a.capabilities.includes(capability))

    res.json({ hub: this.hub, count: agents.length, agents })
  }

  private _agent(req: Request, res: Response): void {
    const name = String(req.params['name'] ?? '')
    // Support "name@hub" format
    const [agentName, agentHub] = name.includes('@') ? name.split('@') : [name, undefined]

    let agent = agentHub
      ? this.capIndex.getAgent(agentName, agentHub)
      : this.capIndex.getAllAgents().find(a => a.name === agentName)

    if (!agent) {
      res.status(404).json({ error: `Agent not found: ${name}` })
      return
    }

    res.json(agent)
  }

  private _capabilities(_req: Request, res: Response): void {
    const capabilities = this.capIndex.getAllCapabilities()
    const withAgents = capabilities.map(cap => ({
      capability: cap,
      agents: this.capIndex.findByCapability(cap).map(a => `${a.name}@${a.hub}`),
    }))
    res.json({ hub: this.hub, capabilities: withAgents })
  }

  private _darkCircles(_req: Request, res: Response): void {
    const circles = this.capIndex.getDarkCircles()
    res.json({
      hub: this.hub,
      darkCircles: circles.sort((a, b) => b.pressure - a.pressure),
    })
  }

  private _mesh(_req: Request, res: Response): void {
    const stats = this.capIndex.stats()
    res.json({
      hub: this.hub,
      agents: this.capIndex.getAllAgents(),
      peers: this.peerRegistry.getPeers(),
      darkCircles: this.capIndex.getDarkCircles(),
      capabilities: this.capIndex.getAllCapabilities(),
      stats: {
        agents: stats.agents,
        capabilities: stats.capabilities,
        darkCircles: stats.darkCircles,
        hubs: Array.from(stats.hubs),
      },
      timestamp: new Date().toISOString(),
    })
  }

  private _query(req: Request, res: Response): void {
    const { capability, minPressure, hub } = req.body as {
      capability?: string
      minPressure?: number
      hub?: string
    }

    if (!capability) {
      res.status(400).json({ error: 'capability is required' })
      return
    }

    let agents = this.capIndex.findByCapability(capability, minPressure)
    if (hub) agents = agents.filter(a => a.hub === hub)

    res.json({
      capability,
      count: agents.length,
      agents,
    })
  }

  private _route(req: Request, res: Response): void {
    // Phase 1: acknowledge route request, return routing info
    const { target, task } = req.body as {
      target?: string
      task?: Record<string, unknown>
    }

    if (!target || !task) {
      res.status(400).json({ error: 'target and task are required' })
      return
    }

    const [agentName, agentHub] = target.includes('@') ? target.split('@') : [target, undefined]
    const agent = agentHub
      ? this.capIndex.getAgent(agentName, agentHub)
      : this.capIndex.getAllAgents().find(a => a.name === agentName)

    if (!agent) {
      res.status(404).json({ error: `Agent not found: ${target}` })
      return
    }

    res.json({
      status: 'routed',
      target: `${agent.name}@${agent.hub}`,
      hub: agent.hub,
      isLocal: agent.isLocal,
      message: 'Route acknowledged (WebSocket routing in Phase 2)',
    })
  }

  private log(msg: string): void {
    if (this.debug) console.log(`[RestApi:${this.hub}] ${msg}`)
  }
}
