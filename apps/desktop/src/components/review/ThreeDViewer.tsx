import React, { useEffect, useRef, useState } from 'react';
import { useThemeStore } from '../../stores/themeStore';
import { useConnectionStore } from '../../stores/connectionStore';
import { Canvas, useLoader, useThree } from '@react-three/fiber';
import { OrbitControls } from '@react-three/drei';
import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import * as BufferGeometryUtils from 'three/examples/jsm/utils/BufferGeometryUtils.js';
import { PartsPanel, type AssemblyPart } from './PartsPanel';
import { useReviewStore } from '../../stores/reviewStore';
import { Box } from 'lucide-react';

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

// ── Auto-fit camera to the loaded model's bounding box ──────────────────────
const CameraFitter = ({ modelRef }: { modelRef: React.RefObject<THREE.Group | null> }) => {
  const { camera, controls } = useThree() as any;

  useEffect(() => {
    if (!modelRef.current) return;

    const box   = new THREE.Box3().setFromObject(modelRef.current);
    const size  = box.getSize(new THREE.Vector3());
    const center= box.getCenter(new THREE.Vector3());

    // Frame the model: pull the camera back so the full diagonal fits in fov
    const maxDim = Math.max(size.x, size.y, size.z);
    const fov    = (camera as THREE.PerspectiveCamera).fov * (Math.PI / 180);
    const dist   = (maxDim / 2) / Math.tan(fov / 2) * 2.2; // 2.2× gives comfortable padding

    const angle = Math.PI / 5; // ~36° elevation
    camera.position.set(
      center.x + dist * Math.cos(angle),
      center.y + dist * Math.sin(angle),
      center.z + dist * Math.cos(angle)
    );
    camera.near  = dist / 100;
    camera.far   = dist * 100;
    camera.updateProjectionMatrix();

    if (controls) {
      controls.target.copy(center);
      controls.update();
    }
  }, [modelRef.current]);

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
}: {
  url: string;
  theme?: string;
  hiddenNodes: number[];
  onSceneReady?: () => void;
  onError?: (error: Error) => void;
}) => {
  const modelRef  = useRef<THREE.Group | null>(null);
  const [, forceUpdate] = useState(0);

  const handleLoaded = (ref: THREE.Group) => {
    modelRef.current = ref;
    forceUpdate((n) => n + 1); // trigger re-render so CameraFitter fires
    // Ensure the scene has updated and camera fitted before revealing the model
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        onSceneReady?.();
      });
    });
  };

  return (
    <>
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
        enableDamping
        dampingFactor={0.06}
        minDistance={0.1}
        maxDistance={5000}
        target={[0, 0, 0]}
        /* ── CAD-style mouse mapping ── */
        enablePan
        panSpeed={1.2}
        screenSpacePanning        /* pan along the camera plane, not the ground */
        enableRotate
        rotateSpeed={0.8}
        enableZoom
        zoomSpeed={1.2}
        mouseButtons={{
          LEFT:   THREE.MOUSE.ROTATE,
          MIDDLE: THREE.MOUSE.PAN,
          RIGHT:  null as any,
        }}
      />

      {/* Auto-fit camera once model is loaded */}
      <CameraFitter modelRef={modelRef} />

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

  // Fetch glTF blob from backend whenever drawing changes
  useEffect(() => {
    if (!drawing?.id) return;

    let objectUrl: string | null = null;
    setIsMeshReady(false);
    setLoadError(null);
    setModelUrl(null);

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

      {/* ── 3-D canvas ─────────────────────────────── */}
      {modelUrl && (
        <Canvas
          camera={{ position: [0, 0, 10], fov: 45, near: 0.01, far: 100000 }}
          shadows
          gl={{ antialias: true, alpha: true, logarithmicDepthBuffer: true }}
          style={{ background: 'transparent' }}
        >
          <ModelScene
            url={modelUrl}
            theme={theme}
            hiddenNodes={hiddenNodes}
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

