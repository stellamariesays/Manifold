/**
 * geometry.test.js — Unit tests for geometry math in geometry.js.
 *
 * geometry.js uses THREE.BufferGeometry which is not available in Node.
 * Strategy: mock THREE so the module loads, then verify the vertex arrays
 * that the functions produce contain the right data.
 *
 * The pure math is in the loops inside makeKleinBottleGeometry and
 * makeMobiusStripGeometry. We test by:
 *   1. Mocking THREE.BufferGeometry / Float32BufferAttribute to capture vertices
 *   2. Verifying vertex count, non-zero values, and scale sensitivity.
 */

import { vi, describe, test, expect, beforeAll } from 'vitest';

// ── Mock THREE before importing geometry.js ────────────────────────────────

class MockBufferGeometry {
  constructor() {
    this._attributes = {};
    this._index = null;
  }
  setAttribute(name, attr) { this._attributes[name] = attr; return this; }
  setIndex(idx) { this._index = idx; return this; }
  computeVertexNormals() {}
}

class MockFloat32BufferAttribute {
  constructor(array, itemSize) {
    this.array = array;
    this.itemSize = itemSize;
  }
}

vi.stubGlobal('THREE', {
  BufferGeometry: MockBufferGeometry,
  Float32BufferAttribute: MockFloat32BufferAttribute,
});

// Vitest resolves bare 'three' via the importmap, but in Node we need a mock.
vi.mock('three', () => ({
  BufferGeometry: MockBufferGeometry,
  Float32BufferAttribute: MockFloat32BufferAttribute,
}));

// Now import geometry functions
const { makeKleinBottleGeometry, makeMobiusStripGeometry } = await import('../../public/nexal/geometry.js');

// ── Helper ─────────────────────────────────────────────────────────────────

function getVertices(geo) {
  return geo._attributes.position.array;
}

// ── Klein Bottle ───────────────────────────────────────────────────────────

describe('makeKleinBottleGeometry', () => {
  test('returns an object (geometry-like)', () => {
    const geo = makeKleinBottleGeometry(1, 20);
    expect(geo).toBeTruthy();
    expect(typeof geo).toBe('object');
  });

  test('has a position attribute with a non-empty array', () => {
    const geo = makeKleinBottleGeometry(1, 20);
    const verts = getVertices(geo);
    expect(verts).toBeInstanceOf(Array);
    expect(verts.length).toBeGreaterThan(0);
  });

  test('vertex count matches expected formula: (segments+1)^2 * 3', () => {
    const segments = 16;
    const geo = makeKleinBottleGeometry(1, segments);
    const verts = getVertices(geo);
    // (uSteps+1) * (vSteps+1) vertices, each with 3 components
    expect(verts.length).toBe((segments + 1) * (segments + 1) * 3);
  });

  test('scale=2 produces vertices with larger magnitude than scale=1', () => {
    const geo1 = makeKleinBottleGeometry(1, 16);
    const geo2 = makeKleinBottleGeometry(2, 16);
    const verts1 = getVertices(geo1);
    const verts2 = getVertices(geo2);

    // Sum of absolute values should be larger with scale=2
    const sum1 = verts1.reduce((s, v) => s + Math.abs(v), 0);
    const sum2 = verts2.reduce((s, v) => s + Math.abs(v), 0);
    expect(sum2).toBeGreaterThan(sum1);
  });

  test('has index data set', () => {
    const geo = makeKleinBottleGeometry(1, 16);
    expect(geo._index).not.toBeNull();
    expect(geo._index.length).toBeGreaterThan(0);
  });

  test('vertices are finite numbers (no NaN/Inf)', () => {
    const geo = makeKleinBottleGeometry(1, 20);
    const verts = getVertices(geo);
    for (const v of verts) {
      expect(isFinite(v)).toBe(true);
    }
  });
});

// ── Möbius Strip ───────────────────────────────────────────────────────────

describe('makeMobiusStripGeometry', () => {
  test('returns an object (geometry-like)', () => {
    const geo = makeMobiusStripGeometry(1, 0.5, 32);
    expect(geo).toBeTruthy();
    expect(typeof geo).toBe('object');
  });

  test('has a position attribute with a non-empty array', () => {
    const geo = makeMobiusStripGeometry(1, 0.5, 32);
    const verts = getVertices(geo);
    expect(verts).toBeInstanceOf(Array);
    expect(verts.length).toBeGreaterThan(0);
  });

  test('vertex count matches expected formula: (segments+1) * 9 * 3', () => {
    const segments = 32;
    const geo = makeMobiusStripGeometry(1, 0.5, segments);
    const verts = getVertices(geo);
    // uSteps=segments, vSteps=8; (uSteps+1)*(vSteps+1)*3
    expect(verts.length).toBe((segments + 1) * (8 + 1) * 3);
  });

  test('larger radius produces vertices with larger magnitude', () => {
    const geoSmall = makeMobiusStripGeometry(1, 0.5, 32);
    const geoLarge = makeMobiusStripGeometry(3, 0.5, 32);
    const vertsSmall = getVertices(geoSmall);
    const vertsLarge = getVertices(geoLarge);
    const sumSmall = vertsSmall.reduce((s, v) => s + Math.abs(v), 0);
    const sumLarge = vertsLarge.reduce((s, v) => s + Math.abs(v), 0);
    expect(sumLarge).toBeGreaterThan(sumSmall);
  });

  test('different width params produce different vertex arrays', () => {
    const geoNarrow = makeMobiusStripGeometry(1, 0.1, 32);
    const geoWide   = makeMobiusStripGeometry(1, 1.0, 32);
    const vNarrow = getVertices(geoNarrow);
    const vWide   = getVertices(geoWide);
    // They should differ at some index
    const differ = vNarrow.some((v, i) => Math.abs(v - vWide[i]) > 1e-9);
    expect(differ).toBe(true);
  });

  test('vertices are finite numbers (no NaN/Inf)', () => {
    const geo = makeMobiusStripGeometry(1, 0.5, 32);
    const verts = getVertices(geo);
    for (const v of verts) {
      expect(isFinite(v)).toBe(true);
    }
  });

  test('has index data set', () => {
    const geo = makeMobiusStripGeometry(1, 0.5, 32);
    expect(geo._index).not.toBeNull();
    expect(geo._index.length).toBeGreaterThan(0);
  });
});
