/**
 * Which per-mesh step in `GltfMesh` costs the time.
 *
 * For every mesh the viewer runs mergeVertices, toCreasedNormals and EdgesGeometry on the main
 * thread. On a 12-part assembly that is 180k triangles spread over 12 meshes, and the pane sits
 * on its loading placeholder while it happens. This measures the three against synthetic
 * geometry of the same order so the optimisation targets the one that actually dominates.
 *
 * Not a correctness test and not part of the suite's guarantees -- it prints numbers. Kept
 * because the next person to ask "why is 3D slow" should not have to rebuild it.
 */
import * as THREE from "three";
import * as BufferGeometryUtils from "three/examples/jsm/utils/BufferGeometryUtils.js";
import { describe, it } from "vitest";

/** A sphere is the fair stand-in: curved, so creasing and edge extraction both do real work. */
function geometryWithTriangles(target: number): THREE.BufferGeometry {
  let seg = 8;
  while (seg * seg * 2 < target && seg < 4096) seg += 8;
  return new THREE.SphereGeometry(1, seg, seg / 2).toNonIndexed();
}

const time = (label: string, fn: () => void) => {
  const t0 = performance.now();
  fn();
  return { label, ms: performance.now() - t0 };
};

describe("per-mesh cost in GltfMesh", () => {
  it("reports where the load time goes", () => {
    for (const target of [15_000, 60_000, 180_000]) {
      const base = geometryWithTriangles(target);
      const tris = base.attributes.position.count / 3;

      let merged: THREE.BufferGeometry = base;
      const rows = [
        time("mergeVertices", () => {
          merged = BufferGeometryUtils.mergeVertices(base);
        }),
        time("toCreasedNormals", () => {
          BufferGeometryUtils.toCreasedNormals(merged, THREE.MathUtils.degToRad(35));
        }),
        time("EdgesGeometry(28)", () => {
          new THREE.EdgesGeometry(merged, 28);
        }),
      ];
      const total = rows.reduce((a, r) => a + r.ms, 0);
      const parts = rows
        .map((r) => `${r.label} ${r.ms.toFixed(0)}ms (${((100 * r.ms) / total).toFixed(0)}%)`)
        .join("   ");
      // eslint-disable-next-line no-console
      console.log(`\n~${Math.round(tris).toLocaleString()} triangles -> ${total.toFixed(0)}ms total\n   ${parts}`);
    }
  });
});
