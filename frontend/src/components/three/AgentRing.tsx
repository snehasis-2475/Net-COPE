import React, { useRef } from "react";
import * as THREE from "three";
import { useThreeStage } from "./useThreeStage";
import { PAPER, SIGNAL } from "./palette";

/** Telemetry dimensions watched by the five agents, arranged as a rotating orbit. */
const SIGNALS = [
  "LATENCY",
  "JITTER",
  "PACKET LOSS",
  "BANDWIDTH",
  "CPU LOAD",
  "MEMORY",
  "CRC ERRORS",
  "QUEUE DROPS",
  "FLAPPING",
  "DNS",
  "DHCP",
  "RSSI",
  "SNR",
  "REACHABILITY",
];

const RADIUS = 2.5;
const FONT_PX = 26;
const WORLD_PER_PX = 0.0058;

const makeLabelTexture = (label: string) => {
  const canvas = document.createElement("canvas");
  const context = canvas.getContext("2d")!;
  const font = `500 ${FONT_PX}px "JetBrains Mono", monospace`;
  context.font = font;
  const textWidth = Math.ceil(context.measureText(label).width) + 16;
  const scale = 2;
  canvas.width = 36 * scale;
  canvas.height = textWidth * scale;

  const draw = () => {
    context.setTransform(scale, 0, 0, scale, 0, 0);
    context.clearRect(0, 0, 36, textWidth);
    context.font = font;
    context.fillStyle = "#ffffff";
    context.textBaseline = "middle";
    context.translate(18, textWidth);
    context.rotate(-Math.PI / 2);
    context.fillText(label, 8, 0);
  };
  draw();

  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  document.fonts?.ready.then(() => {
    draw();
    texture.needsUpdate = true;
  });
  return { texture, width: 36, height: textWidth };
};

/** A rotating ring of telemetry signals; hovering a signal lights it in the accent colour. */
export const AgentRing: React.FC<{ className?: string }> = ({ className }) => {
  const containerRef = useRef<HTMLDivElement>(null);

  useThreeStage(containerRef, ({ scene, camera, pointer, reducedMotion }) => {
    camera.fov = 30;
    camera.position.set(0, 2.7, 10.5);
    camera.lookAt(0, 1.05, 0);

    const base = new THREE.Color(PAPER);
    const accent = new THREE.Color(SIGNAL);
    const group = new THREE.Group();
    scene.add(group);

    const circle = (radius: number, y: number, segments = 160) =>
      new THREE.BufferGeometry().setFromPoints(
        Array.from({ length: segments }, (_, i) => {
          const angle = (i / segments) * Math.PI * 2;
          return new THREE.Vector3(Math.cos(angle) * radius, y, Math.sin(angle) * radius);
        }),
      );
    group.add(new THREE.LineLoop(circle(RADIUS, 0), new THREE.LineBasicMaterial({ color: base, transparent: true, opacity: 0.8 })));
    group.add(new THREE.LineLoop(circle(RADIUS * 1.08, -0.32), new THREE.LineBasicMaterial({ color: base, transparent: true, opacity: 0.18 })));

    const ticks: THREE.Vector3[] = [];
    for (let i = 0; i < 120; i++) {
      const angle = (i / 120) * Math.PI * 2;
      const length = i % 10 === 0 ? 0.16 : 0.07;
      ticks.push(
        new THREE.Vector3(Math.cos(angle) * RADIUS, 0, Math.sin(angle) * RADIUS),
        new THREE.Vector3(Math.cos(angle) * (RADIUS + length), 0, Math.sin(angle) * (RADIUS + length)),
      );
    }
    group.add(
      new THREE.LineSegments(
        new THREE.BufferGeometry().setFromPoints(ticks),
        new THREE.LineBasicMaterial({ color: base, transparent: true, opacity: 0.35 }),
      ),
    );

    const nodeGeometry = new THREE.BoxGeometry(0.07, 0.07, 0.07);
    const entries = SIGNALS.map((label, i) => {
      const angle = (i / SIGNALS.length) * Math.PI * 2;
      const x = Math.cos(angle) * RADIUS;
      const z = Math.sin(angle) * RADIUS;
      const height = 0.75 + (((i * 37) % 7) / 7) * 1.35;

      const lineMaterial = new THREE.LineBasicMaterial({ color: base.clone(), transparent: true, opacity: 0.5 });
      group.add(
        new THREE.Line(
          new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(x, 0, z), new THREE.Vector3(x, height, z)]),
          lineMaterial,
        ),
      );

      const node = new THREE.Mesh(nodeGeometry, new THREE.MeshBasicMaterial({ color: base.clone() }));
      node.position.set(x, height, z);
      group.add(node);

      const { texture, width, height: textHeight } = makeLabelTexture(label);
      const spriteMaterial = new THREE.SpriteMaterial({ map: texture, color: base.clone(), transparent: true, depthWrite: false });
      const sprite = new THREE.Sprite(spriteMaterial);
      sprite.center.set(0.5, 0);
      sprite.position.set(x, height + 0.08, z);
      sprite.scale.set(width * WORLD_PER_PX, textHeight * WORLD_PER_PX, 1);
      group.add(sprite);

      return { sprite, spriteMaterial, lineMaterial, node, highlight: 0 };
    });

    const raycaster = new THREE.Raycaster();
    const ndc = new THREE.Vector2();
    const worldPosition = new THREE.Vector3();
    const sprites = entries.map((entry) => entry.sprite);
    let spin = 0;
    let impulse = 0;

    return {
      pointerDown() {
        impulse += 2.2;
      },
      update(_elapsed, delta) {
        const steer = pointer.inside ? pointer.x * 0.6 : 0;
        impulse *= Math.exp(-delta * 1.6);
        spin += delta * ((reducedMotion ? 0 : 0.12) + steer + impulse);
        group.rotation.y = spin;
        group.rotation.x += ((pointer.inside ? -pointer.y * 0.16 : 0) - group.rotation.x) * (1 - Math.exp(-delta * 3));
        group.updateMatrixWorld();

        let hovered: THREE.Object3D | undefined;
        if (pointer.inside) {
          ndc.set(pointer.x, pointer.y);
          raycaster.setFromCamera(ndc, camera);
          hovered = raycaster.intersectObjects(sprites, false)[0]?.object;
        }

        entries.forEach((entry) => {
          const target = entry.sprite === hovered ? 1 : 0;
          entry.highlight += (target - entry.highlight) * (1 - Math.exp(-delta * 10));
          entry.sprite.getWorldPosition(worldPosition);
          const depth = THREE.MathUtils.clamp((worldPosition.z + RADIUS) / (2 * RADIUS), 0, 1);

          entry.spriteMaterial.color.copy(base).lerp(accent, entry.highlight);
          entry.spriteMaterial.opacity = 0.22 + depth * 0.78;
          entry.lineMaterial.color.copy(base).lerp(accent, entry.highlight);
          entry.lineMaterial.opacity = 0.2 + depth * 0.45 + entry.highlight * 0.35;
          (entry.node.material as THREE.MeshBasicMaterial).color.copy(base).lerp(accent, entry.highlight);
          entry.node.scale.setScalar(1 + entry.highlight * 1.8);
        });
      },
    };
  });

  return <div ref={containerRef} className={className} aria-hidden="true" />;
};
