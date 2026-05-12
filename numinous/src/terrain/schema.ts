/**
 * Terrain Schema — Pure type definitions for the Manifold mesh terrain.
 * 
 * These types define the shape of shared memory. All data flowing through
 * Numinous must conform to these types. No escape hatches, no `any`.
 * 
 * This is the contract. If it doesn't type-check, it doesn't exist.
 */

// ─── Primitives ───────────────────────────────────────────

/** Tailscale IP (100.x.x.x) or local network IP */
export type IPAddress = string & { readonly __brand: unique symbol };

/** SSH key identifier */
export type SSHKeyRef = string & { readonly __brand: unique symbol };

/** Tailscale hostname */
export type Hostname = string & { readonly __brand: unique symbol };

/** Agent name */
export type AgentName = string & { readonly __brand: unique symbol };

// ─── Machine ──────────────────────────────────────────────

export type MachineStatus = 'live' | 'offline' | 'unknown';

export interface Machine {
  readonly name: string;
  readonly role: string;
  readonly status: MachineStatus;
  readonly tailscaleIP: string;
  readonly localIP?: string;
  readonly sshUser: string;
  readonly sshKey: string;
  readonly sshKeyFrom?: string;  // which machine holds the key
  readonly arch?: string;
  readonly os?: string;
  readonly operator?: string;
  readonly notes?: string;
}

// ─── Agent ────────────────────────────────────────────────

export type AgentStatus = 'active' | 'parked' | 'offline' | 'unknown';

export interface AgentCapability {
  readonly name: string;
  readonly verified?: boolean;
}

export interface Agent {
  readonly name: string;
  readonly hub: string;
  readonly focus: string;
  readonly capabilities: readonly AgentCapability[];
  readonly status: AgentStatus;
  readonly runner: boolean;
  readonly script?: string;
  readonly cron?: string;
  readonly claimDomains?: readonly string[];
}

// ─── Federation ───────────────────────────────────────────

export interface FederationState {
  readonly hub: string;
  readonly agentCount: number;
  readonly registeredRunners: readonly string[];
  readonly peers: readonly Peer[];
}

export interface Peer {
  readonly name: string;
  readonly ip: string;
  readonly operator?: string;
  readonly agentCount?: number;
  readonly status: 'connected' | 'offline' | 'unknown';
}

// ─── Project ──────────────────────────────────────────────

export type ProjectStatus = 'active' | 'in_progress' | 'dormant' | 'parked';

export interface Project {
  readonly name: string;
  readonly status: ProjectStatus;
  readonly description?: string;
  readonly phase?: number;
  readonly repo?: string;
  readonly blockers?: readonly string[];
  readonly nextSteps?: readonly string[];
  readonly keyFiles?: Readonly<Record<string, string>>;
}

// ─── Terrain (the whole state) ────────────────────────────

export interface Terrain {
  readonly generated: string;      // ISO timestamp
  readonly updated?: string;       // last update timestamp
  readonly machines: Readonly<Record<string, Machine>>;
  readonly federation: FederationState;
  readonly agents: Readonly<Record<string, Agent>>;
  readonly projects: Readonly<Record<string, Project>>;
  readonly decisions: readonly Decision[];
}

export interface Decision {
  readonly timestamp: string;
  readonly summary: string;
  readonly context?: string;
  readonly decidedBy: string;
}

// ─── Terrain Delta (change event) ─────────────────────────

export type ChangeOp = 'add' | 'update' | 'remove';

export interface TerrainChange {
  readonly op: ChangeOp;
  readonly path: string;          // e.g. "machines.thefog.sshKey"
  readonly from?: unknown;
  readonly to: unknown;
  readonly timestamp: string;
  readonly author: string;
  readonly reason?: string;
}

export interface TerrainPatch {
  readonly baseTimestamp: string;
  readonly changes: readonly TerrainChange[];
  readonly author: string;
}
