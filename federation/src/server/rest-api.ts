import express, { type Request, type Response, type Router } from 'express'
import type { CapabilityIndex } from './capability-index.js'
import type { PeerRegistry } from './peer-registry.js'
import type { MeshSync } from './mesh-sync.js'
import type { TaskRouter } from './task-router.js'
import type { TaskHistory } from './task-history.js'
import type { MetricsCollector } from './metrics.js'
import type { SecurityConfig } from './security.js'
import { createAuthMiddleware } from './security.js'
import type { DetectionCoord } from './detection-coord.js'
import type { TaskRequest, TaskResult } from '../protocol/messages.js'
import { AttestationEngine } from '../attestation/engine.js'
import { AntiSybilGuard, solvePoW } from '../attestation/anti-sybil.js'
import type { ChallengeType } from '../attestation/challenges.js'

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
  private taskRouter!: TaskRouter
  private taskHistory!: TaskHistory
  private metrics!: MetricsCollector
  private detectionCoord!: DetectionCoord
  private attestationEngine: AttestationEngine
  private antiSybilGuard: AntiSybilGuard
  private startTime = Date.now()

  constructor(options: RestApiOptions) {
    this.hub = options.hub
    this.port = options.port
    this.debug = options.debug ?? false
    this.attestationEngine = new AttestationEngine()
    this.antiSybilGuard = new AntiSybilGuard()
    this._setup()
  }

  start(capIndex: CapabilityIndex, peerRegistry: PeerRegistry, meshSync: MeshSync, taskRouter: TaskRouter, taskHistory: TaskHistory, metrics: MetricsCollector, security?: SecurityConfig, detectionCoord?: DetectionCoord): Promise<void> {
    this.capIndex = capIndex
    this.peerRegistry = peerRegistry
    this.meshSync = meshSync
    this.taskRouter = taskRouter
    this.taskHistory = taskHistory
    this.metrics = metrics
    this.detectionCoord = detectionCoord!

    // Apply auth middleware if configured
    if (security?.apiKey) {
      this.app.use(createAuthMiddleware(security))
    }

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
    router.post('/agents/register', this._registerAgent.bind(this))
    router.put('/agents/:name/heartbeat', this._heartbeatAgent.bind(this))
    router.delete('/agents/:name', this._deregisterAgent.bind(this))
    router.get('/agents/:name', this._agent.bind(this))
    router.get('/capabilities', this._capabilities.bind(this))
    router.get('/dark-circles', this._darkCircles.bind(this))
    router.get('/mesh', this._mesh.bind(this))
    router.post('/query', this._query.bind(this))
    router.post('/route', this._route.bind(this))
    router.post('/task', this._submitTask.bind(this))
    router.get('/task/:id', this._taskStatus.bind(this))
    router.get('/tasks', this._pendingTasks.bind(this))
    router.get('/metrics', this._metrics.bind(this))
    router.get('/task-history', this._taskHistory.bind(this))
    router.get('/teacups', this._teacups.bind(this))
    router.post('/teacup/:id/score', this._scoreTeacup.bind(this))
    router.get('/dashboard', this._dashboard.bind(this))

    // Phase 2: Attestation endpoints
    router.post('/attestation/challenge', this._attestationChallenge.bind(this))
    router.post('/attestation/proof', this._attestationProof.bind(this))
    router.post('/attestation/attest', this._attestationAttest.bind(this))
    router.get('/attestation/status/:agentId/:capability', this._attestationStatus.bind(this))
    router.post('/registration/challenge', this._registrationChallenge.bind(this))
    router.post('/registration/verify', this._registrationVerify.bind(this))

    // Phase 3: Detection-Coordination endpoints
    // NOTE: /detections/stats MUST come before /detections/:id (Express matches in order)
    router.get('/detections/stats', this._detectionStats.bind(this))
    router.get('/detections', this._detections.bind(this))
    router.get('/detections/:id', this._detectionDetail.bind(this))
    router.get('/trust', this._trustScores.bind(this))
    router.get('/gossip', this._gossip.bind(this))
    router.post('/detection/claim', this._submitClaim.bind(this))
    router.post('/detection/verify', this._submitVerify.bind(this))
    router.post('/detection/outcome', this._submitOutcome.bind(this))

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

  /**
   * POST /agents/register — register an agent (called by agent-runner on startup).
   */
  private _registerAgent(req: Request, res: Response): void {
    const { name, capabilities, seams } = req.body as {
      name?: string
      capabilities?: string[]
      seams?: string[]
    }

    if (!name || !capabilities) {
      res.status(400).json({ error: 'name and capabilities are required' })
      return
    }

    const { added } = this.capIndex.upsertAgent(
      { name, hub: this.hub, capabilities, seams },
      true,
    )

    // Rebuild bloom filter so peers see the new agent
    this.meshSync.onLocalChange()

    const status = added ? 'registered' : 'updated'
    this.log(`REST register ${name}: ${status} (${capabilities.length} caps)`)
    res.json({ status, name, hub: this.hub, capabilities })
  }

  /**
   * PUT /agents/:name/heartbeat — renew an agent's TTL.
   */
  private _heartbeatAgent(req: Request, res: Response): void {
    const name = String(req.params['name'] ?? '')
    const agent = this.capIndex.getAllAgents().find(a => a.name === name && a.isLocal)

    if (!agent) {
      res.status(404).json({ error: `Agent not found: ${name}` })
      return
    }

    // Touch the agent's lastSeen timestamp
    this.capIndex.upsertAgent(
      { name, hub: this.hub, capabilities: agent.capabilities, seams: agent.seams },
      true,
    )

    res.json({ status: 'ok', name })
  }

  /**
   * DELETE /agents/:name — deregister an agent (called by agent-runner on shutdown).
   */
  private _deregisterAgent(req: Request, res: Response): void {
    const name = String(req.params['name'] ?? '')
    const removed = this.capIndex.removeAgent(name, this.hub)

    if (removed) {
      this.meshSync.onLocalChange()
      this.log(`REST deregister ${name}: removed`)
    }

    res.json({ status: removed ? 'removed' : 'not_found', name })
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

  /**
   * POST /task — submit a task for execution.
   * Blocks until result is available (with timeout).
   */
  private _submitTask(req: Request, res: Response): void {
    const { target, command, args, timeout_ms, capability, teacup } = req.body as {
      target?: string
      command?: string
      args?: Record<string, unknown>
      timeout_ms?: number
      capability?: string
      teacup?: { trigger: string; ground_state?: string; observation?: string }
    }

    if (!command) {
      res.status(400).json({ error: 'command is required' })
      return
    }

    const resolvedTarget = target ?? 'any'
    const task: TaskRequest = {
      id: crypto.randomUUID(),
      target: resolvedTarget,
      capability,
      command,
      args,
      timeout_ms: timeout_ms ?? 30_000,
      origin: this.hub,
      caller: `${this.hub}`,
      created_at: new Date().toISOString(),
      teacup,
    }

    // For "any" target with capability, resolve to best agent
    if (resolvedTarget === 'any' && capability) {
      const agents = this.capIndex.findByCapability(capability)
      if (agents.length === 0) {
        res.status(404).json({ error: `No agent found with capability: ${capability}` })
        return
      }
      // Prefer local agents
      const local = agents.find(a => a.isLocal)
      const chosen = local ?? agents[0]
      task.target = `${chosen.name}@${chosen.hub}`
    } else if (resolvedTarget === 'any') {
      res.status(400).json({ error: 'capability is required when target is "any"' })
      return
    }

    // Set up response handler
    const onResult = (result: { result: TaskResult; task: TaskRequest }) => {
      if (result.task.id === task.id) {
        clearTimeout(timeout)
        this.taskRouter.removeListener('task:complete', onResult)
        res.json({
          task_id: result.result.id,
          status: result.result.status,
          output: result.result.output,
          error: result.result.error,
          executed_by: result.result.executed_by,
          execution_ms: result.result.execution_ms,
          completed_at: result.result.completed_at,
        })
      }
    }

    const timeout = setTimeout(() => {
      this.taskRouter.removeListener('task:complete', onResult)
      res.json({
        task_id: task.id,
        status: 'timeout',
        error: 'Task timed out waiting for result',
        target: task.target,
      })
    }, task.timeout_ms! + 2000)

    this.taskRouter.on('task:complete', onResult)

    // Route the task — if local and no runner, routeTask will emit task:complete with not_found immediately
    this.taskRouter.routeTask(task, null)
  }

  /**
   * GET /task/:id — check task status.
   */
  private _taskStatus(req: Request, res: Response): void {
    const id = String(req.params['id'] ?? '')
    const status = this.taskRouter.getTaskStatus(id)
    res.json({ task_id: id, status })
  }

  /**
   * GET /tasks — list pending tasks.
   */
  private _pendingTasks(_req: Request, res: Response): void {
    res.json({
      pending: this.taskRouter.getPendingTasks(),
      runner_count: this.taskRouter.runnerCount,
    })
  }

  /**
   * GET /teacups — teacup entries (tasks with concrete context).
   * Query params: ?limit=N
   */
  private async _teacups(req: Request, res: Response): Promise<void> {
    const limit = parseInt(String(req.query['limit'] ?? '20'), 10)
    const entries = await this.taskHistory.getTeacups(limit)
    res.json({ count: entries.length, entries })
  }

  /**
   * POST /teacup/:id/score — score a teacup outcome.
   * Body: { score: +1|-1|0, scored_by: "hal"|"auto"|"terrain" }
   */
  private async _scoreTeacup(req: Request, res: Response): Promise<void> {
    const id = String(req.params['id'] ?? '')
    const { score, scored_by } = req.body

    if (typeof score !== 'number' || ![-1, 0, 1].includes(score)) {
      res.status(400).json({ error: 'score must be -1, 0, or 1' })
      return
    }

    const found = await this.taskHistory.scoreOutcome(id, score, String(scored_by ?? 'unknown'))
    if (!found) {
      res.status(404).json({ error: 'Task not found or already scored' })
      return
    }

    res.json({ ok: true, id, score, scored_by })
  }

  /**
   * GET /metrics — JSON metrics snapshot.
   */
  private _metrics(_req: Request, res: Response): void {
    res.json(this.metrics.getSnapshot())
  }

  /**
   * GET /task-history — recent task history.
   * Query params: ?limit=N&offset=N
   */
  private async _taskHistory(req: Request, res: Response): Promise<void> {
    const limit = parseInt(String(req.query['limit'] ?? '50'), 10)
    const offset = parseInt(String(req.query['offset'] ?? '0'), 10)
    const entries = await this.taskHistory.getRecent(limit, offset)
    res.json({ count: entries.length, entries })
  }

  /**
   * GET /dashboard — simple HTML overview.
   */
  private _dashboard(_req: Request, res: Response): void {
    const m = this.metrics.getSnapshot()
    const peers = this.peerRegistry.getPeers()
    const pending = this.taskRouter.getPendingTasks()
    const perAgent = Object.values(m.perAgent)
      .sort((a, b) => b.tasksTotal - a.tasksTotal)

    res.setHeader('Content-Type', 'text/html')
    res.send(`<!DOCTYPE html>
<html><head><title>Manifold — ${m.hub}</title>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<style>
  *{margin:0;padding:0;box-sizing:border-box}
  body{font-family:system-ui,sans-serif;background:#0a0a0a;color:#e0e0e0;padding:1rem}
  h1{color:#60a5fa;font-size:1.5rem;margin-bottom:0.5rem}
  h2{color:#a78bfa;font-size:1.1rem;margin:1rem 0 0.5rem}
  .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:0.5rem;margin:0.5rem 0}
  .card{background:#1a1a2e;border:1px solid #2a2a4a;border-radius:8px;padding:0.75rem}
  .card .label{color:#888;font-size:0.75rem;text-transform:uppercase}
  .card .value{color:#f0f0f0;font-size:1.5rem;font-weight:bold}
  table{width:100%;border-collapse:collapse;margin:0.5rem 0}
  th,td{text-align:left;padding:0.4rem 0.6rem;border-bottom:1px solid #2a2a4a;font-size:0.85rem}
  th{color:#888;font-weight:normal}
  .ok{color:#4ade80} .err{color:#f87171} .warn{color:#fbbf24} .dim{color:#666}
  a{color:#60a5fa;text-decoration:none}
  .refresh{float:right;color:#888;font-size:0.8rem}
</style>
</head><body>
<h1>🕸️ Manifold — ${m.hub}</h1>
<div class="refresh">Auto-refreshes every 10s &middot; <a href="/dashboard">↻</a></div>

<div class="grid">
  <div class="card"><div class="label">Uptime</div><div class="value">${this._fmtUptime(m.uptime)}</div></div>
  <div class="card"><div class="label">Peers</div><div class="value">${m.peers}</div></div>
  <div class="card"><div class="label">Agents</div><div class="value">${m.agents}</div></div>
  <div class="card"><div class="label">Capabilities</div><div class="value">${m.capabilities}</div></div>
  <div class="card"><div class="label">Runners</div><div class="value">${m.runnersConnected}</div></div>
  <div class="card"><div class="label">Dark Circles</div><div class="value">${m.darkCircles}</div></div>
</div>

<h2>📊 Task Stats</h2>
<div class="grid">
  <div class="card"><div class="label">Total Tasks</div><div class="value">${m.tasksTotal}</div></div>
  <div class="card"><div class="label">Success</div><div class="value ok">${m.tasksSuccess}</div></div>
  <div class="card"><div class="label">Errors</div><div class="value err">${m.tasksError}</div></div>
  <div class="card"><div class="label">Success Rate</div><div class="value">${m.successRate}</div></div>
  <div class="card"><div class="label">Avg Latency</div><div class="value">${m.avgExecutionMs}ms</div></div>
  <div class="card"><div class="label">Pending</div><div class="value warn">${m.tasksPending}</div></div>
</div>

<h2>🤖 Per-Agent Stats</h2>
<table><tr><th>Agent</th><th>Total</th><th>✓</th><th>✗</th><th>Avg ms</th><th>Last Seen</th></tr>
${perAgent.length > 0 ? perAgent.map(a => `<tr>
  <td>${a.name}<span class="dim">@${a.hub}</span></td>
  <td>${a.tasksTotal}</td>
  <td class="ok">${a.tasksSuccess}</td>
  <td class="err">${a.tasksError + a.tasksTimeout}</td>
  <td>${a.avgExecutionMs}</td>
  <td class="dim">${a.lastSeen ? this._fmtTime(a.lastSeen) : '—'}</td>
</tr>`).join('') : '<tr><td colspan="6" class="dim">No tasks executed yet</td></tr>'}
</table>

<h2>🌐 Peers</h2>
<table><tr><th>Hub</th><th>Address</th><th>Agents</th><th>Last Seen</th></tr>
${peers.map(p => `<tr>
  <td>${p.hub}</td>
  <td class="dim">${p.address}</td>
  <td>${p.agentCount ?? '?'}</td>
  <td class="dim">${this._fmtTime(p.lastSeen)}</td>
</tr>`).join('') || '<tr><td colspan="4" class="dim">No peers connected</td></tr>'}
</table>

${pending.length > 0 ? `<h2>⏳ Pending Tasks</h2>
<table><tr><th>ID</th><th>Target</th><th>Command</th><th>Age</th></tr>
${pending.map(t => `<tr>
  <td class="dim">${t.id.substring(0, 8)}...</td>
  <td>${t.target}</td>
  <td>${t.command}</td>
  <td>${(t.age_ms / 1000).toFixed(1)}s</td>
</tr>`).join('')}</table>` : ''}

<script>setTimeout(() => location.reload(), 10000)</script>
</body></html>`)
  }

  // ── Helpers for dashboard ──────────────────────────────────────────────────

  private _fmtUptime(seconds: number): string {
    if (seconds < 60) return `${seconds}s`
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${seconds % 60}s`
    const h = Math.floor(seconds / 3600)
    const m = Math.floor((seconds % 3600) / 60)
    return `${h}h ${m}m`
  }

  private _fmtTime(iso: string | null | undefined): string {
    if (!iso) return '—'
    try {
      const d = new Date(iso)
      return d.toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit' })
    } catch {
      return iso
    }
  }

  private log(msg: string): void {
    if (this.debug) console.log(`[RestApi:${this.hub}] ${msg}`)
  }

  // ── Phase 3: Detection-Coordination handlers ─────────────────────────────

  private _detections(req: Request, res: Response): void {
    const domain = req.query['domain'] as string | undefined
    const limit = parseInt(req.query['limit'] as string ?? '20', 10)
    const open = req.query['open'] === 'true'

    let claims = open
      ? this.detectionCoord.getOpenClaims(domain)
      : domain
        ? this.detectionCoord.getOpenClaims(domain)
        : this.detectionCoord.ledger.getRecentClaims(limit)

    res.json({
      claims: claims.slice(0, limit).map(e => ({
        id: e.claim.id,
        source: e.claim.source,
        domain: e.claim.domain,
        summary: e.claim.summary,
        confidence: e.claim.confidence,
        created_at: e.claim.created_at,
        verifications: e.verifications.length,
        challenges: e.challenges.length,
        outcome: e.outcome?.outcome ?? null,
      })),
      total: claims.length,
    })
  }

  private _detectionDetail(req: Request, res: Response): void {
    const id = String(req.params['id'] ?? '')
    const entry = this.detectionCoord.getClaim(id)
    if (!entry) {
      res.status(404).json({ error: 'Claim not found' })
      return
    }
    res.json({
      claim: entry.claim,
      verifications: entry.verifications,
      challenges: entry.challenges,
      outcome: entry.outcome,
      trust_score: this.detectionCoord.ledger.getTrustScore(entry.claim.source),
    })
  }

  private _detectionStats(_req: Request, res: Response): void {
    res.json(this.detectionCoord.getStats())
  }

  private _trustScores(_req: Request, res: Response): void {
    res.json(this.detectionCoord.getTrustScores())
  }

  private _submitClaim(req: Request, res: Response): void {
    const { source, domain, summary, confidence, evidence_hash, ttl_seconds, evidence } = req.body as {
      source?: string
      domain?: string
      summary?: string
      confidence?: number
      evidence_hash?: string
      ttl_seconds?: number
      evidence?: Record<string, unknown>
    }

    if (!source || !domain || !summary || confidence === undefined) {
      res.status(400).json({ error: 'source, domain, summary, and confidence are required' })
      return
    }

    const claim = {
      id: crypto.randomUUID(),
      source,
      domain,
      summary,
      confidence: Math.max(0, Math.min(1, confidence)),
      evidence_hash: evidence_hash ?? '',
      created_at: new Date().toISOString(),
      ttl_seconds,
      evidence,
    }

    this.detectionCoord.handleMessage({ type: 'detection_claim', claim })

    res.json({
      claim_id: claim.id,
      status: 'recorded',
      propagated: true,
    })
  }

  private _submitVerify(req: Request, res: Response): void {
    const { claim_id, verifier, agrees, confidence, notes } = req.body as {
      claim_id?: string
      verifier?: string
      agrees?: boolean
      confidence?: number
      notes?: string
    }

    if (!claim_id || !verifier || agrees === undefined) {
      res.status(400).json({ error: 'claim_id, verifier, and agrees are required' })
      return
    }

    const verification = {
      claim_id,
      verifier,
      agrees,
      confidence: confidence ?? (agrees ? 0.8 : 0.2),
      notes,
      verified_at: new Date().toISOString(),
    }

    this.detectionCoord.handleMessage({ type: 'detection_verify', verification })

    res.json({
      claim_id,
      status: 'verified',
      agrees,
    })
  }

  private _submitOutcome(req: Request, res: Response): void {
    const { claim_id, outcome, resolved_by, notes, superseded_by } = req.body as {
      claim_id?: string
      outcome?: 'confirmed' | 'false_positive' | 'expired' | 'superseded'
      resolved_by?: string
      notes?: string
      superseded_by?: string
    }

    if (!claim_id || !outcome || !resolved_by) {
      res.status(400).json({ error: 'claim_id, outcome, and resolved_by are required' })
      return
    }

    const detectionOutcome = {
      claim_id,
      outcome,
      resolved_by,
      resolved_at: new Date().toISOString(),
      notes,
      superseded_by,
    }

    this.detectionCoord.handleMessage({ type: 'detection_outcome', outcome: detectionOutcome })

    res.json({
      claim_id,
      status: outcome,
    })
  }

  // ── Phase 2: Attestation handlers ─────────────────────────────────────────

  /**
   * POST /attestation/challenge — issue a challenge for a capability claim.
   * Body: { capability, agentId, difficulty?, type? }
   */
  private _attestationChallenge(req: Request, res: Response): void {
    const { capability, agentId, difficulty, type } = req.body as {
      capability?: string
      agentId?: string
      difficulty?: number
      type?: ChallengeType
    }

    if (!capability || !agentId) {
      res.status(400).json({ error: 'capability and agentId are required' })
      return
    }

    const challenge = this.attestationEngine.issueChallenge(capability, agentId, difficulty, type)
    this.log(`Attestation challenge issued: ${challenge.id} for ${agentId} / ${capability}`)
    res.json({ challenge })
  }

  /**
   * POST /attestation/proof — submit proof for a challenge.
   * Body: { challengeId, agentId, response }
   */
  private _attestationProof(req: Request, res: Response): void {
    const { challengeId, agentId, response } = req.body as {
      challengeId?: string
      agentId?: string
      response?: Record<string, unknown>
    }

    if (!challengeId || !agentId || !response) {
      res.status(400).json({ error: 'challengeId, agentId, and response are required' })
      return
    }

    const result = this.attestationEngine.submitProof(challengeId, agentId, response)
    if (!result.success) {
      res.status(400).json({ error: result.error })
      return
    }

    this.log(`Attestation proof submitted: ${challengeId} by ${agentId}`)
    res.json({ status: 'proof_submitted', challengeId })
  }

  /**
   * POST /attestation/attest — peer attests to a proof.
   * Body: { challengeId, peerId, score, notes? }
   */
  private _attestationAttest(req: Request, res: Response): void {
    const { challengeId, peerId, score, notes } = req.body as {
      challengeId?: string
      peerId?: string
      score?: number
      notes?: string
    }

    if (!challengeId || !peerId || score === undefined) {
      res.status(400).json({ error: 'challengeId, peerId, and score are required' })
      return
    }

    const result = this.attestationEngine.addAttestation(challengeId, peerId, score, notes)
    if (!result.success) {
      res.status(400).json({ error: result.error })
      return
    }

    // Update CapabilityIndex attestation scores
    const record = this.attestationEngine.getRecord(challengeId)
    if (record) {
      const scoreData = this.attestationEngine.getScore(
        record.challenge.agentId,
        record.challenge.capability,
      )
      this.capIndex.setAttestationScore(
        record.challenge.agentId,
        record.challenge.capability,
        scoreData.averageScore,
        scoreData.attestationCount,
        scoreData.isAttested,
      )
    }

    this.log(`Attestation: ${peerId} attested ${challengeId} with score ${score}`)
    res.json({ status: 'attested', challengeId })
  }

  /**
   * GET /attestation/status/:agentId/:capability — check attestation status.
   */
  private _attestationStatus(req: Request, res: Response): void {
    const agentId = decodeURIComponent(String(req.params['agentId'] ?? ''))
    const capability = decodeURIComponent(String(req.params['capability'] ?? ''))

    const score = this.attestationEngine.getScore(agentId, capability)
    res.json(score)
  }

  /**
   * POST /registration/challenge — get a PoW challenge for registration.
   */
  private _registrationChallenge(req: Request, res: Response): void {
    const ip = req.ip ?? req.socket.remoteAddress ?? 'unknown'
    const challenge = this.antiSybilGuard.issueChallenge(ip)

    if (!challenge) {
      res.status(429).json({ error: 'Rate limited — too many registration attempts from this IP' })
      return
    }

    res.json({ challenge })
  }

  /**
   * POST /registration/verify — submit PoW solution.
   * Body: { challengeId, nonce, hash }
   */
  private _registrationVerify(req: Request, res: Response): void {
    const { challengeId, nonce, hash } = req.body as {
      challengeId?: string
      nonce?: string
      hash?: string
    }

    if (!challengeId || !nonce || !hash) {
      res.status(400).json({ error: 'challengeId, nonce, and hash are required' })
      return
    }

    const ip = req.ip ?? req.socket.remoteAddress ?? 'unknown'
    const result = this.antiSybilGuard.verifySolution({ challengeId, nonce, hash }, ip)

    if (!result.valid) {
      res.status(400).json({ error: result.error })
      return
    }

    this.log(`PoW registration verified: challenge ${challengeId}`)
    res.json({ status: 'verified', message: 'Registration approved' })
  }

  /** Expose attestation engine for testing */
  getAttestationEngine(): AttestationEngine { return this.attestationEngine }

  /** Expose anti-sybil guard for testing */
  getAntiSybilGuard(): AntiSybilGuard { return this.antiSybilGuard }

  // ── Gossip ─────────────────────────────────────────────────────────────────

  private _gossip(_req: Request, res: Response): void {
    const sampler = this.peerRegistry.sampler
    res.json({
      hub: this.hub,
      viewSize: sampler.viewCount,
      knownPeers: sampler.knownCount,
      view: sampler.getView().map(d => ({
        hub: d.hub,
        address: d.address,
        age: d.age,
      })),
    })
  }
}
