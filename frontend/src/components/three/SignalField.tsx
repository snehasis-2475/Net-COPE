import React, { useRef } from "react";
import * as THREE from "three";
import { useThreeStage } from "./useThreeStage";
import { INK, IRIDESCENT_GLSL, PAPER } from "./palette";

const COLS = 150;
const ROWS = 84;
const WIDTH = 24;
const HEIGHT = 13.5;
const SPLASH_COUNT = 4;
const TILT = -0.62;

const vertexShader = /* glsl */ `
  uniform float uTime;
  uniform float uClock;
  uniform vec2 uMouse;
  uniform float uHover;
  uniform vec4 uSplash[${SPLASH_COUNT}];
  uniform float uSize;
  uniform float uPixelRatio;
  varying float vGlow;
  varying float vHue;
  varying float vDepth;

  void main() {
    vec3 p = position;
    float drift = sin(p.x * 0.42 + uTime * 0.55) * 0.32
      + cos(p.y * 0.65 - uTime * 0.4) * 0.26
      + sin((p.x - p.y) * 0.28 + uTime * 0.25) * 0.38;
    float d = distance(p.xy, uMouse);
    float bump = exp(-d * d * 0.32) * uHover;

    float ring = 0.0;
    for (int i = 0; i < ${SPLASH_COUNT}; i++) {
      float age = uClock - uSplash[i].z;
      if (age > 0.0 && age < 3.5) {
        float dd = distance(p.xy, uSplash[i].xy);
        ring += exp(-pow((dd - age * 3.4) * 1.8, 2.0)) * (1.0 - age / 3.5) * uSplash[i].w;
      }
    }

    p.z += drift + bump * 1.5 + ring * 0.8;
    vGlow = clamp(bump * 1.15 + ring, 0.0, 1.0);
    vHue = p.x * 0.035 + p.y * 0.02 + d * 0.06;

    vec4 mv = modelViewMatrix * vec4(p, 1.0);
    vDepth = smoothstep(22.0, 6.0, -mv.z);
    gl_PointSize = uSize * uPixelRatio * (1.0 + vGlow * 1.6) * (11.0 / -mv.z);
    gl_Position = projectionMatrix * mv;
  }
`;

const fragmentShader = /* glsl */ `
  uniform vec3 uBase;
  uniform float uBaseAlpha;
  uniform float uTime;
  varying float vGlow;
  varying float vHue;
  varying float vDepth;
  ${IRIDESCENT_GLSL}

  void main() {
    float r = length(gl_PointCoord - 0.5);
    if (r > 0.5) discard;
    float soft = 1.0 - smoothstep(0.32, 0.5, r);
    float splash = smoothstep(0.04, 0.55, vGlow);
    vec3 color = mix(uBase, iridescent(vHue + uTime * 0.04 + vGlow * 0.35), splash);
    float alpha = mix(uBaseAlpha * (0.45 + 0.55 * vDepth), 1.0, splash) * soft;
    gl_FragColor = vec4(color, alpha);
  }
`;

interface SignalFieldProps {
  /** "dark" renders pale points for ink backgrounds; "light" renders ink points for paper. */
  tone?: "dark" | "light";
  className?: string;
}

/** Undulating point-cloud surface that bulges and splashes colour under the cursor. */
export const SignalField: React.FC<SignalFieldProps> = ({ tone = "dark", className }) => {
  const containerRef = useRef<HTMLDivElement>(null);

  useThreeStage(containerRef, ({ scene, camera, pointer, renderer, reducedMotion }) => {
    camera.position.set(0, 0, 12);
    camera.lookAt(0, 0, 0);

    const positions = new Float32Array(COLS * ROWS * 3);
    let offset = 0;
    for (let row = 0; row < ROWS; row++) {
      for (let col = 0; col < COLS; col++) {
        positions[offset++] = (col / (COLS - 1) - 0.5) * WIDTH;
        positions[offset++] = (row / (ROWS - 1) - 0.5) * HEIGHT;
        positions[offset++] = 0;
      }
    }
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));

    const splashes = Array.from({ length: SPLASH_COUNT }, () => new THREE.Vector4(0, 0, -100, 0));
    const uniforms = {
      uTime: { value: 0 },
      uClock: { value: 0 },
      uMouse: { value: new THREE.Vector2(999, 999) },
      uHover: { value: 0 },
      uSplash: { value: splashes },
      uSize: { value: 2.4 },
      uPixelRatio: { value: renderer.getPixelRatio() },
      uBase: { value: new THREE.Color(tone === "dark" ? PAPER : INK) },
      uBaseAlpha: { value: tone === "dark" ? 0.42 : 0.26 },
    };
    const material = new THREE.ShaderMaterial({
      uniforms,
      vertexShader,
      fragmentShader,
      transparent: true,
      depthWrite: false,
    });
    const points = new THREE.Points(geometry, material);
    points.rotation.x = TILT;
    scene.add(points);

    const raycaster = new THREE.Raycaster();
    const ndc = new THREE.Vector2();
    const plane = new THREE.Plane();
    const normal = new THREE.Vector3();
    const hit = new THREE.Vector3();
    const mouseLocal = new THREE.Vector2(999, 999);
    let splashIndex = 0;
    let lastAutoSplash = 0;

    const addSplash = (strength: number) => {
      if (mouseLocal.x > 900) return;
      splashes[splashIndex].set(mouseLocal.x, mouseLocal.y, uniforms.uClock.value, strength);
      splashIndex = (splashIndex + 1) % SPLASH_COUNT;
    };

    return {
      resize(width, height) {
        const visibleHeight = 2 * camera.position.z * Math.tan(THREE.MathUtils.degToRad(camera.fov / 2));
        const visibleWidth = visibleHeight * (width / height);
        points.scale.set(Math.max(0.6, (visibleWidth * 1.2) / WIDTH), (visibleHeight * 1.4) / HEIGHT, 1);
      },
      pointerDown() {
        addSplash(1.2);
      },
      update(elapsed, delta) {
        uniforms.uClock.value = elapsed;
        uniforms.uTime.value = reducedMotion ? 0 : elapsed;

        points.rotation.x = TILT + pointer.y * 0.04;
        points.rotation.z = pointer.x * 0.03;
        points.updateMatrixWorld();

        if (pointer.inside) {
          ndc.set(pointer.x, pointer.y);
          raycaster.setFromCamera(ndc, camera);
          normal.set(0, 0, 1).applyQuaternion(points.quaternion);
          plane.setFromNormalAndCoplanarPoint(normal, points.position);
          if (raycaster.ray.intersectPlane(plane, hit)) {
            points.worldToLocal(hit);
            mouseLocal.set(hit.x, hit.y);
          }
        }
        const mouse = uniforms.uMouse.value;
        if (mouse.x > 900) mouse.copy(mouseLocal);
        else mouse.lerp(mouseLocal, 1 - Math.exp(-delta * 8));

        const targetHover = pointer.inside ? 0.55 + pointer.energy * 0.9 : 0;
        uniforms.uHover.value += (targetHover - uniforms.uHover.value) * (1 - Math.exp(-delta * 4));

        if (pointer.inside && pointer.energy > 0.35 && elapsed - lastAutoSplash > 0.55) {
          addSplash(0.55);
          lastAutoSplash = elapsed;
        }
      },
    };
  });

  return <div ref={containerRef} className={className} aria-hidden="true" />;
};
