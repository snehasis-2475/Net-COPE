import React, { useRef } from "react";
import * as THREE from "three";
import { useThreeStage } from "./useThreeStage";
import { IRIDESCENT_GLSL } from "./palette";

const LENGTH = 16;

const vertexShader = /* glsl */ `
  uniform float uTime;
  uniform vec2 uMouse;
  uniform float uHover;
  varying vec3 vNormal;
  varying vec3 vView;
  varying vec2 vUv;
  varying float vBulge;

  float bulgeAt(float x) {
    return exp(-pow(x - uMouse.x * 7.5, 2.0) * 0.18) * uHover;
  }

  vec3 shape(vec3 p) {
    float bulge = bulgeAt(p.x);
    float twist = sin(p.x * 0.32 + uTime * 0.35) * 1.25 + bulge * 1.4 * uMouse.y;
    vec3 q = vec3(p.x, p.y * cos(twist), p.y * sin(twist));
    q.y += sin(p.x * 0.55 + uTime * 0.6) * 0.75 + sin(p.x * 1.2 - uTime * 0.45) * 0.22;
    q.y += bulge * 0.45 * uMouse.y;
    q.z += cos(p.x * 0.42 + uTime * 0.5) * 0.9 + bulge * 1.3;
    return q;
  }

  void main() {
    vec3 p = shape(position);
    vec3 px = shape(position + vec3(0.04, 0.0, 0.0));
    vec3 py = shape(position + vec3(0.0, 0.04, 0.0));
    vec4 mv = modelViewMatrix * vec4(p, 1.0);
    vNormal = normalize(normalMatrix * normalize(cross(px - p, py - p)));
    vView = normalize(-mv.xyz);
    vUv = uv;
    vBulge = bulgeAt(position.x);
    gl_Position = projectionMatrix * mv;
  }
`;

const fragmentShader = /* glsl */ `
  uniform float uTime;
  varying vec3 vNormal;
  varying vec3 vView;
  varying vec2 vUv;
  varying float vBulge;
  ${IRIDESCENT_GLSL}

  void main() {
    vec3 n = normalize(vNormal);
    if (!gl_FrontFacing) n = -n;
    vec3 v = normalize(vView);
    float fresnel = pow(1.0 - abs(dot(n, v)), 1.6);
    vec3 color = iridescent(fresnel * 0.9 + vUv.x * 0.55 + uTime * 0.03 + vBulge * 0.3);

    vec3 light = normalize(vec3(0.3, 0.8, 0.6));
    float diffuse = 0.35 + 0.65 * max(dot(n, light), 0.0);
    float specular = pow(max(dot(n, normalize(light + v)), 0.0), 48.0);
    color = color * diffuse + specular * vec3(1.0, 0.86, 0.95) * 0.9 + fresnel * 0.25 * vec3(1.0, 0.6, 0.9);

    float edges = smoothstep(0.0, 0.06, vUv.y) * smoothstep(1.0, 0.94, vUv.y);
    float ends = smoothstep(0.0, 0.1, vUv.x) * smoothstep(1.0, 0.9, vUv.x);
    gl_FragColor = vec4(color, edges * ends);
  }
`;

/** Iridescent twisting signal surface; the cursor lifts and twists the ribbon beneath it. */
export const SignalRibbon: React.FC<{ className?: string }> = ({ className }) => {
  const containerRef = useRef<HTMLDivElement>(null);

  useThreeStage(containerRef, ({ scene, camera, pointer, reducedMotion }) => {
    camera.position.set(0, 0, 9);
    camera.lookAt(0, 0, 0);

    const uniforms = {
      uTime: { value: 0 },
      uMouse: { value: new THREE.Vector2() },
      uHover: { value: 0 },
    };
    const ribbon = new THREE.Mesh(
      new THREE.PlaneGeometry(LENGTH, 1.8, 320, 24),
      new THREE.ShaderMaterial({ uniforms, vertexShader, fragmentShader, transparent: true, side: THREE.DoubleSide }),
    );
    ribbon.rotation.z = -0.06;
    scene.add(ribbon);

    let time = 0;
    return {
      resize(width, height) {
        const visibleHeight = 2 * camera.position.z * Math.tan(THREE.MathUtils.degToRad(camera.fov / 2));
        ribbon.scale.x = Math.max(0.7, (visibleHeight * (width / height) * 1.05) / LENGTH);
      },
      update(_elapsed, delta) {
        time += delta * ((reducedMotion ? 0 : 1) + pointer.energy * 1.5);
        uniforms.uTime.value = time;
        uniforms.uMouse.value.set(pointer.x, pointer.y);
        const targetHover = pointer.inside ? 1 : 0;
        uniforms.uHover.value += (targetHover - uniforms.uHover.value) * (1 - Math.exp(-delta * 3));
      },
    };
  });

  return <div ref={containerRef} className={className} aria-hidden="true" />;
};
