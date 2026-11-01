import React, { useEffect, useRef } from "react";

const INTERACTIVE = "a, button, input, select, textarea, label, [data-interactive='true'], .editorial-link";

/** Blend-mode cursor with a trailing ring, hover spotlight feed and an iridescent click burst. */
export const Cursor: React.FC = () => {
  const dotRef = useRef<HTMLDivElement>(null);
  const ringRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const target = { x: -100, y: -100 };
    const ring = { x: -100, y: -100 };
    let hovering = false;
    let frame = 0;

    const onMove = (event: MouseEvent) => {
      target.x = event.clientX;
      target.y = event.clientY;
      if (dotRef.current) {
        dotRef.current.style.transform = `translate3d(${target.x}px, ${target.y}px, 0)`;
      }

      const element = event.target as HTMLElement | null;
      const isInteractive = !!element?.closest?.(INTERACTIVE);
      if (isInteractive !== hovering) {
        hovering = isInteractive;
        ringRef.current?.classList.toggle("active", hovering);
      }

      const spot = element?.closest?.<HTMLElement>("[data-spot]");
      if (spot) {
        const rect = spot.getBoundingClientRect();
        spot.style.setProperty("--mx", `${event.clientX - rect.left}px`);
        spot.style.setProperty("--my", `${event.clientY - rect.top}px`);
      }
    };

    const onDown = (event: MouseEvent) => {
      ringRef.current?.classList.add("pressed");
      const burst = document.createElement("span");
      burst.className = "cursor-burst";
      burst.style.left = `${event.clientX}px`;
      burst.style.top = `${event.clientY}px`;
      burst.addEventListener("animationend", () => burst.remove());
      document.body.appendChild(burst);
    };
    const onUp = () => ringRef.current?.classList.remove("pressed");

    const tick = () => {
      ring.x += (target.x - ring.x) * 0.18;
      ring.y += (target.y - ring.y) * 0.18;
      if (ringRef.current) {
        ringRef.current.style.transform = `translate3d(${ring.x}px, ${ring.y}px, 0)`;
      }
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);

    window.addEventListener("mousemove", onMove, { passive: true });
    window.addEventListener("mousedown", onDown);
    window.addEventListener("mouseup", onUp);
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mousedown", onDown);
      window.removeEventListener("mouseup", onUp);
    };
  }, []);

  return (
    <>
      <div ref={dotRef} className="custom-cursor-dot" />
      <div ref={ringRef} className="custom-cursor-ring" />
    </>
  );
};
