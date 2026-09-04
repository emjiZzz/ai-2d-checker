import React, { useEffect, useRef, useState } from 'react';
import { useThemeStore } from '../../stores/themeStore';
import { useConnectionStore } from '../../stores/connectionStore';
import { Box } from 'lucide-react';
import { Canvas, useLoader, useThree } from '@react-three/fiber';
import { OrbitControls, Grid } from '@react-three/drei';
import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';

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

// ── glTF mesh renderer ───────────────────────────────────────────────────────/** Renders a glTF model — preserves original STEP colours from embedded materials */
const GltfMesh = ({
  url,
  onLoaded,
}: {
  url: string;
  onLoaded: (ref: THREE.Group) => void;
}) => {
  const gltf    = useLoader(GLTFLoader, url);
  const groupRef = useRef<THREE.Group>(null!);

  // Enhance PBR quality while keeping the colours as defined in the STEP file
  useEffect(() => {
    gltf.scene.traverse((child) => {
      if ((child as THREE.Mesh).isMesh) {
        const mesh = child as THREE.Mesh;
        mesh.geometry.computeVertexNormals();

        // Support both single and multi-material meshes (one per colour group)
        const srcMats = Array.isArray(mesh.material)
          ? mesh.material
          : [mesh.material];

        const enhanced = srcMats.map((src) => {
          const m = src as THREE.MeshStandardMaterial;
          // Clone the STEP colour — fall back to engineering gray if absent
          const col = m.color ? m.color.clone() : new THREE.Color(0.75, 0.75, 0.75);
          return new THREE.MeshPhysicalMaterial({
            color:        col,
            roughness:    0.45,
            metalness:    0.30,
            reflectivity: 0.35,
            clearcoat:    0.08,
            side:         THREE.DoubleSide,
          });
        });

        mesh.material    = enhanced.length === 1 ? enhanced[0] : enhanced;
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


// ── Simple error boundary that renders a neutral placeholder ─────────────────
class ErrorBoundary extends React.Component<
  { children: React.ReactNode },
  { hasError: boolean; message: string }
> {
  constructor(props: { children: React.ReactNode }) {
    super(props);
    this.state = { hasError: false, message: '' };
  }
  static getDerivedStateFromError(err: Error) {
    return { hasError: true, message: err.message };
  }
  render() {
    if (this.state.hasError) {
      // Neutral placeholder — NOT red, so it doesn't alarm users
      return (
        <mesh>
          <boxGeometry args={[1, 1, 1]} />
          <meshStandardMaterial color="#1e3a4a" wireframe opacity={0.6} transparent />
        </mesh>
      );
    }
    return this.props.children;
  }
}

// ── Scene wrapper ─────────────────────────────────────────────────────────────
const ModelScene = ({
  url,
  theme,
}: {
  url: string;
  theme: string;
}) => {
  const modelRef  = useRef<THREE.Group | null>(null);
  const [, forceUpdate] = useState(0);

  const handleLoaded = (ref: THREE.Group) => {
    modelRef.current = ref;
    forceUpdate((n) => n + 1); // trigger re-render so CameraFitter fires
  };

  return (
    <>
      {/* Lighting rig */}
      <ambientLight intensity={0.45} />
      <directionalLight
        position={[8, 12, 8]}
        intensity={1.6}
        castShadow
        shadow-mapSize-width={2048}
        shadow-mapSize-height={2048}
      />
      <directionalLight position={[-6, -4, -6]} intensity={0.35} />
      <hemisphereLight
        color={new THREE.Color('#b0e4ff')}
        groundColor={new THREE.Color('#1a2a33')}
        intensity={0.4}
      />

      <OrbitControls
        makeDefault
        enableDamping
        dampingFactor={0.06}
        minDistance={0.1}
        maxDistance={5000}
        target={[0, 0, 0]}
      />

      {/* Auto-fit camera once model is loaded */}
      <CameraFitter modelRef={modelRef} />

      {/* Model */}
      <ErrorBoundary>
        <React.Suspense
          fallback={
            <mesh>
              <boxGeometry args={[0.5, 0.5, 0.5]} />
              <meshBasicMaterial color="#1a3a4a" wireframe />
            </mesh>
          }
        >
          <GltfMesh url={url} onLoaded={handleLoaded} />
        </React.Suspense>
      </ErrorBoundary>

      {/* Ground grid — sized to fit the model */}
      <Grid
        args={[2000, 2000]}
        cellSize={10}
        cellThickness={0.6}
        cellColor={theme === 'hc-light' ? '#bbb' : '#2a2a2a'}
        sectionSize={100}
        sectionThickness={1.2}
        sectionColor={theme === 'hc-light' ? '#888' : '#444'}
        fadeDistance={3000}
        position={[0, -200, 0]}
      />
    </>
  );
};

// ── Public component ──────────────────────────────────────────────────────────
export const ThreeDViewer: React.FC<ThreeDViewerProps> = ({ drawing, width, height }) => {
  const theme = useThemeStore((s) => s.theme);
  const { backendUrl, apiToken } = useConnectionStore();

  const [modelUrl,  setModelUrl]  = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loading,   setLoading]   = useState(false);

  // Fetch glTF blob from backend whenever drawing changes
  useEffect(() => {
    if (!drawing?.id) return;

    let objectUrl: string | null = null;

    const fetchModel = async () => {
      setLoading(true);
      setLoadError(null);
      setModelUrl(null);

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
          const blob = new Blob([arrayBuffer], { type: 'model/gltf+json' });
          objectUrl = URL.createObjectURL(blob);
          setModelUrl(objectUrl);
        } else {
          setLoadError(`HTTP ${res.status}`);
        }
      } catch (err) {
        setLoadError(String(err));
        console.error('3D model fetch error:', err);
      } finally {
        setLoading(false);
      }
    };

    fetchModel();

    return () => {
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [drawing?.id, backendUrl, apiToken]);

  return (
    <div style={{ position: 'relative', width, height, overflow: 'hidden' }}>

      {/* ── 3-D canvas ─────────────────────────────── */}
      {modelUrl && (
        <Canvas
          camera={{ position: [0, 0, 10], fov: 45, near: 0.01, far: 100000 }}
          shadows
          gl={{ antialias: true, alpha: true, logarithmicDepthBuffer: true }}
          style={{ background: 'transparent' }}
        >
          <ModelScene url={modelUrl} theme={theme} />
        </Canvas>
      )}

      {/* ── Loading / error placeholders ───────────── */}
      {!modelUrl && (
        <div style={{
          width: '100%', height: '100%',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          flexDirection: 'column', gap: 12,
          color: theme === 'hc-light' ? '#333' : '#aaa',
        }}>
          {loadError ? (
            <>
              <Box size={28} color="#ff6b6b" />
              <span style={{ fontSize: 12 }}>3D model unavailable — {loadError}</span>
            </>
          ) : (
            <span style={{ fontSize: 13, opacity: 0.6 }}>
              {loading ? 'Loading 3D geometry…' : 'Ingesting and parsing 3D B-Rep geometry…'}
            </span>
          )}
        </div>
      )}

      {/* ── Telemetry HUD ──────────────────────────── */}
      <div style={{
        position: 'absolute', top: 16, left: 16,
        padding: '12px 16px',
        backgroundColor: theme === 'hc-light' ? 'rgba(226,230,237,0.95)' : 'rgba(9,9,11,0.95)',
        border: `1px solid ${theme === 'hc-light' ? 'rgba(0,0,0,0.1)' : 'rgba(255,255,255,0.08)'}`,
        borderRadius: 8,
        backdropFilter: 'blur(8px)',
        pointerEvents: 'none',
        display: 'flex', flexDirection: 'column', gap: 6,
        zIndex: 10,
        minWidth: 180,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
          <Box size={16} color="#00e5ff" />
          <span style={{ fontSize: 13, fontWeight: 700, color: '#00e5ff', letterSpacing: '0.05em' }}>
            3D TELEMETRY MONITOR
          </span>
        </div>
        <HudRow label="Model Name" value={drawing?.file_name || '—'} />
        <HudRow label="Format"     value={drawing?.format?.toUpperCase() || '—'} color="#a855f7" />
        {drawing?.metadata?.triangle_count > 0 && (
          <HudRow label="Triangles"  value={drawing.metadata.triangle_count.toLocaleString()} color="#10b981" />
        )}
        {drawing?.metadata?.face_count > 0 && (
          <HudRow label="B-Rep Faces" value={drawing.metadata.face_count.toLocaleString()} color="#f59e0b" />
        )}
        {drawing?.metadata?.vertex_count > 0 && (
          <HudRow label="Vertices"   value={drawing.metadata.vertex_count.toLocaleString()} color="#60a5fa" />
        )}
        {drawing?.metadata?.color_groups > 1 && (
          <HudRow label="Colour Groups" value={`${drawing.metadata.color_groups} zones`} color="#e879f9" />
        )}
        <div style={{ marginTop: 4, paddingTop: 6, borderTop: '1px solid rgba(255,255,255,0.07)' }}>
          <span style={{ fontSize: 10, opacity: 0.4, fontFamily: 'monospace' }}>
            Drag to orbit · Scroll to zoom
          </span>
        </div>
      </div>
    </div>
  );
};

const HudRow = ({
  label, value, color,
}: {
  label: string; value: string; color?: string;
}) => {
  const theme = useThemeStore((s) => s.theme);
  return (
    <div style={{ fontSize: 12, color: theme === 'hc-light' ? '#333' : '#ddd' }}>
      <span style={{ opacity: 0.55 }}>{label} : </span>
      <span style={{ fontWeight: 600, color: color ?? 'inherit' }}>{value}</span>
    </div>
  );
};
