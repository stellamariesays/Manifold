#!/usr/bin/env node
/**
 * Manifold MCP Server — exposes the Manifold federation mesh as MCP tools.
 *
 * Lets external AI clients (Claude Code, Cursor, Windsurf, etc.) query and
 * dispatch tasks through the Manifold mesh via the Model Context Protocol.
 *
 * Usage:
 *   MANIFOLD_REST_URL=http://localhost:8777 node manifold-mcp-server.js
 *
 * Or configure in Claude Code's MCP settings:
 *   { "mcpServers": { "manifold": { "command": "node", "args": ["path/to/manifold-mcp-server.mjs"] } } }
 */

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";

const REST_URL = process.env.MANIFOLD_REST_URL || "http://localhost:8777";

async function apiGet(path: string): Promise<any> {
  const res = await fetch(`${REST_URL}${path}`);
  if (!res.ok) throw new Error(`GET ${path}: ${res.status} ${await res.text()}`);
  return res.json();
}

async function apiPost(path: string, body: any): Promise<any> {
  const res = await fetch(`${REST_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`POST ${path}: ${res.status} ${await res.text()}`);
  return res.json();
}

// ── Server ──────────────────────────────────────────────────────────────────

const server = new McpServer({
  name: "manifold-mesh",
  version: "1.0.0",
});

server.tool(
  "mesh_status",
  "Get Manifold mesh status — hub name, peer count, agent count, capabilities, uptime",
  {},
  async () => {
    const status = await apiGet("/status");
    return {
      content: [{
        type: "text" as const,
        text: `Hub: ${status.hub}\nStatus: ${status.status}\nPeers: ${status.peers}\nAgents: ${status.agents}\nCapabilities: ${status.capabilities}\nDark Circles: ${status.darkCircles}\nUptime: ${Math.floor(status.uptime / 60)}m`,
      }],
    };
  },
);

server.tool(
  "mesh_agents",
  "List all agents across all hubs in the Manifold mesh, with their capabilities",
  {},
  async () => {
    const mesh = await apiGet("/mesh");
    const lines = mesh.agents.map((a: any) =>
      `${a.name}@${a.hub} — caps: [${(a.capabilities || []).join(", ")}]`
    );
    return {
      content: [{
        type: "text" as const,
        text: `${mesh.agents.length} agents across ${mesh.stats.hubs.length} hubs:\n\n${lines.join("\n")}`,
      }],
    };
  },
);

server.tool(
  "mesh_task",
  "Dispatch a task to an agent on the Manifold mesh. Target format: 'agent@hub'",
  {
    target: z.string().describe("Agent target, e.g. 'void-watcher@thefog' or 'stella@satelliteA'"),
    command: z.string().describe("Command to send to the agent"),
    args: z.record(z.unknown()).optional().describe("Arguments for the command"),
    timeout_ms: z.number().optional().describe("Timeout in milliseconds (default 30000)"),
  },
  async ({ target, command, args, timeout_ms }) => {
    const result = await apiPost("/task", {
      target,
      command,
      args: args || {},
      timeout_ms: timeout_ms || 30000,
    });
    const status = result.status;
    const output = result.output ? JSON.stringify(result.output, null, 2) : "";
    const error = result.error || "";
    return {
      content: [{
        type: "text" as const,
        text: `Task ${result.task_id}: ${status}${error ? "\nError: " + error : ""}${output ? "\nOutput: " + output : ""}${result.executed_by ? "\nExecuted by: " + result.executed_by : ""}${result.execution_ms ? " (" + result.execution_ms + "ms)" : ""}`,
      }],
    };
  },
);

server.tool(
  "mesh_discover",
  "Find agents that have a specific capability",
  {
    capability: z.string().describe("Capability to search for, e.g. 'solar-monitoring' or 'deployment'"),
  },
  async ({ capability }) => {
    const result = await apiGet(`/agents/capability/${encodeURIComponent(capability)}`);
    const agents = result.agents || result;
    if (Array.isArray(agents)) {
      const lines = agents.map((a: any) => `${a.name}@${a.hub} — [${(a.capabilities || []).join(", ")}]`);
      return {
        content: [{
          type: "text" as const,
          text: agents.length > 0
            ? `${agents.length} agents with '${capability}':\n\n${lines.join("\n")}`
            : `No agents found with capability '${capability}'`,
        }],
      };
    }
    return {
      content: [{ type: "text" as const, text: JSON.stringify(result, null, 2) }],
    };
  },
);

server.tool(
  "mesh_peers",
  "List connected hubs in the Manifold mesh",
  {},
  async () => {
    const data = await apiGet("/peers");
    const peers = data.peers || [];
    const lines = peers.map((p: any) =>
      `${p.hub} — agents: ${p.agentCount ?? "?"} (connected ${p.connectedAt ? new Date(p.connectedAt).toLocaleString() : "?"})`
    );
    return {
      content: [{
        type: "text" as const,
        text: peers.length > 0
          ? `${peers.length} connected hubs:\n\n${lines.join("\n")}`
          : "No peers connected",
      }],
    };
  },
);

// ── Start ───────────────────────────────────────────────────────────────────

const transport = new StdioServerTransport();
await server.connect(transport);
