import React, { useEffect, useRef, useState } from 'react';
import { useThemeStore } from '../../stores/themeStore';
import { useConnectionStore } from '../../stores/connectionStore';
import { Canvas, useLoader, useThree } from '@react-three/fiber';
import {
  OrbitControls,
  OrthographicCamera,
} from '@react-three/drei';
import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import * as BufferGeometryUtils from 'three/examples/jsm/utils/BufferGeometryUtils.js';
import { PartsPanel, type AssemblyPart } from './PartsPanel';
import { useReviewStore } from '../../stores/reviewStore';
import { Box } from 'lucide-react';
import { ViewCubeIcon } from './ViewCubeIcon';

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
      case 'se': {
        const c = dist / Math.sqrt(3);
        pos.set(center.x + c, center.y + c, center.z + c);
        up.set(0, 1, 0);
        break;
      }
      case 'sw': {
        const c = dist / Math.sqrt(3);
        pos.set(center.x - c, center.y + c, center.z + c);
        up.set(0, 1, 0);
        break;
      }
      case 'ne': {
        const c = dist / Math.sqrt(3);
        pos.set(center.x + c, center.y + c, center.z - c);
        up.set(0, 1, 0);
        break;
      }
      case 'nw': {
        const c = dist / Math.sqrt(3);
        pos.set(center.x - c, center.y + c, center.z - c);
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
    applyView(targetView ?? 'se');
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
/** Renders a glTF model — preserves original STEP colours from embedded materials */
const GltfMesh = ({
  url,
  onLoaded,
  hiddenNodes,
}: {
  url: string;
  onLoaded: (ref: THREE.Group) => void;
  hiddenNodes: number[];
}) => {
  const gltf    = useLoader(GLTFLoader, url);
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
          let col = m.color ? m.color.clone() : new THREE.Color(0.82, 0.85, 0.88);
          if (col.r < 0.08 && col.g < 0.08 && col.b < 0.08) {
            col = new THREE.Color(0.82, 0.85, 0.88);
          }
          return new THREE.MeshPhysicalMaterial({
            color:        col,
            roughness:    0.35,
            metalness:    0.25,
            reflectivity: 0.40,
            clearcoat:    0.15,
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

// ── Scene wrapper ─────────────────────────────────────────────────────────────
const ModelScene = ({
  url,
  hiddenNodes,
  onSceneReady,
  onError,
  targetView,
  width,
  height,
  onStartOrbit,
}: {
  url: string;
  theme?: string;
  hiddenNodes: number[];
  onSceneReady?: () => void;
  onError?: (error: Error) => void;
  targetView: ViewPreset | null;
  width: number;
  height: number;
  onStartOrbit?: () => void;
}) => {
  const modelRef  = useRef<THREE.Group | null>(null);
  const [, forceUpdate] = useState(0);

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
      {/* CAD Orthographic Camera (Zero perspective distortion, matching iCAD SX) */}
      <OrthographicCamera makeDefault near={-100000} far={100000} />

      {/* Studio CAD Lighting rig */}
      <ambientLight intensity={0.65} />
      <directionalLight
        position={[12, 16, 12]}
        intensity={1.8}
        castShadow
        shadow-mapSize-width={2048}
        shadow-mapSize-height={2048}
      />
      <directionalLight position={[-12, 10, -10]} intensity={0.9} />
      <directionalLight position={[0, -10, 6]} intensity={0.4} />
      <hemisphereLight
        color={new THREE.Color('#ffffff')}
        groundColor={new THREE.Color('#334155')}
        intensity={0.5}
      />

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
        <React.Suspense fallback={null}>
          <GltfMesh url={url} onLoaded={handleLoaded} hiddenNodes={hiddenNodes} />
        </React.Suspense>
      </ErrorBoundary>

    </>
  );
};

// ── Public component ──────────────────────────────────────────────────────────
export const ThreeDViewer: React.FC<ThreeDViewerProps> = ({ drawing, width, height }) => {
  const theme = useThemeStore((s) => s.theme);
  const { backendUrl, apiToken } = useConnectionStore();

  const [modelUrl,    setModelUrl]    = useState<string | null>(null);
  const [loadError,   setLoadError]   = useState<string | null>(null);
  const [isMeshReady, setIsMeshReady] = useState(false);
  const [activeView,  setActiveView]  = useState<ViewPreset | null>('se');

  // Fetch glTF blob from backend whenever drawing changes
  useEffect(() => {
    if (!drawing?.id) return;

    let objectUrl: string | null = null;
    setIsMeshReady(false);
    setLoadError(null);
    setModelUrl(null);
    setActiveView('se');

    const fetchModel = async () => {
      try {
        const headers: Record<string, string> = {};
        if (apiToken) headers['Authorization'] = `Bearer ${apiToken}`;

        const res = await fetch(
          `${backendUrl}/api/v1/drawings/${drawing.id}/gltf?t=${Date.now()}`,
          { headers }
        );

        if (res.ok) {
          // Create blob with explicit MIME so GLTFLoader resolves it correctly
          const arrayBuffer = await res.arrayBuffer();
          // The backend now sends binary glTF. GLTFLoader identifies a document by its magic
          // bytes rather than this type, so both the GLB and any .gltf written before the
          // switch still load -- but a blob should not claim to be JSON when it is not.
          const blob = new Blob([arrayBuffer], { type: 'model/gltf-binary' });
          objectUrl = URL.createObjectURL(blob);
          setModelUrl(objectUrl);
        } else {
          setLoadError(`HTTP ${res.status}`);
        }
      } catch (err) {
        setLoadError(String(err));
        console.error('3D model fetch error:', err);
      }
    };

    fetchModel();

    return () => {
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [drawing?.id, backendUrl, apiToken]);

  const parts: AssemblyPart[] = drawing?.metadata?.parts ?? [];
  const hiddenNodes = useReviewStore((s) => s.hiddenParts[drawing?.id ?? ''] ?? EMPTY_HIDDEN);

  return (
    <div style={{ position: 'relative', width, height, overflow: 'hidden' }}>

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

          {/* Isometric views: SE, SW, NE, NW */}
          <div className="flex items-center h-7 rounded border border-border-color bg-bg-card/90 backdrop-blur-sm shadow-sm p-0.5 gap-0.5">
            {([
              { id: 'se', label: 'SE Isometric (Front-Right)' },
              { id: 'sw', label: 'SW Isometric (Front-Left)' },
              { id: 'ne', label: 'NE Isometric (Back-Right)' },
              { id: 'nw', label: 'NW Isometric (Back-Left)' },
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
      {modelUrl && (
        <Canvas
          shadows
          gl={{ antialias: true, alpha: true, logarithmicDepthBuffer: true }}
          style={{ background: 'transparent' }}
        >
          <ModelScene
            url={modelUrl}
            theme={theme}
            hiddenNodes={hiddenNodes}
            targetView={activeView}
            width={width}
            height={height}
            onStartOrbit={() => setActiveView(null)}
            onSceneReady={() => setIsMeshReady(true)}
            onError={(err) => setLoadError(err.message)}
          />
        </Canvas>
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

