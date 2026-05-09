/**
 * Transform — Pure functions for transforming Terrain.
 * 
 * Every function returns a NEW Terrain. The original is never modified.
 * Changes are tracked as TerrainChange records for audit trail.
 */

import type {
  Terrain,
  Machine,
  Agent,
  Project,
  Decision,
  TerrainChange,
} from './schema.js';

// ─── Helper: create a change record ──────────────────────

const now = (): string => new Date().toISOString();

function change(
  op: TerrainChange['op'],
  path: string,
  to: unknown,
  author: string,
  from?: unknown,
  reason?: string,
): TerrainChange {
  return {
    op,
    path,
    from,
    to,
    timestamp: now(),
    author,
    reason,
  };
}

/** Safely read a field from a readonly object */
function getField(obj: object, field: string): unknown {
  return (obj as Record<string, unknown>)[field];
}

// ─── Machine Transforms ───────────────────────────────────

export const addMachine = (machine: Machine, author: string) =>
  (terrain: Terrain): { terrain: Terrain; changes: readonly TerrainChange[] } => {
    const key = machine.name.toLowerCase();
    if (terrain.machines[key]) {
      throw new Error(`Machine ${machine.name} already exists. Use updateMachine.`);
    }
    
    return {
      terrain: {
        ...terrain,
        updated: now(),
        machines: {
          ...terrain.machines,
          [key]: machine,
        },
      },
      changes: [
        change('add', `machines.${key}`, machine, author),
      ],
    };
  };

export const updateMachine = (name: string, patch: Partial<Machine>, author: string, reason?: string) =>
  (terrain: Terrain): { terrain: Terrain; changes: readonly TerrainChange[] } => {
    const key = name.toLowerCase();
    const existing = terrain.machines[key];
    if (!existing) {
      throw new Error(`Machine ${name} not found. Use addMachine.`);
    }
    
    const updated: Machine = { ...existing, ...patch };
    
    const changes: TerrainChange[] = [];
    for (const field of Object.keys(patch)) {
      const oldVal = getField(existing, field);
      const newVal = getField(updated, field);
      if (oldVal !== newVal) {
        changes.push(change('update', `machines.${key}.${field}`, newVal, author, oldVal, reason));
      }
    }
    
    return {
      terrain: {
        ...terrain,
        updated: now(),
        machines: {
          ...terrain.machines,
          [key]: updated,
        },
      },
      changes,
    };
  };

export const removeMachine = (name: string, author: string, reason?: string) =>
  (terrain: Terrain): { terrain: Terrain; changes: readonly TerrainChange[] } => {
    const key = name.toLowerCase();
    const existing = terrain.machines[key];
    if (!existing) {
      throw new Error(`Machine ${name} not found.`);
    }
    
    const { [key]: _, ...rest } = terrain.machines;
    
    return {
      terrain: {
        ...terrain,
        updated: now(),
        machines: rest,
      },
      changes: [
        change('remove', `machines.${key}`, null, author, existing, reason),
      ],
    };
  };

// ─── Agent Transforms ─────────────────────────────────────

export const addAgent = (agent: Agent, author: string) =>
  (terrain: Terrain): { terrain: Terrain; changes: readonly TerrainChange[] } => {
    if (terrain.agents[agent.name]) {
      throw new Error(`Agent ${agent.name} already exists. Use updateAgent.`);
    }
    
    return {
      terrain: {
        ...terrain,
        updated: now(),
        agents: {
          ...terrain.agents,
          [agent.name]: agent,
        },
      },
      changes: [
        change('add', `agents.${agent.name}`, agent, author),
      ],
    };
  };

export const updateAgent = (name: string, patch: Partial<Agent>, author: string, reason?: string) =>
  (terrain: Terrain): { terrain: Terrain; changes: readonly TerrainChange[] } => {
    const existing = terrain.agents[name];
    if (!existing) {
      throw new Error(`Agent ${name} not found.`);
    }
    
    const updated: Agent = { ...existing, ...patch };
    
    const changes: TerrainChange[] = [];
    for (const field of Object.keys(patch)) {
      const oldVal = getField(existing, field);
      const newVal = getField(updated, field);
      if (oldVal !== newVal) {
        changes.push(change('update', `agents.${name}.${field}`, newVal, author, oldVal, reason));
      }
    }
    
    return {
      terrain: {
        ...terrain,
        updated: now(),
        agents: {
          ...terrain.agents,
          [name]: updated,
        },
      },
      changes,
    };
  };

// ─── Decision Transforms ──────────────────────────────────

export const addDecision = (decision: Decision, author: string) =>
  (terrain: Terrain): { terrain: Terrain; changes: readonly TerrainChange[] } => {
    return {
      terrain: {
        ...terrain,
        updated: now(),
        decisions: [...terrain.decisions, decision],
      },
      changes: [
        change('add', `decisions[${terrain.decisions.length}]`, decision, author),
      ],
    };
  };

// ─── Project Transforms ───────────────────────────────────

export const addProject = (project: Project, author: string) =>
  (terrain: Terrain): { terrain: Terrain; changes: readonly TerrainChange[] } => {
    if (terrain.projects[project.name]) {
      throw new Error(`Project ${project.name} already exists.`);
    }
    
    return {
      terrain: {
        ...terrain,
        updated: now(),
        projects: {
          ...terrain.projects,
          [project.name]: project,
        },
      },
      changes: [
        change('add', `projects.${project.name}`, project, author),
      ],
    };
  };

// ─── Diff ─────────────────────────────────────────────────

/** Compare two terrains and produce changes */
export function diffTerrain(
  before: Terrain,
  after: Terrain,
  author: string,
): readonly TerrainChange[] {
  const changes: TerrainChange[] = [];
  
  for (const key of Object.keys(after.machines)) {
    if (!before.machines[key]) {
      changes.push(change('add', `machines.${key}`, after.machines[key], author));
    } else if (JSON.stringify(before.machines[key]) !== JSON.stringify(after.machines[key])) {
      for (const field of Object.keys(after.machines[key])) {
        const oldVal = getField(before.machines[key], field);
        const newVal = getField(after.machines[key], field);
        if (oldVal !== newVal) {
          changes.push(change('update', `machines.${key}.${field}`, newVal, author, oldVal));
        }
      }
    }
  }
  
  for (const key of Object.keys(before.machines)) {
    if (!after.machines[key]) {
      changes.push(change('remove', `machines.${key}`, null, author, before.machines[key]));
    }
  }
  
  return changes;
}
