import React, { useEffect, useRef, useState } from 'react';
import { useThemeStore } from '../../stores/themeStore';
import { useConnectionStore } from '../../stores/connectionStore';
import { Canvas, useThree, useFrame } from '@react-three/fiber';
import {
  OrbitControls,
  OrthographicCamera,
} from '@react-three/drei';
import * as THREE from 'three';
import { GLTFLoader, type GLTF } from 'three/examples/jsm/loaders/GLTFLoader.js';
import * as BufferGeometryUtils from 'three/examples/jsm/utils/BufferGeometryUtils.js';
import { PartsPanel, type AssemblyPart } from './PartsPanel';
import { useReviewStore } from '../../stores/reviewStore';
import { Box } from 'lucide-react';
import { ViewCubeIcon } from './ViewCubeIcon';
import { CadTripodOverlay } from './CadTripodOverlay';

export type ViewPreset = 'se' | 'sw' | 'ne' | 'nw' | 'top' | 'front' | 'right' | 'left' | 'back' | 'bottom';

/**
 * Triangles above which the CAD edge outlines are skipped.
 *
 * `EdgesGeometry` measured 42% of the per-mesh load cost and is linear in triangles, so it
 * is what makes a large assembly freeze the pane. 120k is a little under the 12-part
 * assembly that prompted this (180k) and comfortably above every single-part model in the
 * corpus, the largest of which is 37k -- so nothing that renders quickly today loses them.
 */
const EDGE_OUTLINE_TRIANGLE_BUDGET = 120_000;

/** Stable reference, so the zustand selector does not return a new array every render. */
const EMPTY_HIDDEN: number[] = [];

interface ThreeDViewerProps {
  drawing: any;
  width: number;
  height: number;
}

// ── Camera controller for framing and standard CAD view presets ─────────────
interface CameraControllerProps {
  modelRef: React.RefObject<THREE.Group | null>;
  targetView: ViewPreset | null;
  width: number;
  height: number;
  onViewApplied?: () => void;
}

const CameraController = ({
  modelRef,
  targetView,
  width,
  height,
  onViewApplied,
}: CameraControllerProps) => {
  const { camera, controls } = useThree() as any;
  const metricsRef = useRef<{ center: THREE.Vector3; dist: number; maxDim: number } | null>(null);

  const applyView = (view: ViewPreset) => {
    if (!metricsRef.current || !camera) return;
    const { center, dist, maxDim } = metricsRef.current;

    const pos = new THREE.Vector3();
    const up = new THREE.Vector3(0, 1, 0);

    switch (view) {
      case 'sw': {
        const c = dist / Math.sqrt(3);
        pos.set(center.x + c, center.y + c, center.z + c);
        up.set(0, 1, 0);
        break;
      }
      case 'nw': {
        const c = dist / Math.sqrt(3);
        pos.set(center.x + c, center.y + c, center.z - c);
        up.set(0, 1, 0);
        break;
      }
      case 'ne': {
        const c = dist / Math.sqrt(3);
        pos.set(center.x - c, center.y + c, center.z - c);
        up.set(0, 1, 0);
        break;
      }
      case 'se': {
        const c = dist / Math.sqrt(3);
        pos.set(center.x - c, center.y + c, center.z + c);
        up.set(0, 1, 0);
        break;
      }
      case 'top':
        pos.set(center.x, center.y + dist, center.z);
        up.set(0, 0, -1);
        break;
      case 'front':
        pos.set(center.x, center.y, center.z + dist);
        up.set(0, 1, 0);
        break;
      case 'right':
        pos.set(center.x + dist, center.y, center.z);
        up.set(0, 1, 0);
        break;
      case 'left':
        pos.set(center.x - dist, center.y, center.z);
        up.set(0, 1, 0);
        break;
      case 'back':
        pos.set(center.x, center.y, center.z - dist);
        up.set(0, 1, 0);
        break;
      case 'bottom':
        pos.set(center.x, center.y - dist, center.z);
        up.set(0, 0, 1);
        break;
      default: {
        const c = dist / Math.sqrt(3);
        pos.set(center.x + c, center.y + c, center.z + c);
        up.set(0, 1, 0);
        break;
      }
    }

    camera.position.copy(pos);
    camera.up.copy(up);
    camera.lookAt(center);

    // True CAD Orthographic parallel projection: zero perspective distortion
    if (camera.isOrthographicCamera) {
      const padding = 0.75;
      camera.zoom = (Math.min(width, height) * padding) / maxDim;
      camera.near = -dist * 50;
      camera.far = dist * 50;
      camera.updateProjectionMatrix();
    }

    if (controls) {
      controls.target.copy(center);
      controls.update();
    }

    onViewApplied?.();
  };

  // Measure bounding box and apply initial framing
  useEffect(() => {
    if (!modelRef.current) return;

    const box = new THREE.Box3().setFromObject(modelRef.current);
    const size = box.getSize(new THREE.Vector3());
    const center = box.getCenter(new THREE.Vector3());
    const maxDim = Math.max(size.x, size.y, size.z) || 1;
    const dist = maxDim * 2.5;

    metricsRef.current = { center, dist, maxDim };
    applyView(targetView ?? 'sw');
  }, [modelRef.current]);

  // Apply new view preset when user clicks a button
  useEffect(() => {
    if (targetView && metricsRef.current) {
      applyView(targetView);
    }
  }, [targetView]);

  // Adjust zoom when viewport width or height changes
  useEffect(() => {
    if (!metricsRef.current || !camera) return;
    const { maxDim } = metricsRef.current;
    if (camera.isOrthographicCamera) {
      const padding = 0.75;
      camera.zoom = (Math.min(width, height) * padding) / maxDim;
      camera.updateProjectionMatrix();
      if (controls) controls.update();
    }
  }, [width, height]);

  return null;
};

// ── glTF mesh renderer ───────────────────────────────────────────────────────
interface GltfMeshProps {
  gltf: GLTF;
  onLoaded: (ref: THREE.Group) => void;
  hiddenNodes: number[];
}

/** Renders a glTF model — preserves original STEP colours from embedded materials */
const GltfMesh = ({
  gltf,
  onLoaded,
  hiddenNodes,
}: GltfMeshProps) => {
  const groupRef = useRef<THREE.Group>(null!);

  // Visibility is applied by POSITION among the scene's own children, matching the order the
  // backend emits its nodes. Not by name: iCAD repeats a part name across instances, so two
  // `φ9×204` share one, and matching on it would hide both.
  useEffect(() => {
    const hide = new Set(hiddenNodes);
    gltf.scene.children.forEach((child, i) => {
      child.visible = !hide.has(i);
    });
  }, [gltf, hiddenNodes]);

  // Enhance PBR quality while keeping the colours as defined in the STEP file
  useEffect(() => {
    // Every mesh below runs mergeVertices, toCreasedNormals and EdgesGeometry on the main
    // thread, and all three are linear in triangle count: measured 1144ms per ~92k triangles,
    // of which EdgesGeometry is 42%. A 12-part assembly is 180k, so the pane sits on its
    // loading placeholder for over two seconds before anything appears.
    //
    // The outlines are the part worth dropping when a model is dense. They are a CAD styling
    // cue, not geometry, and on a model detailed enough to cross this budget they read as
    // noise on the silhouette anyway. Shading and normals are kept at every size, because
    // those change what the surface looks like rather than how it is decorated.
    let sceneTriangles = 0;
    gltf.scene.traverse((child) => {
      const m = child as THREE.Mesh;
      if (m.isMesh && m.geometry) {
        const idx = m.geometry.getIndex();
        sceneTriangles += (idx ? idx.count : m.geometry.attributes.position?.count ?? 0) / 3;
      }
    });
    const drawEdges = sceneTriangles <= EDGE_OUTLINE_TRIANGLE_BUDGET;

    gltf.scene.traverse((child) => {
      if ((child as THREE.Mesh).isMesh) {
        const mesh = child as THREE.Mesh;

        // 1. Merge duplicated vertices and compute creased normals so cylinders are silky smooth while 90° edges stay crisp
        if (mesh.geometry) {
          try {
            const merged = BufferGeometryUtils.mergeVertices(mesh.geometry);
            mesh.geometry = BufferGeometryUtils.toCreasedNormals(merged, THREE.MathUtils.degToRad(35));
          } catch {
            mesh.geometry.computeVertexNormals();
          }

          // 2. Add subtle CAD edge outlines like iCAD / SolidWorks
          const existingEdges = mesh.children.find((c) => c.name === 'cad_edges');
          if (drawEdges && !existingEdges) {
            const edgesGeom = new THREE.EdgesGeometry(mesh.geometry, 28);
            const edgesMat = new THREE.LineBasicMaterial({
              color: 0x475569,
              linewidth: 1,
              transparent: true,
              opacity: 0.65,
            });
            const line = new THREE.LineSegments(edgesGeom, edgesMat);
            line.name = 'cad_edges';
            mesh.add(line);
          }
        }

        // Support both single and multi-material meshes (one per colour group)
        const srcMats = Array.isArray(mesh.material)
          ? mesh.material
          : [mesh.material];

        const enhanced = srcMats.map((src) => {
          const m = src as THREE.MeshStandardMaterial;
          // Clone the STEP colour — fall back to clean machined steel if absent or black
          let col = m.color ? m.color.clone() : new THREE.Color(0.85, 0.85, 0.85);
          if (col.r < 0.08 && col.g < 0.08 && col.b < 0.08) {
            col = new THREE.Color(0.85, 0.85, 0.85);
          } else {
            // Restore rich CAD color saturation matching iCAD SX golden tone
            const hsl = { h: 0, s: 0, l: 0 };
            col.getHSL(hsl);
            if (hsl.s > 0.08) {
              hsl.s = Math.min(1.0, hsl.s * 1.35);
              hsl.l = Math.max(0.44, Math.min(hsl.l, 0.52));
              col.setHSL(hsl.h, hsl.s, hsl.l);
            }
          }
          return new THREE.MeshStandardMaterial({
            color:        col,
            roughness:    0.35,
            metalness:    0.05,
            side:         THREE.DoubleSide,
          });
        });

        mesh.material      = enhanced.length === 1 ? enhanced[0] : enhanced;
        mesh.castShadow    = true;
        mesh.receiveShadow = true;
      }
    });
  }, [gltf]);

  // Notify parent once mounted so CameraFitter can measure the bounding box
  useEffect(() => {
    if (groupRef.current) onLoaded(groupRef.current);
  }, [gltf]);

  return (
    <group ref={groupRef}>
      <primitive object={gltf.scene} />
    </group>
  );
};


// ── Silent error boundary to prevent scene crashes ─────────────────────────
class ErrorBoundary extends React.Component<
  { children: React.ReactNode; onError?: (error: Error) => void },
  { hasError: boolean }
> {
  constructor(props: { children: React.ReactNode; onError?: (error: Error) => void }) {
    super(props);
    this.state = { hasError: false };
  }
  static getDerivedStateFromError() {
    return { hasError: true };
  }
  override componentDidCatch(error: Error) {
    this.props.onError?.(error);
  }
  override render() {
    if (this.state.hasError) {
      return null;
    }
    return this.props.children;
  }
}

// ── Dynamic CAD Lighting Rig: Key light dynamically shines from North-East (screen top-right) ──
const DynamicCadLighting: React.FC<{ modelRef: React.RefObject<THREE.Group | null> }> = ({ modelRef }) => {
  const lightRef = useRef<THREE.DirectionalLight>(null);
  const targetRef = useRef<THREE.Object3D>(null);
  const fillLightRef = useRef<THREE.DirectionalLight>(null);
  const fillTargetRef = useRef<THREE.Object3D>(null);

  const vRight = useRef(new THREE.Vector3());
  const vUp = useRef(new THREE.Vector3());
  const vFwd = useRef(new THREE.Vector3());
  const vDir = useRef(new THREE.Vector3());
  const vFillDir = useRef(new THREE.Vector3());

  useFrame(({ camera }) => {
    if (!lightRef.current || !targetRef.current || !modelRef.current) return;

    // Model bounding box center and scale
    const box = new THREE.Box3().setFromObject(modelRef.current);
    const center = box.getCenter(new THREE.Vector3());
    const size = box.getSize(new THREE.Vector3());
    const maxDim = Math.max(size.x, size.y, size.z) || 1;
    const dist = maxDim * 2.5;

    // Extract camera orientation basis vectors in world space
    camera.matrixWorld.extractBasis(vRight.current, vUp.current, vFwd.current);

    // North-East in screen space:
    // +0.8 Right (East), +1.0 Up (North), +0.9 Forward (out of screen towards viewer)
    vDir.current
      .set(0, 0, 0)
      .addScaledVector(vRight.current, 0.8)
      .addScaledVector(vUp.current, 1.0)
      .addScaledVector(vFwd.current, 0.9)
      .normalize();

    lightRef.current.position.copy(center).addScaledVector(vDir.current, dist);
    targetRef.current.position.copy(center);
    targetRef.current.updateMatrixWorld();

    // Dynamically adjust shadow camera frustum so it covers the entire model without clipping
    const shadowCam = lightRef.current.shadow?.camera as THREE.OrthographicCamera | undefined;
    const r = maxDim * 1.5;
    if (shadowCam && shadowCam.left !== -r) {
      shadowCam.left = -r;
      shadowCam.right = r;
      shadowCam.top = r;
      shadowCam.bottom = -r;
      shadowCam.near = 0.5;
      shadowCam.far = dist * 4;
      shadowCam.updateProjectionMatrix();
    }

    // Soft opposing fill light from South-West (screen bottom-left)
    if (fillLightRef.current && fillTargetRef.current) {
      vFillDir.current
        .set(0, 0, 0)
        .addScaledVector(vRight.current, -0.6)
        .addScaledVector(vUp.current, -0.4)
        .addScaledVector(vFwd.current, 0.5)
        .normalize();

      fillLightRef.current.position.copy(center).addScaledVector(vFillDir.current, dist);
      fillTargetRef.current.position.copy(center);
      fillTargetRef.current.updateMatrixWorld();
    }
  });

  return (
    <>
      <object3D ref={targetRef} />
      <directionalLight
        ref={lightRef}
        target={targetRef.current ?? undefined}
        intensity={1.25}
        castShadow
        shadow-bias={-0.0003}
        shadow-normalBias={0.02}
        shadow-mapSize-width={2048}
        shadow-mapSize-height={2048}
      />

      <object3D ref={fillTargetRef} />
      <directionalLight
        ref={fillLightRef}
        target={fillTargetRef.current ?? undefined}
        intensity={0.4}
      />

      <ambientLight intensity={0.55} color="#ffffff" />
      <hemisphereLight
        color={new THREE.Color('#ffffff')}
        groundColor={new THREE.Color('#cbd5e1')}
        intensity={0.35}
      />
    </>
  );
};

// ── Scene wrapper ─────────────────────────────────────────────────────────────
interface ModelSceneProps {
  gltf: GLTF;
  theme?: string;
  hiddenNodes: number[];
  onSceneReady?: () => void;
  onError?: (error: Error) => void;
  targetView: ViewPreset | null;
  width: number;
  height: number;
  onStartOrbit?: () => void;
  onCameraReady?: (camera: THREE.Camera) => void;
}

const ModelScene = ({
  gltf,
  hiddenNodes,
  onSceneReady,
  onError,
  targetView,
  width,
  height,
  onStartOrbit,
  onCameraReady,
}: ModelSceneProps) => {
  const modelRef  = useRef<THREE.Group | null>(null);
  const [, forceUpdate] = useState(0);
  const { camera } = useThree();

  useEffect(() => {
    onCameraReady?.(camera);
  }, [camera, onCameraReady]);

  const handleLoaded = (ref: THREE.Group) => {
    modelRef.current = ref;
    forceUpdate((n) => n + 1); // trigger re-render so CameraController fires
    // Ensure the scene has updated and camera fitted before revealing the model
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        onSceneReady?.();
      });
    });
  };

  return (
    <>
      {/* CAD Orthographic Camera */}
      <OrthographicCamera makeDefault near={-100000} far={100000} />

      {/* ── Dynamic CAD Lighting Rig (Key light dynamically shines from North-East as model rotates) ── */}
      <DynamicCadLighting modelRef={modelRef} />

      <OrbitControls
        makeDefault
        enableDamping={false}
        minDistance={0.1}
        maxDistance={5000}
        target={[0, 0, 0]}
        /* ── CAD-style direct 1:1 mouse mapping (no inertia/sliding) ── */
        enablePan
        panSpeed={1.0}
        screenSpacePanning        /* pan along the camera plane, not the ground */
        enableRotate
        rotateSpeed={1.0}
        enableZoom
        zoomSpeed={1.0}
        onStart={onStartOrbit}
        mouseButtons={{
          LEFT:   THREE.MOUSE.ROTATE,
          MIDDLE: THREE.MOUSE.PAN,
          RIGHT:  null as any,
        }}
      />

      {/* Framing & View Presets */}
      <CameraController
        modelRef={modelRef}
        targetView={targetView}
        width={width}
        height={height}
      />


      {/* Model */}
      <ErrorBoundary onError={onError}>
        <GltfMesh gltf={gltf} onLoaded={handleLoaded} hiddenNodes={hiddenNodes} />
      </ErrorBoundary>
    </>
  );
};

// ── Public component ──────────────────────────────────────────────────────────
export const ThreeDViewer: React.FC<ThreeDViewerProps> = ({ drawing, width, height }) => {
  const theme = useThemeStore((s) => s.theme);
  const { backendUrl, apiToken } = useConnectionStore();

  const [parsedGltf,  setParsedGltf]  = useState<GLTF | null>(null);
  const [loadError,   setLoadError]   = useState<string | null>(null);
  const [isMeshReady, setIsMeshReady] = useState(false);
  const [activeView,  setActiveView]  = useState<ViewPreset | null>('sw');
  const [mainCamera,  setMainCamera]  = useState<THREE.Camera | null>(null);

  // Fetch and parse glTF from backend whenever drawing changes
  useEffect(() => {
    if (!drawing?.id) return;

    let isCancelled = false;
    setIsMeshReady(false);
    setLoadError(null);
    setParsedGltf(null);
    setActiveView('sw');

    const fetchModel = async () => {
      try {
        const headers: Record<string, string> = {};
        if (apiToken) headers['Authorization'] = `Bearer ${apiToken}`;

        const res = await fetch(
          `${backendUrl}/api/v1/drawings/${drawing.id}/gltf?t=${Date.now()}`,
          { headers }
        );

        if (!res.ok) {
          if (!isCancelled) setLoadError(`HTTP ${res.status}`);
          return;
        }

        const arrayBuffer = await res.arrayBuffer();
        if (isCancelled) return;

        const loader = new GLTFLoader();
        loader.parse(
          arrayBuffer,
          '',
          (gltf) => {
            if (!isCancelled) {
              setParsedGltf(gltf);
            }
          },
          (err) => {
            if (!isCancelled) {
              setLoadError(err instanceof Error ? err.message : String(err));
              console.error('3D model parse error:', err);
            }
          }
        );
      } catch (err) {
        if (!isCancelled) {
          setLoadError(String(err));
          console.error('3D model fetch error:', err);
        }
      }
    };

    fetchModel();

    return () => {
      isCancelled = true;
    };
  }, [drawing?.id, backendUrl, apiToken]);

  const parts: AssemblyPart[] = drawing?.metadata?.parts ?? [];
  const hiddenNodes = useReviewStore((s) => s.hiddenParts[drawing?.id ?? ''] ?? EMPTY_HIDDEN);

  return (
    <div
      style={{
        position: 'relative',
        width,
        height,
        overflow: 'hidden',
        background: 'linear-gradient(180deg, #f1f5f9 0%, #cbd5e1 45%, #8290a4 100%)',
      }}
    >

      {/* Assembly parts, and which of them are drawn. Rendered outside the Canvas: it is DOM,
          and putting it inside would make it a three.js object. */}
      {parts.length > 1 && <PartsPanel drawingId={drawing.id} parts={parts} />}

      {/* ── View Presets Toolbar: Orthographic & Isometric in separate containers (aligned with 2D toggle) ── */}
      {isMeshReady && !loadError && (
        <div className="absolute top-2 right-13 z-20 flex items-center gap-1.5 select-none">
          {/* Orthographic Face views: Top, Front, Right, Left, Back, Bottom */}
          <div className="flex items-center h-7 rounded border border-border-color bg-bg-card/90 backdrop-blur-sm shadow-sm p-0.5 gap-0.5">
            {([
              { id: 'top', label: 'Top View' },
              { id: 'front', label: 'Front View' },
              { id: 'right', label: 'Right View' },
              { id: 'left', label: 'Left View' },
              { id: 'back', label: 'Back View' },
              { id: 'bottom', label: 'Bottom View' },
            ] as const).map(({ id, label }) => (
              <button
                key={id}
                type="button"
                onClick={() => setActiveView(id)}
                className={`w-6 h-6 flex items-center justify-center rounded transition-all cursor-pointer ${
                  activeView === id
                    ? 'border border-black bg-transparent'
                    : 'border border-transparent hover:bg-border-color/30'
                }`}
                title={label}
                aria-label={label}
              >
                <ViewCubeIcon face={id} size={15} active={activeView === id} />
              </button>
            ))}
          </div>

          {/* Isometric views: SW, NW, NE, SE */}
          <div className="flex items-center h-7 rounded border border-border-color bg-bg-card/90 backdrop-blur-sm shadow-sm p-0.5 gap-0.5">
            {([
              { id: 'sw', label: 'SW Isometric (Front-Left)' },
              { id: 'nw', label: 'NW Isometric (Back-Left)' },
              { id: 'ne', label: 'NE Isometric (Back-Right)' },
              { id: 'se', label: 'SE Isometric (Front-Right)' },
            ] as const).map(({ id, label }) => (
              <button
                key={id}
                type="button"
                onClick={() => setActiveView(id)}
                className={`w-6 h-6 flex items-center justify-center rounded transition-all cursor-pointer ${
                  activeView === id
                    ? 'border border-black bg-transparent'
                    : 'border border-transparent hover:bg-border-color/30'
                }`}
                title={label}
                aria-label={label}
              >
                <ViewCubeIcon face={id} size={15} active={activeView === id} />
              </button>
            ))}
          </div>
        </div>
      )}

      {/* ── 3-D canvas ─────────────────────────────── */}
      {parsedGltf && (
        <Canvas
          shadows
          gl={{
            antialias: true,
            alpha: true,
            logarithmicDepthBuffer: true,
            toneMapping: THREE.LinearToneMapping,
          }}
          style={{ background: 'transparent' }}
        >
          <ModelScene
            gltf={parsedGltf}
            theme={theme}
            hiddenNodes={hiddenNodes}
            targetView={activeView}
            width={width}
            height={height}
            onStartOrbit={() => setActiveView(null)}
            onCameraReady={setMainCamera}
            onSceneReady={() => setIsMeshReady(true)}
            onError={(err) => setLoadError(err.message)}
          />
        </Canvas>
      )}

      {/* ── CAD 3D Orientation Tripod (X: Red, Y: Blue, Z: Yellow) ── */}
      {isMeshReady && !loadError && mainCamera && (
        <CadTripodOverlay mainCamera={mainCamera} />
      )}

      {/* ── Loading / error placeholders ───────────── */}
      {loadError ? (
        <div style={{
          position: 'absolute',
          inset: 0,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          flexDirection: 'column', gap: 12,
          color: theme === 'hc-light' ? '#333' : '#aaa',
          zIndex: 10,
        }}>
          <Box size={28} color="#ff6b6b" />
          <span style={{ fontSize: 12 }}>3D model unavailable — {loadError}</span>
        </div>
      ) : (
        <div style={{
          position: 'absolute',
          inset: 0,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          flexDirection: 'column', gap: 12,
          color: theme === 'hc-light' ? '#333' : '#aaa',
          pointerEvents: 'none',
          opacity: isMeshReady ? 0 : 1,
          transition: 'opacity 0.25s ease-out',
          zIndex: 10,
        }}>
          <span style={{ fontSize: 13, opacity: 0.6 }}>
            Loading 3D geometry…
          </span>
        </div>
      )}

    </div>
  );
};

