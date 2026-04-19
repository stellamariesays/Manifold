# Manifold MCP Server

Expose the Manifold federation mesh to external AI clients via the Model Context Protocol (MCP).

Any MCP-compatible client (Claude Code, Cursor, Windsurf, etc.) can query the mesh, discover agents, and dispatch tasks.

## Setup

```bash
cd federation
npm install
npm run build
```

## Configuration

### Claude Code

Add to your `claude_desktop_config.json` or `.claude/mcp.json`:

```json
{
  "mcpServers": {
    "manifold": {
      "command": "node",
      "args": ["/path/to/manifold/federation/dist/mcp/manifold-mcp-server.js"],
      "env": {
        "MANIFOLD_REST_URL": "http://localhost:8777"
      }
    }
  }
}
```

### Cursor

Add to your `.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "manifold": {
      "command": "node",
      "args": ["/path/to/manifold/federation/dist/mcp/manifold-mcp-server.js"],
      "env": {
        "MANIFOLD_REST_URL": "http://localhost:8777"
      }
    }
  }
}
```

### Windsurf

Add to your `.windsurf/mcp.json` with the same format.

## Tools

| Tool | Description |
|------|-------------|
| `mesh_status` | Hub status — name, peers, agents, uptime |
| `mesh_agents` | All agents across all hubs with capabilities |
| `mesh_task` | Dispatch a task to an agent (e.g. `void-watcher@thefog`) |
| `mesh_discover` | Find agents by capability (e.g. `solar-monitoring`) |
| `mesh_peers` | Connected hubs and their status |

## Usage Examples

Once configured, your AI client can:

```
"Check what agents are available on the mesh"
→ calls mesh_agents

"Send a solar monitoring task to thefog"
→ calls mesh_task with target="solar-detect@thefog"

"Which agents can do deployment?"
→ calls mesh_discover with capability="deployment"

"What's the mesh status?"
→ calls mesh_status
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MANIFOLD_REST_URL` | `http://localhost:8777` | Manifold REST API endpoint |

## Remote Access

To connect to a remote Manifold hub (e.g. over Tailscale):

```json
"env": { "MANIFOLD_REST_URL": "http://100.70.172.34:8777" }
```
