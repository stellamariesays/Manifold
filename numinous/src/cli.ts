/**
 * Numinous CLI — Query and transform the shared terrain.
 * 
 * Usage:
 *   numinous query <query> [--target <name>]
 *   numinous ssh <target>
 *   numinous context <agent-name>
 *   numinous status
 *   numinous blockers
 *   numinous diff --author <who>
 */

import { loadTerrain } from './terrain/loader.js';
import * as Q from './terrain/query.js';
import type { Terrain } from './terrain/schema.js';
import * as fs from 'fs';
import * as path from 'path';

// ─── Find the Manifold memory directory ───────────────────

function findMemoryDir(): string {
  // Check common locations
  const candidates = [
    path.join(process.cwd(), 'memory'),
    path.join(process.env.HOME || '', 'projects', 'Manifold', 'memory'),
    path.join(process.env.HOME || '', 'openclaw-workspace', 'stella', 'projects', 'Manifold', 'memory'),
  ];
  
  for (const dir of candidates) {
    if (fs.existsSync(path.join(dir, 'terrain-delta.md')) ||
        fs.existsSync(path.join(dir, 'index', 'system.json'))) {
      return dir;
    }
  }
  
  // Fall back to first candidate
  return candidates[0];
}

// ─── Formatters ───────────────────────────────────────────

function formatMachine(m: {
  name: string;
  tailscaleIP: string;
  localIP?: string;
  sshUser: string;
  sshKey: string;
  status?: string;
  role?: string;
  operator?: string;
  sshKeyFrom?: string;
}): string {
  const lines = [
    `  ${m.name}`,
    `    IP: ${m.tailscaleIP}${m.localIP ? ` (local: ${m.localIP})` : ''}`,
    `    SSH: ${m.sshUser}@${m.localIP || m.tailscaleIP}${m.sshKey ? ` -i ${m.sshKey}` : ''}`,
  ];
  if (m.status) lines.push(`    Status: ${m.status}`);
  if (m.role) lines.push(`    Role: ${m.role}`);
  if (m.operator) lines.push(`    Operator: ${m.operator}`);
  if (m.sshKeyFrom) lines.push(`    Key from: ${m.sshKeyFrom}`);
  return lines.join('\n');
}

function formatAgent(a: {
  name: string;
  hub: string;
  focus: string;
  status: string;
  runner: boolean;
  capabilities: readonly { name: string }[];
}): string {
  const caps = a.capabilities.map(c => c.name).join(', ');
  return `  ${a.name} @ ${a.hub} [${a.status}]${a.runner ? ' (runner)' : ''} — ${a.focus}${caps ? ` (${caps})` : ''}`;
}

// ─── Commands ─────────────────────────────────────────────

function cmdStatus(terrain: Terrain): void {
  const summary = Q.getMeshSummary(terrain);
  console.log('=== Mesh Status ===');
  console.log(`Hubs: ${summary.hubs}`);
  console.log(`Agents: ${summary.agents} (${summary.runners} runners)`);
  console.log(`Machines: ${summary.liveMachines} live / ${Object.keys(terrain.machines).length} total`);
  console.log(`Projects: ${summary.projects}`);
  console.log(`Terrain generated: ${terrain.generated}`);
  if (terrain.updated) console.log(`Last updated: ${terrain.updated}`);
  console.log();
  
  console.log('--- Machines ---');
  for (const m of Object.values(terrain.machines)) {
    console.log(formatMachine(m));
  }
  
  console.log();
  console.log('--- Agents ---');
  for (const a of Object.values(terrain.agents)) {
    console.log(formatAgent(a));
  }
}

function cmdSSH(terrain: Terrain, target: string): void {
  const ctx = Q.getSSHContext(target)(terrain);
  
  if (!ctx.machine) {
    console.error(`Machine "${target}" not found in terrain.`);
    console.error('Available:', Object.keys(terrain.machines).join(', '));
    process.exit(1);
  }
  
  console.log(`# SSH to ${ctx.machine.name}`);
  console.log(ctx.command || 'No SSH command available');
  console.log();
  console.log(`# Context`);
  console.log(`Machine: ${ctx.machine.name} (${ctx.machine.status})`);
  console.log(`Role: ${ctx.machine.role}`);
  if (ctx.machine.operator) console.log(`Operator: ${ctx.machine.operator}`);
  if (ctx.keyFrom) console.log(`SSH key from: ${ctx.keyFrom.name} (${ctx.keyFrom.tailscaleIP})`);
  
  if (ctx.agentsOnMachine.length > 0) {
    console.log();
    console.log(`# Agents on this machine:`);
    for (const a of ctx.agentsOnMachine) {
      console.log(`  - ${a.name} (${a.focus}) [${a.status}]`);
    }
  }
}

function cmdContext(terrain: Terrain, agentName: string): void {
  const ctx = Q.getAgentContext(agentName)(terrain);
  
  if (!ctx.agent) {
    console.error(`Agent "${agentName}" not found.`);
    console.error('Available:', Object.keys(terrain.agents).join(', '));
    process.exit(1);
  }
  
  console.log(`=== ${ctx.agent.name} ===`);
  console.log(`Hub: ${ctx.agent.hub}`);
  console.log(`Focus: ${ctx.agent.focus}`);
  console.log(`Status: ${ctx.agent.status}`);
  console.log(`Runner: ${ctx.agent.runner}`);
  console.log(`Capabilities: ${ctx.agent.capabilities.map(c => c.name).join(', ') || 'none'}`);
  
  if (ctx.machine) {
    console.log();
    console.log(`--- Machine ---`);
    console.log(formatMachine(ctx.machine));
  }
  
  if (ctx.sshCommand) {
    console.log();
    console.log(`SSH: ${ctx.sshCommand}`);
  }
  
  if (ctx.coAgents.length > 0) {
    console.log();
    console.log(`--- Co-agents on ${ctx.agent.hub} ---`);
    for (const a of ctx.coAgents) {
      console.log(formatAgent(a));
    }
  }
}

function cmdBlockers(terrain: Terrain): void {
  const blockers = Q.getBlockers(terrain);
  
  if (blockers.length === 0) {
    console.log('No blockers found.');
    return;
  }
  
  console.log('=== Blockers ===');
  for (const b of blockers) {
    console.log(`\n${b.project}:`);
    for (const bl of b.blockers) {
      console.log(`  ⚠ ${bl}`);
    }
  }
}

function cmdQuery(terrain: Terrain, query: string): void {
  // Natural-ish query parsing
  const q = query.toLowerCase().trim();
  
  // "where is X" / "find X" / "X"
  const whereMatch = q.match(/^(?:where\s+(?:is|are)\s+|find\s+|locate\s+)?(\S+)$/);
  if (whereMatch) {
    const target = whereMatch[1];
    
    // Try machine first
    const machine = Q.getMachine(target)(terrain);
    if (machine) {
      console.log(formatMachine(machine));
      const sshCmd = Q.getSSHCommand(target)(terrain);
      if (sshCmd) console.log(`\nSSH: ${sshCmd}`);
      return;
    }
    
    // Try agent
    const agentCtx = Q.getAgentContext(target)(terrain);
    if (agentCtx.agent) {
      console.log(formatAgent(agentCtx.agent));
      if (agentCtx.machine) {
        console.log(`On machine:`);
        console.log(formatMachine(agentCtx.machine));
      }
      return;
    }
    
    // Try project
    const project = Q.getProject(target)(terrain);
    if (project) {
      console.log(`${project.name} [${project.status}] — ${project.description || ''}`);
      if (project.blockers?.length) {
        console.log('Blockers:');
        project.blockers.forEach(b => console.log(`  ⚠ ${b}`));
      }
      return;
    }
    
    console.error(`"${target}" not found in terrain.`);
    console.error('Machines:', Object.keys(terrain.machines).join(', '));
    console.error('Agents:', Object.keys(terrain.agents).join(', '));
    console.error('Projects:', Object.keys(terrain.projects).join(', '));
    process.exit(1);
  }
}

// ─── Main ─────────────────────────────────────────────────

function main(): void {
  const args = process.argv.slice(2);
  
  if (args.length === 0) {
    console.log('Usage: numinous <command> [args]');
    console.log('');
    console.log('Commands:');
    console.log('  status              Mesh overview');
    console.log('  ssh <target>        Get SSH command + context for a machine');
    console.log('  context <agent>     Full context for an agent');
    console.log('  blockers            Show all blocked projects');
    console.log('  query <name>        Find anything by name');
    console.log('  json                Dump full terrain as JSON');
    process.exit(0);
  }
  
  const cmd = args[0];
  const memoryDir = findMemoryDir();
  const terrain = loadTerrain(memoryDir);
  
  switch (cmd) {
    case 'status':
      cmdStatus(terrain);
      break;
    case 'ssh':
      if (!args[1]) { console.error('Usage: numinous ssh <target>'); process.exit(1); }
      cmdSSH(terrain, args[1]);
      break;
    case 'context':
      if (!args[1]) { console.error('Usage: numinous context <agent>'); process.exit(1); }
      cmdContext(terrain, args[1]);
      break;
    case 'blockers':
      cmdBlockers(terrain);
      break;
    case 'query':
      if (!args[1]) { console.error('Usage: numinous query <name>'); process.exit(1); }
      cmdQuery(terrain, args.slice(1).join(' '));
      break;
    case 'json':
      console.log(JSON.stringify(terrain, null, 2));
      break;
    default:
      console.error(`Unknown command: ${cmd}`);
      process.exit(1);
  }
}

main();
