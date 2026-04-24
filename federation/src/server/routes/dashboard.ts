/**
 * dashboard.ts — GET /dashboard — simple HTML overview of hub status.
 *
 * The HTML template is intentionally inline here because it is tightly
 * coupled to the MetricsCollector snapshot shape.  If it grows significantly,
 * move it to a separate template file.
 */
import { type Request, type Response, type Router } from 'express'
import type { MetricsCollector } from '../metrics.js'
import type { PeerRegistry } from '../peer-registry.js'
import type { TaskRouter } from '../task-router.js'

export interface DashboardRouterDeps {
  hub: string
  metrics: MetricsCollector
  peerRegistry: PeerRegistry
  taskRouter: TaskRouter
}

export function buildDashboardRouter(router: Router, deps: DashboardRouterDeps): void {
  router.get('/dashboard', (_req, res) => _dashboard(_req, res, deps))
}

function _dashboard(_req: Request, res: Response, deps: DashboardRouterDeps): void {
  const m = deps.metrics.getSnapshot()
  const peers = deps.peerRegistry.getPeers()
  const pending = deps.taskRouter.getPendingTasks()
  const perAgent = Object.values(m.perAgent).sort((a, b) => b.tasksTotal - a.tasksTotal)

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
  .examples{background:#16213e;border:1px solid #2563eb;border-radius:8px;padding:1rem;margin:1rem 0}
  .example{background:#0f172a;border:1px solid #1e293b;border-radius:4px;padding:0.75rem;margin:0.5rem 0}
  .example h4{color:#60a5fa;margin:0 0 0.5rem 0;font-size:0.9rem}
  .example pre{background:#000;color:#e2e8f0;padding:0.5rem;border-radius:4px;font-size:0.8rem;overflow-x:auto;margin:0.25rem 0}
  .example .desc{color:#94a3b8;font-size:0.85rem;margin:0.25rem 0}
</style>
</head><body>
<h1>🕸️ Manifold — ${m.hub}</h1>
<div class="refresh">Auto-refreshes every 10s &middot; <a href="/dashboard">↻</a></div>

<div class="grid">
  <div class="card"><div class="label">Uptime</div><div class="value">${_fmtUptime(m.uptime)}</div></div>
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

<div class="examples">
<h2>🚀 Cross-Agent Task Examples</h2>
<div class="desc">Submit tasks to leverage the distributed capabilities across all connected hubs.</div>

<div class="example">
<h4>🔍 Solar Monitoring Pipeline</h4>
<div class="desc">Coordinate solar flare detection across multiple specialized agents</div>
<pre>curl -X POST https://nexal.network/api/task \\
  -H "Content-Type: application/json" \\
  -d '{
    "command": "monitor-solar-activity",
    "target": "solar-detect",
    "params": {
      "threshold": "M-class",
      "duration": "24h",
      "notify": ["stella", "braid"]
    }
  }'</pre>
</div>

<div class="example">
<h4>🤖 Multi-Hub Agent Orchestration</h4>
<div class="desc">Route tasks across hubs using agent capabilities</div>
<pre>curl -X POST https://nexal.network/api/task \\
  -H "Content-Type: application/json" \\
  -d '{
    "command": "coordinate-deployment",
    "capability": "deployment-strategy",
    "params": {
      "project": "manifold-update",
      "hubs": ["hog", "trillian", "thefog"]
    }
  }'</pre>
</div>

<div class="example">
<h4>💬 Conversational + Technical Analysis</h4>
<div class="desc">Combine Bob's conversation skills with Stella's judgment</div>
<pre>curl -X POST https://nexal.network/api/task \\
  -H "Content-Type: application/json" \\
  -d '{
    "command": "analyze-and-explain",
    "targets": ["bob", "stella"],
    "params": {
      "data": "crypto market analysis",
      "format": "conversational-summary"
    }
  }'</pre>
</div>

<div class="example">
<h4>🔧 Infrastructure Health Check</h4>
<div class="desc">Distributed system monitoring across all hubs</div>
<pre>curl -X POST https://nexal.network/api/task \\
  -H "Content-Type: application/json" \\
  -d '{
    "command": "system-health-audit",
    "capability": "system-administration",
    "params": {
      "scope": "all-hubs",
      "include": ["security", "performance", "capacity"]
    }
  }'</pre>
</div>

<div class="example">
<h4>📊 Real-time Dashboard Creation</h4>
<div class="desc">Use solar-sites agent for live visualization</div>
<pre>curl -X POST https://nexal.network/api/task \\
  -H "Content-Type: application/json" \\
  -d '{
    "command": "create-dashboard",
    "target": "solar-sites",
    "params": {
      "data_source": "manifold-metrics",
      "visualization": "d3-network",
      "update_interval": "5s"
    }
  }'</pre>
</div>

<div class="example">
<h4>🎯 Capability Discovery</h4>
<div class="desc">Find agents with specific capabilities across the federation</div>
<pre># List all available capabilities
curl https://nexal.network/api/agents

# Find agents with specific capability
curl "https://nexal.network/api/agents?capability=deployment"

# Check task status
curl https://nexal.network/api/task/&lt;task-id&gt;</pre>
</div>
</div>

<h2>🤖 Per-Agent Stats</h2>
<table><tr><th>Agent</th><th>Total</th><th>✓</th><th>✗</th><th>Avg ms</th><th>Last Seen</th></tr>
${perAgent.length > 0 ? perAgent.map(a => `<tr>
  <td>${a.name}<span class="dim">@${a.hub}</span></td>
  <td>${a.tasksTotal}</td>
  <td class="ok">${a.tasksSuccess}</td>
  <td class="err">${a.tasksError + a.tasksTimeout}</td>
  <td>${a.avgExecutionMs}</td>
  <td class="dim">${a.lastSeen ? _fmtTime(a.lastSeen) : '—'}</td>
</tr>`).join('') : '<tr><td colspan="6" class="dim">No tasks executed yet</td></tr>'}
</table>

<h2>🌐 Peers</h2>
<table><tr><th>Hub</th><th>Address</th><th>Agents</th><th>Last Seen</th></tr>
${peers.map(p => `<tr>
  <td>${p.hub}</td>
  <td class="dim">${p.address}</td>
  <td>${p.agentCount ?? '?'}</td>
  <td class="dim">${_fmtTime(p.lastSeen)}</td>
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

function _fmtUptime(seconds: number): string {
  if (seconds < 60) return `${seconds}s`
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${seconds % 60}s`
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  return `${h}h ${m}m`
}

function _fmtTime(iso: string | null | undefined): string {
  if (!iso) return '—'
  try {
    const d = new Date(iso)
    return d.toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit' })
  } catch {
    return iso
  }
}
