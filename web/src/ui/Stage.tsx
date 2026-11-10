import { useEffect, useRef, type KeyboardEvent, type PointerEvent as RPointerEvent } from "react";
import type { Player } from "../lib/useFrameClock";
import type { Sketch } from "../lib/data";
import { drawOverlay } from "../lib/overlay";
import type { View } from "../lib/params";
import { wipeFromPointer, wipeKey } from "../lib/wipe";

/** The take under the render; the render and the overlay are clipped by the wipe. */
export function Stage({ sketch, player, frame, wipe, onWipe, view, overlay }: {
  sketch: Sketch; player: Player; frame: number; wipe: number; onWipe: (x: number) => void; view: View; overlay: boolean;
}) {
  const { meta, seam, base } = sketch;
  const stage = useRef<HTMLDivElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const drag = useRef(false);

  // the effective divider: the take-only and render-only views park it at an end
  const x = view === "take" ? 1 : view === "render" ? 0 : wipe;

  // keep the canvas at the displayed size (times the pixel ratio) and redraw for every presented frame
  const draw = useRef<() => void>(() => undefined);
  draw.current = () => {
    const c = canvas.current, s = stage.current;
    if (!c || !s) return;
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    const w = Math.round(s.clientWidth * dpr), h = Math.round(s.clientHeight * dpr);
    if (c.width !== w || c.height !== h) { c.width = w; c.height = h; }
    const ctx = c.getContext("2d");
    if (ctx) drawOverlay(ctx, overlay && view !== "take" ? seam : null, frame, meta.cell, meta.video.width, meta.video.height);
  };
  useEffect(() => { draw.current(); }, [frame, overlay, view, seam]);
  useEffect(() => {
    const s = stage.current;
    if (!s) return;
    const ro = new ResizeObserver(() => draw.current());
    ro.observe(s);
    return () => ro.disconnect();
  }, []);

  const move = (e: RPointerEvent) => {
    const r = stage.current?.getBoundingClientRect();
    if (r) onWipe(wipeFromPointer(e.clientX, r.left, r.width));
  };
  const onKey = (e: KeyboardEvent) => {
    const n = wipeKey(e.key, wipe, e.shiftKey);
    if (n !== null) { e.preventDefault(); onWipe(n); }
  };
  const pct = Math.round(wipe * 100);

  return (
    <div className="stage" ref={stage} role="group" aria-label="The take and the render, compared with a wipe"
      style={{ aspectRatio: `${meta.video.width} / ${meta.video.height}` }}>
      <video ref={player.a} className="stage-video" src={`${base}${meta.video.take}`} muted playsInline preload="auto" aria-label="The take" />
      <div className="stage-top" style={{ clipPath: `inset(0 0 0 ${x * 100}%)` }}>
        <video ref={player.b} className="stage-video" src={`${base}${meta.video.render}`} muted playsInline preload="auto" aria-label="The render" />
        <canvas ref={canvas} className="stage-overlay" aria-hidden="true" data-testid="overlay" />
      </div>
      {view !== "render" && <span className="stage-tag stage-tag-l">take</span>}
      {view !== "take" && <span className="stage-tag stage-tag-r">render</span>}
      {view === "wipe" && (
        <div className="divider" style={{ left: `${wipe * 100}%` }} role="slider" tabIndex={0}
          aria-label="Wipe divider: take on the left, render on the right" aria-orientation="horizontal"
          aria-valuemin={0} aria-valuemax={100} aria-valuenow={pct} aria-valuetext={`take ${pct} percent, render ${100 - pct} percent`}
          onKeyDown={onKey}
          onPointerDown={(e) => { drag.current = true; e.currentTarget.setPointerCapture(e.pointerId); move(e); }}
          onPointerMove={(e) => { if (drag.current) move(e); }}
          onPointerUp={(e) => { drag.current = false; e.currentTarget.releasePointerCapture(e.pointerId); }}
          onPointerCancel={() => { drag.current = false; }}>
          <span className="divider-handle" aria-hidden="true"><i /><i /></span>
        </div>
      )}
    </div>
  );
}
