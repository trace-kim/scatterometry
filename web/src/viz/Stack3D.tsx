// Interactive 3D view of the mask stack: one instanced mesh per material, a clipping
// plane to cut the stack open, orbit controls. Coordinates are nm with z = -depth.
import { GizmoHelper, GizmoViewport, OrbitControls } from "@react-three/drei";
import { Canvas } from "@react-three/fiber";
import { useLayoutEffect, useMemo, useRef } from "react";
import * as THREE from "three";
import type { BoxesResponse } from "@/api/model";
import { useThemeColors } from "./theme";

interface Stack3DProps {
  data: BoxesResponse;
  /** Material display colors, indexed like data.materials. */
  colors: string[];
  /** Fraction of the x extent kept visible (1 = whole stack). */
  cut: number;
}

type Box = number[]; // [material, x0, x1, y0, y1, z0, z1]

const SHRINK = 0.9995;

function MaterialBoxes({ boxes, color, clip }: { boxes: Box[]; color: string; clip: THREE.Plane[] }) {
  const mesh = useRef<THREE.InstancedMesh>(null);
  useLayoutEffect(() => {
    const target = mesh.current;
    if (!target) return;
    const matrix = new THREE.Matrix4();
    const position = new THREE.Vector3();
    const rotation = new THREE.Quaternion();
    const scale = new THREE.Vector3();
    boxes.forEach(([, x0, x1, y0, y1, z0, z1], i) => {
      position.set((x0 + x1) / 2, (y0 + y1) / 2, -(z0 + z1) / 2);
      // Shrink a hair so faces shared by neighbouring boxes don't z-fight.
      scale.set((x1 - x0) * SHRINK, (y1 - y0) * SHRINK, (z1 - z0) * SHRINK);
      target.setMatrixAt(i, matrix.compose(position, rotation, scale));
    });
    target.instanceMatrix.needsUpdate = true;
    target.computeBoundingSphere();
  }, [boxes]);
  return (
    <instancedMesh ref={mesh} args={[undefined, undefined, boxes.length]}>
      <boxGeometry />
      <meshStandardMaterial
        color={color}
        roughness={0.55}
        metalness={0.05}
        clippingPlanes={clip}
        side={THREE.DoubleSide}
      />
    </instancedMesh>
  );
}

export function Stack3D({ data, colors, cut }: Stack3DProps) {
  const theme = useThemeColors();
  const [width, height, depth] = data.size_nm;
  const groups = useMemo(() => {
    const byMaterial = new Map<number, Box[]>();
    for (const box of data.boxes) {
      const list = byMaterial.get(box[0]) ?? [];
      list.push(box);
      byMaterial.set(box[0], list);
    }
    return [...byMaterial.entries()];
  }, [data.boxes]);
  const clip = useMemo(
    () => [new THREE.Plane(new THREE.Vector3(-1, 0, 0), Math.max(cut, 0.001) * width)],
    [cut, width],
  );
  const span = Math.max(width, height, depth);
  const center = new THREE.Vector3(width / 2, height / 2, -depth / 2);

  return (
    <Canvas
      key={`${width}-${height}-${depth}`}
      camera={{
        up: [0, 0, 1],
        fov: 32,
        near: span / 100,
        far: span * 20,
        position: [center.x + span * 1.9, center.y - span * 2.4, center.z + span * 1.5],
      }}
      onCreated={({ gl }) => {
        gl.localClippingEnabled = true;
      }}
      style={{ background: theme.background }}
    >
      <ambientLight intensity={0.55} />
      <directionalLight position={[width * 2, -height, depth * 2 + span]} intensity={1.1} />
      <directionalLight position={[-width, height * 2, span]} intensity={0.35} />
      {groups.map(([material, boxes]) => (
        <MaterialBoxes
          key={`${material}-${boxes.length}`}
          boxes={boxes}
          color={colors[material] ?? "#999"}
          clip={clip}
        />
      ))}
      <OrbitControls makeDefault target={center} />
      <GizmoHelper alignment="bottom-right" margin={[56, 56]}>
        <GizmoViewport labelColor={theme.dark ? "black" : "white"} axisHeadScale={0.9} />
      </GizmoHelper>
    </Canvas>
  );
}
