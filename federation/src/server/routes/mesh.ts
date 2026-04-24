/**
 * mesh.ts — /mesh, /peers, /capabilities, /dark-circles, /status, /metrics, /gossip routes.
 */
import { type Request, type Response, type Router } from 'express'
import type { CapabilityIndex } from '../capability-index.js'
import type { PeerRegistry } from '../peer-registry.js'
import type { MetricsCollector } from '../metrics.js'

export interface MeshRouterDeps {
  hub: string
  startTime: number
  capIndex: CapabilityIndex
  peerRegistry: PeerRegistry
  metrics: MetricsCollector
}

export function buildMeshRouter(router: Router, deps: MeshRouterDeps): void {
  router.get('/status', (req, res) => _status(req, res, deps))
  router.get('/peers', (req, res) => _peers(req, res, deps))
  router.get('/capabilities', (req, res) => _capabilities(req, res, deps))
  router.get('/dark-circles', (req, res) => _darkCircles(req, res, deps))
  router.get('/mesh', (req, res) => _mesh(req, res, deps))
  router.get('/metrics', (req, res) => _metrics(req, res, deps))
  router.get('/gossip', (req, res) => _gossip(req, res, deps))
}

function _status(_req: Request, res: Response, { hub, startTime, capIndex, peerRegistry }: MeshRouterDeps): void {
  const stats = capIndex.stats()
  res.json({
    hub,
    status: 'ok',
    uptime: Math.floor((Date.now() - startTime) / 1000),
    peers: peerRegistry.getPeers().length,
    agents: stats.agents,
    capabilities: stats.capabilities,
    darkCircles: stats.darkCircles,
    timestamp: new Date().toISOString(),
  })
}

function _peers(_req: Request, res: Response, { hub, peerRegistry }: MeshRouterDeps): void {
  res.json({ hub, peers: peerRegistry.getPeers() })
}

function _capabilities(_req: Request, res: Response, { hub, capIndex }: MeshRouterDeps): void {
  const capabilities = capIndex.getAllCapabilities()
  const withAgents = capabilities.map(cap => ({
    capability: cap,
    agents: capIndex.findByCapability(cap).map(a => `${a.name}@${a.hub}`),
  }))
  res.json({ hub, capabilities: withAgents })
}

function _darkCircles(_req: Request, res: Response, { hub, capIndex }: MeshRouterDeps): void {
  const circles = capIndex.getDarkCircles()
  res.json({ hub, darkCircles: circles.sort((a, b) => b.pressure - a.pressure) })
}

function _mesh(_req: Request, res: Response, { hub, capIndex, peerRegistry }: MeshRouterDeps): void {
  const stats = capIndex.stats()
  res.json({
    hub,
    agents: capIndex.getAllAgents(),
    peers: peerRegistry.getPeers(),
    darkCircles: capIndex.getDarkCircles(),
    capabilities: capIndex.getAllCapabilities(),
    stats: {
      agents: stats.agents,
      capabilities: stats.capabilities,
      darkCircles: stats.darkCircles,
      hubs: Array.from(stats.hubs),
    },
    timestamp: new Date().toISOString(),
  })
}

function _metrics(_req: Request, res: Response, { metrics }: MeshRouterDeps): void {
  res.json(metrics.getSnapshot())
}

function _gossip(_req: Request, res: Response, { hub, peerRegistry }: MeshRouterDeps): void {
  const sampler = peerRegistry.sampler
  res.json({
    hub,
    viewSize: sampler.viewCount,
    knownPeers: sampler.knownCount,
    view: sampler.getView().map(d => ({
      hub: d.hub,
      address: d.address,
      age: d.age,
    })),
  })
}
