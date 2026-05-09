/**
 * Query — Pure composable query functions over Terrain.
 * 
 * Every function here is pure: (terrain) → result.
 * No IO, no mutation, no side effects.
 * Compose these to build any question about the mesh.
 */

import type {
  Terrain,
  Machine,
  Agent,
  Project,
  Decision,
} from './schema.js';

// ─── Machine Queries ──────────────────────────────────────

export const getMachine = (name: string) => (terrain: Terrain): Machine | null =>
  terrain.machines[name.toLowerCase()] ?? null;

export const getMachineByIP = (ip: string) => (terrain: Terrain): Machine | null =>
  Object.values(terrain.machines).find(
    m => m.tailscaleIP === ip || m.localIP === ip
  ) ?? null;

export const getSSHCommand = (target: string) => (terrain: Terrain): string | null => {
  const machine = getMachine(target)(terrain);
  if (!machine || !machine.tailscaleIP) return null;
  
  const keyFlag = machine.sshKey ? `-i ${machine.sshKey}` : '';
  const host = machine.localIP || machine.tailscaleIP;
  return `ssh ${keyFlag} ${machine.sshUser}@${host}`.trim();
};

export const getLiveMachines = (terrain: Terrain): readonly Machine[] =>
  Object.values(terrain.machines).filter(m => m.status === 'live');

export const getMachineOperator = (name: string) => (terrain: Terrain): string | null =>
  terrain.machines[name.toLowerCase()]?.operator ?? null;

// ─── Agent Queries ────────────────────────────────────────

export const getAgent = (name: string) => (terrain: Terrain): Agent | null =>
  terrain.agents[name] ?? null;

export const getAgentsByHub = (hub: string) => (terrain: Terrain): readonly Agent[] =>
  Object.values(terrain.agents).filter(a => a.hub === hub);

export const getRunners = (terrain: Terrain): readonly Agent[] =>
  Object.values(terrain.agents).filter(a => a.runner);

export const getAgentsByCapability = (cap: string) => (terrain: Terrain): readonly Agent[] =>
  Object.values(terrain.agents).filter(a =>
    a.capabilities.some(c => c.name === cap)
  );

export const getAgentsByStatus = (status: Agent['status']) => (terrain: Terrain): readonly Agent[] =>
  Object.values(terrain.agents).filter(a => a.status === status);

export const getAgentCount = (terrain: Terrain): number =>
  Object.keys(terrain.agents).length;

// ─── Project Queries ──────────────────────────────────────

export const getProject = (name: string) => (terrain: Terrain): Project | null =>
  terrain.projects[name] ?? null;

export const getActiveProjects = (terrain: Terrain): readonly Project[] =>
  Object.values(terrain.projects).filter(p => p.status === 'active' || p.status === 'in_progress');

export const getBlockedProjects = (terrain: Terrain): readonly (Project & { blockers: readonly string[] })[] =>
  Object.values(terrain.projects)
    .filter((p): p is Project & { blockers: readonly string[] } =>
      p.status === 'active' && (p.blockers?.length ?? 0) > 0
    );

// ─── Decision Queries ─────────────────────────────────────

export const getRecentDecisions = (count: number) => (terrain: Terrain): readonly Decision[] =>
  terrain.decisions.slice(-count);

export const getDecisionsByAuthor = (author: string) => (terrain: Terrain): readonly Decision[] =>
  terrain.decisions.filter(d => d.decidedBy === author);

// ─── Federation Queries ───────────────────────────────────

export const getMeshSummary = (terrain: Terrain): {
  hubs: number;
  agents: number;
  runners: number;
  liveMachines: number;
  projects: number;
} => ({
  hubs: terrain.federation.hub ? 1 : 0,
  agents: terrain.federation.agentCount,
  runners: terrain.federation.registeredRunners.length,
  liveMachines: getLiveMachines(terrain).length,
  projects: Object.keys(terrain.projects).length,
});

export const findWhoOwns = (agentName: string) => (terrain: Terrain): {
  agent: Agent;
  machine: Machine | null;
} | null => {
  const agent = getAgent(agentName)(terrain);
  if (!agent) return null;
  
  const machine = Object.values(terrain.machines).find(
    m => m.name.toLowerCase() === agent.hub.toLowerCase()
  ) ?? null;
  
  return { agent, machine };
};

// ─── Cross-cutting Queries ────────────────────────────────

/** What's everything I need to know before SSH'ing somewhere? */
export const getSSHContext = (target: string) => (terrain: Terrain): {
  command: string | null;
  machine: Machine | null;
  agentsOnMachine: readonly Agent[];
  keyFrom: Machine | null;
} => {
  const machine = getMachine(target)(terrain);
  const command = getSSHCommand(target)(terrain);
  const agentsOnMachine = machine
    ? Object.values(terrain.agents).filter(a => a.hub.toLowerCase() === machine.name.toLowerCase())
    : [];
  const keyFrom = machine?.sshKeyFrom
    ? getMachine(machine.sshKeyFrom)(terrain)
    : null;
  
  return { command, machine, agentsOnMachine, keyFrom };
};

/** What's broken or blocked right now? */
export const getBlockers = (terrain: Terrain): readonly {
  project: string;
  blockers: readonly string[];
}[] =>
  Object.values(terrain.projects)
    .filter(p => (p.blockers?.length ?? 0) > 0)
    .map(p => ({ project: p.name, blockers: p.blockers! }));

/** What's the full context for a given agent name? */
export const getAgentContext = (name: string) => (terrain: Terrain): {
  agent: Agent | null;
  machine: Machine | null;
  sshCommand: string | null;
  coAgents: readonly Agent[];
} => {
  const agent = getAgent(name)(terrain);
  if (!agent) return { agent: null, machine: null, sshCommand: null, coAgents: [] };
  
  const machine = Object.values(terrain.machines).find(
    m => m.name.toLowerCase() === agent.hub.toLowerCase()
  ) ?? null;
  
  const sshCommand = machine ? getSSHCommand(machine.name)(terrain) : null;
  
  const coAgents = Object.values(terrain.agents).filter(
    a => a.hub === agent.hub && a.name !== agent.name
  );
  
  return { agent, machine, sshCommand, coAgents };
};
