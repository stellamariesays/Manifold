/**
 * Terrain Loader — Pure functions for loading terrain from disk.
 * 
 * Reads existing JSON/markdown files and parses them into typed Terrain.
 * All functions are pure: same input → same output, no side effects except IO.
 */

import * as fs from 'fs';
import * as path from 'path';
import type {
  Terrain,
  Machine,
  Agent,
  FederationState,
  Peer,
  Project,
  Decision,
} from './schema.js';

// ─── Types for raw parsed data (before validation) ───────

interface RawTerrainDelta {
  machines?: Record<string, Partial<Machine>>;
  federation?: Partial<FederationState>;
}

// ─── Pure Parsing Functions ───────────────────────────────

/** Parse the markdown terrain-delta into structured data */
export function parseTerrainMarkdown(md: string): RawTerrainDelta {
  const result: RawTerrainDelta = {};
  const machines: Record<string, Partial<Machine>> = {};
  
  const machinePattern = /\*\*(\w+[\w\s]*?):\*\s*(.*?)(?=\n\n\*\*|\n\n##|$)/gs;
  let match: RegExpExecArray | null;
  
  while ((match = machinePattern.exec(md)) !== null) {
    const rawName = match[1].trim();
    const body = match[2];
    
    const lower = rawName.toLowerCase();
    if (lower === 'generated' || lower === 'updated' || lower === 'hub:' || lower === 'status:' || lower === 'agents on mesh:') continue;
    
    // Strip parenthetical like (HOG)
    const name = rawName.replace(/\s*\(.*?\)\s*/g, '').toLowerCase().replace(/\s+/g, '');
    
    const m: Record<string, unknown> = {
      name,
      role: '',
      status: 'unknown',
      tailscaleIP: '',
      sshUser: '',
      sshKey: '',
    };
    
    const tsIp = body.match(/Tailscale IP:\s*`?([\d.]+)`?/);
    if (tsIp) m.tailscaleIP = tsIp[1];
    
    const localIp = body.match(/Local IP:\s*`?([\d.]+)`?/);
    if (localIp) m.localIP = localIp[1];
    
    const sshUser = body.match(/SSH user:\s*`?(\w+)`?/);
    if (sshUser) m.sshUser = sshUser[1];
    
    const sshKey = body.match(/SSH key:?\s*`?([^`\n]+)`?/);
    if (sshKey) m.sshKey = sshKey[1].trim();
    
    const role = body.match(/Role:\s*(.+?)(?:\n|$)/);
    if (role) m.role = role[1].trim();
    
    const status = body.match(/Status:\s*(\w+)/i);
    if (status) m.status = status[1].toLowerCase();
    
    const osMatch = body.match(/OS:\s*(.+?)[,.]|\sLinux\s(\w+)/);
    if (osMatch) m.os = osMatch[1] || osMatch[2];
    
    machines[name] = m as unknown as Partial<Machine>;
  }
  
  if (Object.keys(machines).length > 0) {
    result.machines = machines;
  }
  
  return result;
}

/** Load and parse a JSON file */
export function loadJSON<T>(filePath: string): T | null {
  try {
    const raw = fs.readFileSync(filePath, 'utf-8');
    return JSON.parse(raw) as T;
  } catch {
    return null;
  }
}

/** Load decisions from JSONL file */
export function loadDecisions(filePath: string): Decision[] {
  try {
    const raw = fs.readFileSync(filePath, 'utf-8');
    return raw
      .split('\n')
      .filter(line => line.trim())
      .map(line => {
        try { return JSON.parse(line) as Decision; }
        catch { return null; }
      })
      .filter((d): d is Decision => d !== null);
  } catch {
    return [];
  }
}

/** Coerce string status to Peer status */
function asPeerStatus(s: string | undefined): Peer['status'] {
  if (s === 'connected') return 'connected';
  if (s === 'offline') return 'offline';
  return 'unknown';
}

/** Load the full terrain from the Manifold memory directory */
export function loadTerrain(memoryDir: string): Terrain {
  // Load terrain-delta.md
  const terrainPath = path.join(memoryDir, 'terrain-delta.md');
  let terrainMd = '';
  try {
    terrainMd = fs.readFileSync(terrainPath, 'utf-8');
  } catch { /* no terrain file */ }
  
  // Load structured JSON indices
  const systemIndex = loadJSON<{
    host?: { name: string; tailscale_ip: string; user: string };
    peers?: Record<string, { ip: string; operator?: string; status?: string; agents?: number }>;
    ports?: Record<string, number>;
  }>(path.join(memoryDir, 'index', 'system.json'));
  
  const agentsIndex = loadJSON<{
    agents?: Array<{
      name: string;
      hub: string;
      focus: string;
      capabilities?: string[] | number;
      status: string;
      runner: boolean;
      script?: string;
      cron?: string;
      claim_domains?: string[];
    }>;
  }>(path.join(memoryDir, 'index', 'agents.json'));
  
  const projectsIndex = loadJSON<{
    projects?: Array<{
      name: string;
      status: string;
      description?: string;
      phase?: number;
      repo?: string;
      blockers?: string[];
      next_steps?: string[];
      key_files?: Record<string, string>;
    }>;
  }>(path.join(memoryDir, 'index', 'projects.json'));
  
  const decisions = loadDecisions(path.join(memoryDir, 'index', 'decisions.jsonl'));
  
  // Parse terrain markdown
  const parsed = parseTerrainMarkdown(terrainMd);
  
  // Build machines from terrain-delta + system index
  const machines: Record<string, Machine> = {};
  
  if (parsed.machines) {
    for (const [key, partial] of Object.entries(parsed.machines)) {
      machines[key] = {
        name: partial.name || key,
        role: partial.role || '',
        status: partial.status || 'unknown',
        tailscaleIP: partial.tailscaleIP || '',
        localIP: partial.localIP,
        sshUser: partial.sshUser || '',
        sshKey: partial.sshKey || '',
        sshKeyFrom: partial.sshKeyFrom,
        arch: partial.arch,
        os: partial.os,
        operator: partial.operator,
        notes: partial.notes,
      };
    }
  }
  
  // Augment with system index peers
  if (systemIndex?.peers) {
    for (const [name, peer] of Object.entries(systemIndex.peers)) {
      const key = name.toLowerCase();
      if (!machines[key]) {
        machines[key] = {
          name,
          role: 'peer',
          status: (asPeerStatus(peer.status) === 'connected' ? 'live' : asPeerStatus(peer.status)) as Machine['status'],
          tailscaleIP: peer.ip,
          sshUser: '',
          sshKey: '',
          operator: peer.operator,
          notes: `${peer.agents ?? 0} agents`,
        };
      }
    }
  }
  
  // Build agents
  const agents: Record<string, Agent> = {};
  if (agentsIndex?.agents) {
    for (const a of agentsIndex.agents) {
      agents[a.name] = {
        name: a.name,
        hub: a.hub,
        focus: a.focus,
        capabilities: Array.isArray(a.capabilities)
          ? a.capabilities.map(c => ({ name: c }))
          : [],
        status: (a.status as Agent['status']) || 'unknown',
        runner: a.runner,
        script: a.script,
        cron: a.cron,
        claimDomains: a.claim_domains,
      };
    }
  }
  
  // Build projects
  const projects: Record<string, Project> = {};
  if (projectsIndex?.projects) {
    for (const p of projectsIndex.projects) {
      projects[p.name] = {
        name: p.name,
        status: (p.status as Project['status']) || 'unknown',
        description: p.description,
        phase: p.phase,
        repo: p.repo,
        blockers: p.blockers,
        nextSteps: p.next_steps,
        keyFiles: p.key_files,
      };
    }
  }
  
  // Build federation
  const federation: FederationState = {
    hub: 'satelitea',
    agentCount: agentsIndex?.agents?.length ?? 0,
    registeredRunners: agentsIndex?.agents?.filter(a => a.runner).map(a => a.name) ?? [],
    peers: systemIndex?.peers
      ? Object.entries(systemIndex.peers).map(([name, p]) => ({
          name,
          ip: p.ip,
          operator: p.operator,
          agentCount: p.agents,
          status: asPeerStatus(p.status),
        }))
      : [],
  };
  
  // Extract generated timestamp from terrain markdown
  const tsMatch = terrainMd.match(/\*\*Generated:\*\*\s*(.+?)(?:\n|$)/);
  const updatedMatch = terrainMd.match(/\*\*Updated:\*\*\s*(.+?)(?:\n|$)/);
  
  return {
    generated: tsMatch?.[1]?.trim() || new Date().toISOString(),
    updated: updatedMatch?.[1]?.trim(),
    machines,
    federation,
    agents,
    projects,
    decisions,
  };
}
