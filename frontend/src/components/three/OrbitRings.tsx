import React, { useEffect, useRef } from "react";
import * as THREE from "three";
import { useThreeStage } from "./useThreeStage";
import { INK } from "./palette";

const MERIDIANS = 22;
const RADIUS = 2.3;

interface OrbitRingsProps {
  /** Spins faster and pulses the core while a diagnosis is running. */
  active?: boolean;
  className?: string;
}

/** Wireframe meridian sphere with a magnetic core that follows the cursor. */
export const OrbitRings: React.FC<OrbitRingsProps> = ({ active = false, className }) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const activeRef = useRef(active);

  useEffect(() => {
    activeRef.current = active;
  }, [active]);

  useThreeStage(containerRef, ({ scene, camera, pointer, reducedMotion }) => {
    camera.fov = 32;
    camera.position.set(0, 0, 10);
    camera.lookAt(0, 0, 0);

    const stretch = new THREE.Group();
    const spinner = new THREE.Group();
    stretch.add(spinner);
    scene.add(stretch);

    const circle = new THREE.BufferGeometry().setFromPoints(
      Array.from({ length: 180 }, (_, i) => {
        const angle = (i / 180) * Math.PI * 2;
        return new THREE.Vector3(Math.cos(angle) * RADIUS, Math.sin(angle) * RADIUS, 0);
      }),
    );
    const lineMaterial = new THREE.LineBasicMaterial({ color: INK, transparent: true, opacity: 0.82 });
    for (let i = 0; i < MERIDIANS; i++) {
      const meridian = new THREE.LineLoop(circle, lineMaterial);
      meridian.rotation.y = (i / MERIDIANS) * Math.PI;
      spinner.add(meridian);
    }

    const core = new THREE.Mesh(new THREE.SphereGeometry(0.3, 40, 20), new THREE.MeshBasicMaterial({ color: INK }));
    scene.add(core);

    let velocity = 0;
    return {
      pointerDown() {
        velocity += 3;
      },
      update(elapsed, delta) {
        const ease = 1 - Math.exp(-delta * 4);
        const busy = activeRef.current;
        velocity *= Math.exp(-delta * 1.4);
        spinner.rotation.y += delta * ((reducedMotion ? 0 : busy ? 1.6 : 0.22) + velocity);

        const spread = pointer.inside ? 1.75 : 1.5;
        stretch.scale.x += (spread - stretch.scale.x) * ease;
        stretch.rotation.x += ((pointer.inside ? -pointer.y * 0.35 : 0) - stretch.rotation.x) * ease;
        stretch.rotation.z += ((pointer.inside ? -pointer.x * 0.12 : 0) - stretch.rotation.z) * ease;

        core.position.x += ((pointer.inside ? pointer.x * 1.4 : 0) - core.position.x) * ease;
        core.position.y += ((pointer.inside ? pointer.y * 0.9 : 0) - core.position.y) * ease;
        const pulse = busy && !reducedMotion ? 1 + Math.sin(elapsed * 6) * 0.18 : 1;
        core.scale.setScalar(pulse * (1 + pointer.energy * 0.6));
      },
    };
  });

  return <div ref={containerRef} className={className} aria-hidden="true" />;
};
