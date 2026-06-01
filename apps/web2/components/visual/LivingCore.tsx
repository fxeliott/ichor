"use client";

import { useEffect, useRef } from "react";

/**
 * LivingCore — bespoke animated "living macro entity" illustration.
 *
 * A luminous pulsing core with data-nodes in elliptical orbit, each tethered
 * to the core by a flux line carrying a traveling pulse, over a faint drifting
 * particle field. Canvas 2D, devicePixelRatio-aware, pauses when off-screen or
 * the tab is hidden, and renders a single static frame under
 * prefers-reduced-motion. Pure decoration (aria-hidden) — no semantic content.
 *
 * Refonte 2026 (Aurora cobalt) — the hero centerpiece. Cobalt/azure palette
 * to match --accent. GPU-light (a handful of arcs + gradients per frame).
 */
export function LivingCore({ className = "", nodes = 7 }: { className?: string; nodes?: number }) {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const node = ref.current;
    if (!node) return;
    // Non-nullable capture for the nested closures (see ctx note below).
    const canvas: HTMLCanvasElement = node;
    const maybeCtx = canvas.getContext("2d");
    if (!maybeCtx) return;
    // Non-nullable capture so the nested draw()/resize() closures don't lose
    // the narrowing (TS doesn't carry control-flow narrowing into closures).
    const ctx: CanvasRenderingContext2D = maybeCtx;

    const reduce =
      typeof window !== "undefined" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    const COBALT = "rgba(96,156,255,";
    const AZURE = "rgba(130,205,255,";
    const INK = "rgba(232,242,255,";

    let dpr = Math.min(window.devicePixelRatio || 1, 2);
    let w = 0;
    let h = 0;
    let t = 0;
    let rafId = 0;
    let running = false;

    type Orbiter = { angle: number; speed: number; phase: number };
    const orbiters: Orbiter[] = Array.from({ length: nodes }, (_, i) => ({
      angle: (i / nodes) * Math.PI * 2,
      speed: 0.06 + Math.random() * 0.05,
      phase: Math.random() * Math.PI * 2,
    }));

    type Particle = { x: number; y: number; vx: number; vy: number; r: number; a: number };
    let particles: Particle[] = [];

    function resize() {
      const rect = canvas.getBoundingClientRect();
      w = rect.width;
      h = rect.height;
      if (w === 0 || h === 0) return;
      canvas.width = Math.round(w * dpr);
      canvas.height = Math.round(h * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      const count = Math.min(64, Math.round((w * h) / 15000));
      particles = Array.from({ length: count }, () => ({
        x: Math.random() * w,
        y: Math.random() * h,
        vx: (Math.random() - 0.5) * 0.14,
        vy: (Math.random() - 0.5) * 0.14,
        r: Math.random() * 1.3 + 0.3,
        a: Math.random() * 0.45 + 0.12,
      }));
    }

    function draw() {
      if (w === 0 || h === 0) {
        resize();
        if (w === 0 || h === 0) return;
      }
      if (!reduce) t += 0.016;
      ctx.clearRect(0, 0, w, h);
      const cx = w * 0.5;
      const cy = h * 0.5;
      const minDim = Math.min(w, h);
      const orbitR = minDim * 0.34;

      // particle field
      for (const p of particles) {
        if (!reduce) {
          p.x += p.vx;
          p.y += p.vy;
          if (p.x < 0) p.x += w;
          else if (p.x > w) p.x -= w;
          if (p.y < 0) p.y += h;
          else if (p.y > h) p.y -= h;
        }
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
        ctx.fillStyle = COBALT + p.a * 0.6 + ")";
        ctx.fill();
      }

      // flux lines + orbiting nodes
      for (const o of orbiters) {
        const ang = o.angle + (reduce ? 0 : t * o.speed * 0.5);
        const wobble = Math.sin(t * 1.1 + o.phase) * 0.05;
        const r = orbitR * (1 + wobble);
        const nx = cx + Math.cos(ang) * r * 1.18;
        const ny = cy + Math.sin(ang) * r * 0.74;

        const grad = ctx.createLinearGradient(cx, cy, nx, ny);
        grad.addColorStop(0, COBALT + "0)");
        grad.addColorStop(1, COBALT + "0.22)");
        ctx.beginPath();
        ctx.moveTo(cx, cy);
        ctx.lineTo(nx, ny);
        ctx.strokeStyle = grad;
        ctx.lineWidth = 1;
        ctx.stroke();

        const pulseT = Math.sin(t * 1.4 + o.phase) * 0.5 + 0.5;
        const px = cx + (nx - cx) * pulseT;
        const py = cy + (ny - cy) * pulseT;
        ctx.beginPath();
        ctx.arc(px, py, 1.6, 0, Math.PI * 2);
        ctx.fillStyle = AZURE + "0.85)";
        ctx.fill();

        const ng = ctx.createRadialGradient(nx, ny, 0, nx, ny, 11);
        ng.addColorStop(0, AZURE + "0.85)");
        ng.addColorStop(1, COBALT + "0)");
        ctx.beginPath();
        ctx.arc(nx, ny, 11, 0, Math.PI * 2);
        ctx.fillStyle = ng;
        ctx.fill();
        ctx.beginPath();
        ctx.arc(nx, ny, 2.3, 0, Math.PI * 2);
        ctx.fillStyle = INK + "0.95)";
        ctx.fill();
      }

      // pulsing core
      const pulse = reduce ? 1 : Math.sin(t * 1.5) * 0.5 + 0.5;
      const coreR = minDim * 0.13 * (0.9 + pulse * 0.18);
      const cg = ctx.createRadialGradient(cx, cy, 0, cx, cy, coreR * 2.6);
      cg.addColorStop(0, INK + "0.95)");
      cg.addColorStop(0.22, COBALT + "0.5)");
      cg.addColorStop(1, COBALT + "0)");
      ctx.beginPath();
      ctx.arc(cx, cy, coreR * 2.6, 0, Math.PI * 2);
      ctx.fillStyle = cg;
      ctx.fill();
      ctx.beginPath();
      ctx.arc(cx, cy, coreR * 0.5, 0, Math.PI * 2);
      ctx.fillStyle = INK + "0.95)";
      ctx.fill();
    }

    function loop() {
      if (!running) return;
      draw();
      rafId = requestAnimationFrame(loop);
    }
    function start() {
      if (running || reduce) return;
      running = true;
      rafId = requestAnimationFrame(loop);
    }
    function stop() {
      running = false;
      cancelAnimationFrame(rafId);
    }

    resize();
    draw(); // first paint (also the static frame under reduced-motion)
    start();

    const onResize = () => {
      dpr = Math.min(window.devicePixelRatio || 1, 2);
      resize();
      draw();
    };
    const onVisibility = () => {
      if (document.hidden) stop();
      else start();
    };
    window.addEventListener("resize", onResize);
    document.addEventListener("visibilitychange", onVisibility);

    const io = new IntersectionObserver(
      (entries) => {
        const visible = entries[0]?.isIntersecting ?? true;
        if (visible) start();
        else stop();
      },
      { threshold: 0 },
    );
    io.observe(canvas);

    return () => {
      stop();
      window.removeEventListener("resize", onResize);
      document.removeEventListener("visibilitychange", onVisibility);
      io.disconnect();
    };
  }, [nodes]);

  return <canvas ref={ref} aria-hidden className={`block h-full w-full ${className}`} />;
}
