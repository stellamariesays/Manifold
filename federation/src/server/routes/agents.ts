/**
 * agents.ts — Agent register/heartbeat/deregister/list/get routes.
 */
import { type Request, type Response, type Router } from 'express'
import type { CapabilityIndex } from '../capability-index.js'
import type { MeshSync } from '../mesh-sync.js'

export interface AgentRouterDeps {
  hub: string
  capIndex: CapabilityIndex
  meshSync: MeshSync
  log: (msg: string) => void
}

export function buildAgentRouter(router: Router, deps: AgentRouterDeps): void {
  router.get('/agents', (req, res) => _agents(req, res, deps))
  router.post('/agents/register', (req, res) => _registerAgent(req, res, deps))
  router.put('/agents/:name/heartbeat', (req, res) => _heartbeatAgent(req, res, deps))
  router.delete('/agents/:name', (req, res) => _deregisterAgent(req, res, deps))
  router.get('/agents/:name', (req, res) => _agent(req, res, deps))
}

function _agents(req: Request, res: Response, { hub, capIndex }: AgentRouterDeps): void {
  const { hub: hubFilter, capability } = req.query as Record<string, string>
  let agents = capIndex.getAllAgents()
  if (hubFilter) agents = agents.filter(a => a.hub === hubFilter)
  if (capability) agents = agents.filter(a => a.capabilities.includes(capability))
  res.json({ hub, count: agents.length, agents })
}

function _agent(req: Request, res: Response, { capIndex }: AgentRouterDeps): void {
  const name = String(req.params['name'] ?? '')
  const [agentName, agentHub] = name.includes('@') ? name.split('@') : [name, undefined]
  const agent = agentHub
    ? capIndex.getAgent(agentName, agentHub)
    : capIndex.getAllAgents().find(a => a.name === agentName)
  if (!agent) {
    res.status(404).json({ error: `Agent not found: ${name}` })
    return
  }
  res.json(agent)
}

function _registerAgent(req: Request, res: Response, { hub, capIndex, meshSync, log }: AgentRouterDeps): void {
  const { name, capabilities, seams } = req.body as {
    name?: string
    capabilities?: string[]
    seams?: string[]
  }
  if (!name || !capabilities) {
    res.status(400).json({ error: 'name and capabilities are required' })
    return
  }
  const { added } = capIndex.upsertAgent({ name, hub, capabilities, seams }, true)
  meshSync.onLocalChange()
  const status = added ? 'registered' : 'updated'
  log(`REST register ${name}: ${status} (${capabilities.length} caps)`)
  res.json({ status, name, hub, capabilities })
}

function _heartbeatAgent(req: Request, res: Response, { hub, capIndex }: AgentRouterDeps): void {
  const name = String(req.params['name'] ?? '')
  const agent = capIndex.getAllAgents().find(a => a.name === name && a.isLocal)
  if (!agent) {
    res.status(404).json({ error: `Agent not found: ${name}` })
    return
  }
  capIndex.upsertAgent({ name, hub, capabilities: agent.capabilities, seams: agent.seams }, true)
  res.json({ status: 'ok', name })
}

function _deregisterAgent(req: Request, res: Response, { hub, capIndex, meshSync, log }: AgentRouterDeps): void {
  const name = String(req.params['name'] ?? '')
  const removed = capIndex.removeAgent(name, hub)
  if (removed) {
    meshSync.onLocalChange()
    log(`REST deregister ${name}: removed`)
  }
  res.json({ status: removed ? 'removed' : 'not_found', name })
}
