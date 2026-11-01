import { useEffect, useRef, type RefObject } from "react";
import * as THREE from "three";

export interface StagePointer {
  /** Smoothed pointer position relative to the stage, in normalized device coordinates (-1..1). */
  x: number;
  y: number;
  targetX: number;
  targetY: number;
  inside: boolean;
  /** Recent pointer speed (0..1); decays every frame. */
  energy: number;
}

export interface StageContext {
  renderer: THREE.WebGLRenderer;
  scene: THREE.Scene;
  camera: THREE.PerspectiveCamera;
  pointer: StagePointer;
  reducedMotion: boolean;
}

export interface StageHandlers {
  update?: (elapsed: number, delta: number) => void;
  resize?: (width: number, height: number) => void;
  pointerDown?: () => void;
}

const disposeObject = (object: THREE.Object3D) => {
  const renderable = object as Partial<THREE.Mesh>;
  renderable.geometry?.dispose();
  const materials = renderable.material
    ? Array.isArray(renderable.material)
      ? renderable.material
      : [renderable.material]
    : [];
  materials.forEach((material) => {
    (material as THREE.MeshBasicMaterial).map?.dispose();
    material.dispose();
  });
};

/**
 * Mounts a transparent WebGL canvas inside `containerRef` and runs a render loop that
 * pauses offscreen. Pointer tracking is window-level so the canvas never blocks UI events.
 */
export function useThreeStage(
  containerRef: RefObject<HTMLElement | null>,
  setup: (ctx: StageContext) => StageHandlers,
) {
  const setupRef = useRef(setup);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: "high-performance" });
    } catch {
      return; // WebGL unavailable: the decorative layer is simply omitted.
    }
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.75));
    renderer.setClearColor(0x000000, 0);
    renderer.domElement.style.cssText = "display:block;width:100%;height:100%;";
    renderer.domElement.setAttribute("aria-hidden", "true");
    container.appendChild(renderer.domElement);

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(35, 1, 0.1, 100);
    const pointer: StagePointer = { x: 0, y: 0, targetX: 0, targetY: 0, inside: false, energy: 0 };
    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const handlers = setupRef.current({ renderer, scene, camera, pointer, reducedMotion });

    const resize = () => {
      const width = Math.max(1, container.clientWidth);
      const height = Math.max(1, container.clientHeight);
      renderer.setSize(width, height, false);
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
      handlers.resize?.(width, height);
    };
    resize();
    const resizeObserver = new ResizeObserver(resize);
    resizeObserver.observe(container);

    let lastX = 0;
    let lastY = 0;
    const onMove = (event: PointerEvent) => {
      const rect = container.getBoundingClientRect();
      if (rect.width === 0 || rect.height === 0) return;
      pointer.targetX = ((event.clientX - rect.left) / rect.width) * 2 - 1;
      pointer.targetY = -(((event.clientY - rect.top) / rect.height) * 2 - 1);
      pointer.inside = Math.abs(pointer.targetX) <= 1 && Math.abs(pointer.targetY) <= 1;
      pointer.energy = Math.min(1, pointer.energy + Math.hypot(event.clientX - lastX, event.clientY - lastY) / 420);
      lastX = event.clientX;
      lastY = event.clientY;
    };
    const onDown = (event: PointerEvent) => {
      onMove(event);
      if (pointer.inside) handlers.pointerDown?.();
    };
    const onLeave = () => {
      pointer.inside = false;
    };
    window.addEventListener("pointermove", onMove, { passive: true });
    window.addEventListener("pointerdown", onDown, { passive: true });
    document.documentElement.addEventListener("pointerleave", onLeave);

    let visible = true;
    const intersectionObserver = new IntersectionObserver(
      ([entry]) => {
        visible = entry.isIntersecting;
      },
      { rootMargin: "120px" },
    );
    intersectionObserver.observe(container);

    const clock = new THREE.Clock();
    let elapsed = 0;
    let frame = 0;
    const tick = () => {
      frame = requestAnimationFrame(tick);
      const delta = Math.min(clock.getDelta(), 0.05);
      if (!visible || document.hidden) return;
      elapsed += delta;
      const ease = 1 - Math.exp(-delta * 6);
      pointer.x += (pointer.targetX - pointer.x) * ease;
      pointer.y += (pointer.targetY - pointer.y) * ease;
      pointer.energy *= Math.exp(-delta * 2.4);
      handlers.update?.(elapsed, delta);
      renderer.render(scene, camera);
    };
    frame = requestAnimationFrame(tick);

    return () => {
      cancelAnimationFrame(frame);
      resizeObserver.disconnect();
      intersectionObserver.disconnect();
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerdown", onDown);
      document.documentElement.removeEventListener("pointerleave", onLeave);
      scene.traverse(disposeObject);
      renderer.dispose();
      renderer.domElement.remove();
    };
  }, [containerRef]);
}
