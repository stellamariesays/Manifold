/**
 * rest-api.ts — RestApi wiring/bootstrap entry point.
 *
 * This class owns lifecycle (start/stop) and wires the focused route
 * modules together.  Business logic lives in the individual router files
 * under routes/.
 */
import express, { type Router } from 'express'
import type { CapabilityIndex } from './capability-index.js'
import type { PeerRegistry } from './peer-registry.js'
import type { MeshSync } from './mesh-sync.js'
import type { TaskRouter } from './task-router.js'
import type { TaskHistory } from './task-history.js'
import type { MetricsCollector } from './metrics.js'
import type { SecurityConfig } from './security.js'
import { createAuthMiddleware } from './security.js'
import type { DetectionCoord } from './detection-coord.js'
import { AttestationEngine } from '../attestation/engine.js'
import { AntiSybilGuard } from '../attestation/anti-sybil.js'

import { registerNexalRoutes } from './routes/nexal.js'
import { buildAgentRouter } from './routes/agents.js'
import { buildTaskRouter } from './routes/tasks.js'
import { buildAttestationRouter } from './routes/attestation.js'
import { buildDetectionRouter } from './routes/detection.js'
import { buildMeshRouter } from './routes/mesh.js'
import { buildTeacupsRouter } from './routes/teacups.js'
import { buildDashboardRouter } from './routes/dashboard.js'

export interface RestApiOptions {
  hub: string
  port: number
  debug?: boolean
  apiKey?: string
}

export class RestApi {
  private readonly hub: string
  private readonly port: number
  private readonly debug: boolean
  private readonly apiKey?: string

  private app = express()
  private server: ReturnType<typeof this.app.listen> | null = null

  private capIndex!: CapabilityIndex
  private peerRegistry!: PeerRegistry
  private meshSync!: MeshSync
  private taskRouterInst!: TaskRouter
  private taskHistory!: TaskHistory
  private metrics!: MetricsCollector
  private detectionCoord!: DetectionCoord
  readonly attestationEngine: AttestationEngine
  readonly antiSybilGuard: AntiSybilGuard
  private startTime = Date.now()

  constructor(options: RestApiOptions) {
    this.hub = options.hub
    this.port = options.port
    this.debug = options.debug ?? false
    this.apiKey = options.apiKey
    this.attestationEngine = new AttestationEngine()
    this.antiSybilGuard = new AntiSybilGuard()
    this._setup()
  }

  start(
    capIndex: CapabilityIndex,
    peerRegistry: PeerRegistry,
    meshSync: MeshSync,
    taskRouter: TaskRouter,
    taskHistory: TaskHistory,
    metrics: MetricsCollector,
    _security?: SecurityConfig,
    detectionCoord?: DetectionCoord,
  ): Promise<void> {
    this.capIndex = capIndex
    this.peerRegistry = peerRegistry
    this.meshSync = meshSync
    this.taskRouterInst = taskRouter
    this.taskHistory = taskHistory
    this.metrics = metrics
    this.detectionCoord = detectionCoord!

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
    // Keep a stable ref to `this` for closures inside deps objects
    // eslint-disable-next-line @typescript-eslint/no-this-alias
    const self = this

    this.app.use(express.json())

    // CORS for visualization clients
    this.app.use((_req, res, next) => {
      res.setHeader('Access-Control-Allow-Origin', '*')
      res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
      res.setHeader('Access-Control-Allow-Headers', 'Content-Type, Authorization')
      next()
    })

    // Static file serving for web interfaces (before auth middleware)
    this.app.use(express.static('public'))

    // Nexal / topology UI routes (public, no auth required)
    registerNexalRoutes(this.app)

    // Authenticated API router
    const router: Router = express.Router()

    if (this.apiKey) {
      router.use(createAuthMiddleware({ apiKey: this.apiKey }))
    }

    buildMeshRouter(router, {
      hub: self.hub,
      startTime: self.startTime,
      get capIndex() { return self.capIndex },
      get peerRegistry() { return self.peerRegistry },
      get metrics() { return self.metrics },
    })

    buildAgentRouter(router, {
      hub: self.hub,
      get capIndex() { return self.capIndex },
      get meshSync() { return self.meshSync },
      log: self.log.bind(self),
    })

    buildTaskRouter(router, {
      hub: self.hub,
      get capIndex() { return self.capIndex },
      get taskRouter() { return self.taskRouterInst },
      get taskHistory() { return self.taskHistory },
    })

    buildTeacupsRouter(router, {
      get taskHistory() { return self.taskHistory },
    })

    buildAttestationRouter(router, {
      attestationEngine: self.attestationEngine,
      antiSybilGuard: self.antiSybilGuard,
      get capIndex() { return self.capIndex },
      log: self.log.bind(self),
    })

    buildDetectionRouter(router, {
      get detectionCoord() { return self.detectionCoord },
    })

    buildDashboardRouter(router, {
      get hub() { return self.hub },
      get metrics() { return self.metrics },
      get peerRegistry() { return self.peerRegistry },
      get taskRouter() { return self.taskRouterInst },
    })

    this.app.use('/', router)
  }

  /** Expose attestation engine for testing */
  getAttestationEngine(): AttestationEngine { return this.attestationEngine }

  /** Expose anti-sybil guard for testing */
  getAntiSybilGuard(): AntiSybilGuard { return this.antiSybilGuard }

  private log(msg: string): void {
    if (this.debug) console.log(`[RestApi:${this.hub}] ${msg}`)
  }
}
