/**
 * boundary.test.js — Static analysis: enforce the 3D/2D layer boundary.
 *
 * These tests READ the source files and check import statements.
 * No runtime execution of Three.js code needed.
 *
 * Rules enforced:
 *   3D layer (scene.js, animation.js, geometry.js):
 *     - Must NOT import from ui.js
 *     - Must NOT import from each other across the boundary
 *   2D layer (ui.js):
 *     - Must NOT import from scene.js, animation.js, geometry.js, or 'three'
 *   bridge.js:
 *     - Must NOT import from scene.js, animation.js, ui.js (neutral bus)
 *   data.js:
 *     - Must NOT import from scene.js, animation.js, geometry.js, or 'three'
 *     - Only cross-layer dep allowed: bridge.js
 */

import { readFileSync } from 'fs';
import { resolve, dirname } from 'path';
import { fileURLToPath } from 'url';
import { describe, test, expect } from 'vitest';

const __dirname = dirname(fileURLToPath(import.meta.url));
const UI_DIR = resolve(__dirname, '../../public/nexal');

function readFile(name) {
  return readFileSync(resolve(UI_DIR, name), 'utf8');
}

/**
 * Extract all static import source strings from an ES module source.
 * Handles:
 *   import ... from 'specifier'
 *   import 'specifier'
 */
function getImports(source) {
  const importRe = /^\s*import\s+(?:[\s\S]*?from\s+)?['"]([^'"]+)['"]/gm;
  const imports = [];
  let match;
  while ((match = importRe.exec(source)) !== null) {
    imports.push(match[1]);
  }
  return imports;
}

// ── scene.js ───────────────────────────────────────────────────────────────

describe('scene.js — 3D layer boundary', () => {
  const source = readFile('scene.js');
  const imports = getImports(source);

  test('does NOT import from ui.js', () => {
    const violation = imports.find(i => i.includes('ui.js') || i === './ui');
    expect(violation).toBeUndefined();
  });

  test('does NOT import from animation.js', () => {
    const violation = imports.find(i => i.includes('animation.js') || i === './animation');
    expect(violation).toBeUndefined();
  });

  test('does import from geometry.js (expected 3D-3D dep)', () => {
    const hasGeo = imports.some(i => i.includes('geometry'));
    expect(hasGeo).toBe(true);
  });

  test('does import from bridge.js (allowed cross-layer channel)', () => {
    const hasBridge = imports.some(i => i.includes('bridge'));
    expect(hasBridge).toBe(true);
  });
});

// ── animation.js ───────────────────────────────────────────────────────────

describe('animation.js — 3D layer boundary', () => {
  const source = readFile('animation.js');
  const imports = getImports(source);

  test('does NOT import from ui.js', () => {
    const violation = imports.find(i => i.includes('ui.js') || i === './ui');
    expect(violation).toBeUndefined();
  });

  test('does NOT import from data.js', () => {
    const violation = imports.find(i => i.includes('data.js') || i === './data');
    expect(violation).toBeUndefined();
  });

  test('does import from scene.js (expected 3D-3D dep)', () => {
    const hasScene = imports.some(i => i.includes('scene'));
    expect(hasScene).toBe(true);
  });
});

// ── geometry.js ────────────────────────────────────────────────────────────

describe('geometry.js — 3D layer boundary', () => {
  const source = readFile('geometry.js');
  const imports = getImports(source);

  test('does NOT import from ui.js', () => {
    const violation = imports.find(i => i.includes('ui.js') || i === './ui');
    expect(violation).toBeUndefined();
  });

  test('does NOT import from scene.js', () => {
    const violation = imports.find(i => i.includes('scene.js') || i === './scene');
    expect(violation).toBeUndefined();
  });

  test('does NOT import from animation.js', () => {
    const violation = imports.find(i => i.includes('animation.js') || i === './animation');
    expect(violation).toBeUndefined();
  });

  test('does NOT import from bridge.js (geometry is pure math)', () => {
    const violation = imports.find(i => i.includes('bridge'));
    expect(violation).toBeUndefined();
  });
});

// ── ui.js ──────────────────────────────────────────────────────────────────

describe('ui.js — 2D layer boundary', () => {
  const source = readFile('ui.js');
  const imports = getImports(source);

  test('does NOT import from scene.js', () => {
    const violation = imports.find(i => i.includes('scene.js') || i === './scene');
    expect(violation).toBeUndefined();
  });

  test('does NOT import from animation.js', () => {
    const violation = imports.find(i => i.includes('animation.js') || i === './animation');
    expect(violation).toBeUndefined();
  });

  test('does NOT import from geometry.js', () => {
    const violation = imports.find(i => i.includes('geometry.js') || i === './geometry');
    expect(violation).toBeUndefined();
  });

  test('does NOT import from three / THREE', () => {
    const violation = imports.find(i => i === 'three' || i.includes('three@') || i.toLowerCase().includes('/three.module'));
    expect(violation).toBeUndefined();
  });
});

// ── bridge.js ─────────────────────────────────────────────────────────────

describe('bridge.js — must be neutral (no layer imports)', () => {
  const source = readFile('bridge.js');
  const imports = getImports(source);

  test('does NOT import from scene.js', () => {
    const violation = imports.find(i => i.includes('scene'));
    expect(violation).toBeUndefined();
  });

  test('does NOT import from animation.js', () => {
    const violation = imports.find(i => i.includes('animation'));
    expect(violation).toBeUndefined();
  });

  test('does NOT import from ui.js', () => {
    const violation = imports.find(i => i.includes('ui'));
    expect(violation).toBeUndefined();
  });

  test('does NOT import from geometry.js', () => {
    const violation = imports.find(i => i.includes('geometry'));
    expect(violation).toBeUndefined();
  });

  test('does NOT import from three', () => {
    const violation = imports.find(i => i === 'three' || i.includes('three@'));
    expect(violation).toBeUndefined();
  });

  test('has zero imports total (pure event bus)', () => {
    expect(imports).toHaveLength(0);
  });
});

// ── data.js ────────────────────────────────────────────────────────────────

describe('data.js — neutral layer boundary', () => {
  const source = readFile('data.js');
  const imports = getImports(source);

  test('does NOT import from scene.js', () => {
    const violation = imports.find(i => i.includes('scene'));
    expect(violation).toBeUndefined();
  });

  test('does NOT import from animation.js', () => {
    const violation = imports.find(i => i.includes('animation'));
    expect(violation).toBeUndefined();
  });

  test('does NOT import from geometry.js', () => {
    const violation = imports.find(i => i.includes('geometry'));
    expect(violation).toBeUndefined();
  });

  test('does NOT import from ui.js', () => {
    const violation = imports.find(i => i.includes('ui.js') || i === './ui');
    expect(violation).toBeUndefined();
  });

  test('does NOT import three directly', () => {
    const violation = imports.find(i => i === 'three' || i.includes('three@'));
    expect(violation).toBeUndefined();
  });

  test('imports bridge.js (the only allowed cross-layer channel)', () => {
    const hasBridge = imports.some(i => i.includes('bridge'));
    expect(hasBridge).toBe(true);
  });
});

// ── nexal.js — orchestrator may import both layers ─────────────────────────

describe('nexal.js — allowed to import both layers via bridge', () => {
  const source = readFile('nexal.js');
  const imports = getImports(source);

  test('imports bridge.js', () => {
    expect(imports.some(i => i.includes('bridge'))).toBe(true);
  });

  test('imports scene.js', () => {
    expect(imports.some(i => i.includes('scene'))).toBe(true);
  });

  test('imports ui.js', () => {
    expect(imports.some(i => i.includes('ui'))).toBe(true);
  });

  test('imports animation.js', () => {
    expect(imports.some(i => i.includes('animation'))).toBe(true);
  });
});
