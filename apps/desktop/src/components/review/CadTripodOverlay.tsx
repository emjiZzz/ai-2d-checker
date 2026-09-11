import React, { useRef, useState } from 'react';
import { Canvas, useFrame } from '@react-three/fiber';
import * as THREE from 'three';

interface CadTripodOverlayProps {
  mainCamera: THREE.Camera;
}

const ARROW_SHAFT_RADIUS = 0.045;
const ARROW_SHAFT_LENGTH = 0.68;
const ARROW_HEAD_RADIUS = 0.11;
const ARROW_HEAD_LENGTH = 0.25;
const LABEL_TIP_OFFSET = 1.08;

// ── Colors from CAD specification: X=Red, Y=Blue, Z=Yellow ──────────────────
const COLOR_X = '#dc2626'; // Red
const COLOR_Y = '#1d4ed8'; // Blue
const COLOR_Z = '#eab308'; // Yellow

interface TripodSceneProps {
  mainCamera: THREE.Camera;
  onPositionsUpdate: (pos: {
    x: [number, number];
    y: [number, number];
    z: [number, number];
  }) => void;
  size: number;
  zoom: number;
}

const TripodScene: React.FC<TripodSceneProps> = ({
  mainCamera,
  onPositionsUpdate,
  size,
  zoom,
}) => {
  const groupRef = useRef<THREE.Group>(null);
  const qInv = useRef(new THREE.Quaternion());
  const vX = useRef(new THREE.Vector3(LABEL_TIP_OFFSET, 0, 0));
  const vY = useRef(new THREE.Vector3(0, LABEL_TIP_OFFSET, 0));
  const vZ = useRef(new THREE.Vector3(0, 0, LABEL_TIP_OFFSET));

  useFrame(() => {
    if (!groupRef.current) return;

    // Mirror the main camera's rotation so tripod matches model space
    qInv.current.copy(mainCamera.quaternion).invert();
    groupRef.current.quaternion.copy(qInv.current);

    // Project tip points to 2D overlay pixel coordinates
    const half = size / 2;
    const px = vX.current.set(LABEL_TIP_OFFSET, 0, 0).applyQuaternion(qInv.current);
    const py = vY.current.set(0, LABEL_TIP_OFFSET, 0).applyQuaternion(qInv.current);
    const pz = vZ.current.set(0, 0, LABEL_TIP_OFFSET).applyQuaternion(qInv.current);

    onPositionsUpdate({
      x: [half + px.x * zoom, half - px.y * zoom],
      y: [half + py.x * zoom, half - py.y * zoom],
      z: [half + pz.x * zoom, half - pz.y * zoom],
    });
  });

  return (
    <>
      <ambientLight intensity={0.9} />
      <directionalLight position={[2, 4, 3]} intensity={1.8} />
      <directionalLight position={[-2, -2, -1]} intensity={0.5} />

      <group ref={groupRef}>
        {/* Central joint */}
        <mesh>
          <sphereGeometry args={[ARROW_SHAFT_RADIUS * 1.15, 16, 16]} />
          <meshStandardMaterial color="#475569" roughness={0.3} metalness={0.2} />
        </mesh>

        {/* ── X Axis (Red) ── */}
        <group>
          {/* Cylinder Shaft */}
          <mesh position={[ARROW_SHAFT_LENGTH / 2, 0, 0]} rotation={[0, 0, -Math.PI / 2]}>
            <cylinderGeometry args={[ARROW_SHAFT_RADIUS, ARROW_SHAFT_RADIUS, ARROW_SHAFT_LENGTH, 16]} />
            <meshStandardMaterial color={COLOR_X} roughness={0.25} metalness={0.15} />
          </mesh>
          {/* Cone Arrowhead */}
          <mesh position={[ARROW_SHAFT_LENGTH + ARROW_HEAD_LENGTH / 2, 0, 0]} rotation={[0, 0, -Math.PI / 2]}>
            <coneGeometry args={[ARROW_HEAD_RADIUS, ARROW_HEAD_LENGTH, 16]} />
            <meshStandardMaterial color={COLOR_X} roughness={0.25} metalness={0.15} />
          </mesh>
        </group>

        {/* ── Y Axis (Blue) ── */}
        <group>
          {/* Cylinder Shaft */}
          <mesh position={[0, ARROW_SHAFT_LENGTH / 2, 0]} rotation={[0, 0, 0]}>
            <cylinderGeometry args={[ARROW_SHAFT_RADIUS, ARROW_SHAFT_RADIUS, ARROW_SHAFT_LENGTH, 16]} />
            <meshStandardMaterial color={COLOR_Y} roughness={0.25} metalness={0.15} />
          </mesh>
          {/* Cone Arrowhead */}
          <mesh position={[0, ARROW_SHAFT_LENGTH + ARROW_HEAD_LENGTH / 2, 0]} rotation={[0, 0, 0]}>
            <coneGeometry args={[ARROW_HEAD_RADIUS, ARROW_HEAD_LENGTH, 16]} />
            <meshStandardMaterial color={COLOR_Y} roughness={0.25} metalness={0.15} />
          </mesh>
        </group>

        {/* ── Z Axis (Yellow) ── */}
        <group>
          {/* Cylinder Shaft */}
          <mesh position={[0, 0, ARROW_SHAFT_LENGTH / 2]} rotation={[Math.PI / 2, 0, 0]}>
            <cylinderGeometry args={[ARROW_SHAFT_RADIUS, ARROW_SHAFT_RADIUS, ARROW_SHAFT_LENGTH, 16]} />
            <meshStandardMaterial color={COLOR_Z} roughness={0.25} metalness={0.15} />
          </mesh>
          {/* Cone Arrowhead */}
          <mesh position={[0, 0, ARROW_SHAFT_LENGTH + ARROW_HEAD_LENGTH / 2]} rotation={[Math.PI / 2, 0, 0]}>
            <coneGeometry args={[ARROW_HEAD_RADIUS, ARROW_HEAD_LENGTH, 16]} />
            <meshStandardMaterial color={COLOR_Z} roughness={0.25} metalness={0.15} />
          </mesh>
        </group>
      </group>
    </>
  );
};

export const CadTripodOverlay: React.FC<CadTripodOverlayProps> = ({ mainCamera }) => {
  const SIZE = 110;
  const ZOOM = 40;

  const [labelPositions, setLabelPositions] = useState<{
    x: [number, number];
    y: [number, number];
    z: [number, number];
  }>({
    x: [SIZE / 2 + LABEL_TIP_OFFSET * ZOOM, SIZE / 2],
    y: [SIZE / 2, SIZE / 2 - LABEL_TIP_OFFSET * ZOOM],
    z: [SIZE / 2, SIZE / 2],
  });

  return (
    <div
      className="absolute top-2 left-2 pointer-events-none z-20 select-none"
      style={{ width: SIZE, height: SIZE }}
      title="CAD Orientation (X: Red, Y: Blue, Z: Yellow)"
    >
      {/* 3-D Arrow Tripod Canvas */}
      <Canvas
        orthographic
        camera={{ position: [0, 0, 10], zoom: ZOOM, near: -100, far: 100 }}
        gl={{ alpha: true, antialias: true }}
        style={{ background: 'transparent', width: '100%', height: '100%' }}
      >
        <TripodScene
          mainCamera={mainCamera}
          onPositionsUpdate={setLabelPositions}
          size={SIZE}
          zoom={ZOOM}
        />
      </Canvas>

      {/* ── Spanned Letters at Arrow Tips ── */}
      <span
        style={{
          position: 'absolute',
          left: labelPositions.x[0],
          top: labelPositions.x[1],
          transform: 'translate(-50%, -50%)',
          color: COLOR_X,
          fontWeight: 800,
          fontSize: 13,
          fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
          textShadow: '0 0 3px rgba(255,255,255,0.9), 0 0 1px #fff',
        }}
      >
        X
      </span>

      <span
        style={{
          position: 'absolute',
          left: labelPositions.y[0],
          top: labelPositions.y[1],
          transform: 'translate(-50%, -50%)',
          color: COLOR_Y,
          fontWeight: 800,
          fontSize: 13,
          fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
          textShadow: '0 0 3px rgba(255,255,255,0.9), 0 0 1px #fff',
        }}
      >
        Y
      </span>

      <span
        style={{
          position: 'absolute',
          left: labelPositions.z[0],
          top: labelPositions.z[1],
          transform: 'translate(-50%, -50%)',
          color: COLOR_Z,
          fontWeight: 800,
          fontSize: 13,
          fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
          textShadow: '0 0 3px rgba(0,0,0,0.5), 0 0 1px #000',
        }}
      >
        Z
      </span>
    </div>
  );
};
