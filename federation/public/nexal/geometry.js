/**
 * geometry.js — Topological geometry factories.
 * Exports: makeKleinBottleGeometry, makeMobiusStripGeometry
 */
import * as THREE from 'three';

export function makeKleinBottleGeometry(scale = 1, segments = 32) {
  const geometry = new THREE.BufferGeometry();
  const vertices = [];
  const indices = [];

  const uSteps = segments;
  const vSteps = segments;

  for (let i = 0; i <= uSteps; i++) {
    for (let j = 0; j <= vSteps; j++) {
      const u = (i / uSteps) * Math.PI * 2;
      const v = (j / vSteps) * Math.PI * 2;

      const a = 3, n = 2;
      const x = (a + Math.cos(u / 2) * Math.sin(v) - Math.sin(u / 2) * Math.sin(2 * v)) * Math.cos(u / n);
      const y = (a + Math.cos(u / 2) * Math.sin(v) - Math.sin(u / 2) * Math.sin(2 * v)) * Math.sin(u / n);
      const z = Math.sin(u / 2) * Math.sin(v) + Math.cos(u / 2) * Math.sin(2 * v);

      vertices.push(x * scale * 0.3, y * scale * 0.3, z * scale * 0.3);
    }
  }

  for (let i = 0; i < uSteps; i++) {
    for (let j = 0; j < vSteps; j++) {
      const a = i * (vSteps + 1) + j;
      const b = (i + 1) * (vSteps + 1) + j;
      const c = (i + 1) * (vSteps + 1) + j + 1;
      const d = i * (vSteps + 1) + j + 1;

      indices.push(a, b, d);
      indices.push(b, c, d);
    }
  }

  geometry.setAttribute('position', new THREE.Float32BufferAttribute(vertices, 3));
  geometry.setIndex(indices);
  geometry.computeVertexNormals();

  return geometry;
}

export function makeMobiusStripGeometry(radius = 1, width = 0.5, segments = 64) {
  const geometry = new THREE.BufferGeometry();
  const vertices = [];
  const indices = [];

  const uSteps = segments;
  const vSteps = 8;

  for (let i = 0; i <= uSteps; i++) {
    for (let j = 0; j <= vSteps; j++) {
      const u = (i / uSteps) * Math.PI * 2;
      const v = ((j / vSteps) - 0.5) * width;

      const x = (radius + v * Math.cos(u / 2)) * Math.cos(u);
      const y = (radius + v * Math.cos(u / 2)) * Math.sin(u);
      const z = v * Math.sin(u / 2);

      vertices.push(x, y, z);
    }
  }

  for (let i = 0; i < uSteps; i++) {
    for (let j = 0; j < vSteps; j++) {
      const a = i * (vSteps + 1) + j;
      const b = (i + 1) * (vSteps + 1) + j;
      const c = (i + 1) * (vSteps + 1) + j + 1;
      const d = i * (vSteps + 1) + j + 1;

      indices.push(a, b, d);
      indices.push(b, c, d);
    }
  }

  geometry.setAttribute('position', new THREE.Float32BufferAttribute(vertices, 3));
  geometry.setIndex(indices);
  geometry.computeVertexNormals();

  return geometry;
}
