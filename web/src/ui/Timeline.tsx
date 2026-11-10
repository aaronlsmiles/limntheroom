import { useMemo, useRef, type KeyboardEvent, type PointerEvent as RPointerEvent } from "react";
import type { SeamMeta } from "../lib/seam";
import { clock } from "../lib/seam";
import type { Summary } from "../lib/seam";
import { useWidth } from "../lib/useSize";

const PAD = { l: 44, r: 10, top: 22, mid: 16, bottom: 22 };
const H_D = 64, H_K = 46;
const HEIGHT = PAD.top + H_D + PAD.mid + H_K + PAD.bottom;

/** Drift and kept over time, with the contact windows shaded and the cues marked. A click or drag seeks. */
export function Timeline({ meta, summary, frame, onSeek, onStep }: {
  meta: SeamMeta; summary: Summary; frame: number; onSeek: (f: number) => void; onStep: (d: number) => void;
}) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const drag = useRef(false);
  const { fps, frames, series } = meta;
  const dur = frames / fps;
  const w = Math.max(240, width);
  const iw = w - PAD.l - PAD.r;
  const X = (t: number) => PAD.l + (t / dur) * iw;
  const dMax = useMemo(() => Math.ceil(Math.max(...series.D, ...series.D0) * 1.15 * 2) / 2, [series]);
  const kMin = useMemo(() => Math.max(0, Math.min(80, Math.floor((summary.low.pct - 5) / 10) * 10)), [summary]);
  const yD = (v: number) => PAD.top + H_D - (v / dMax) * H_D;
  const yK = (p: number) => PAD.top + H_D + PAD.mid + H_K - ((p - kMin) / (100 - kMin)) * H_K;
  const line = (xs: number[], ys: number[]) => xs.map((x, i) => `${i ? "L" : "M"}${x.toFixed(1)},${ys[i].toFixed(1)}`).join("");
  const tx = useMemo(() => series.t.map((t) => X(t + 0.5 / fps)), [series.t, w]); // eslint-disable-line react-hooks/exhaustive-deps
  const dPath = useMemo(() => line(tx, series.D.map(yD)), [tx, series.D, dMax]); // eslint-disable-line react-hooks/exhaustive-deps
  const d0Path = useMemo(() => line(tx, series.D0.map(yD)), [tx, series.D0, dMax]); // eslint-disable-line react-hooks/exhaustive-deps
  const kPts = summary.pct.map((p, i) => (p === null ? null : [tx[i], yK(p)] as const)).filter((p): p is readonly [number, number] => p !== null);
  const kPath = kPts.map((p, i) => `${i ? "L" : "M"}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join("");
    const ticks = Array.from({ length: Math.floor(dur / 2) + 1 }, (_, i) => i * 2);
  const contacts = meta.cues.filter((c) => c.kind === "contact");
  const cues = meta.cues.filter((c) => c.kind === "cue");
  const px = X((frame + 0.5) / fps);

  const seekAt = (e: RPointerEvent<HTMLDivElement>) => {
    const r = e.currentTarget.getBoundingClientRect();
    const t = ((e.clientX - r.left - PAD.l) / iw) * dur;
    onSeek(Math.max(0, Math.min(frames - 1, Math.floor(t * fps))));
  };
  const onKey = (e: KeyboardEvent) => {
    const big = e.shiftKey ? fps : 1;
    if (e.key === "ArrowRight" || e.key === "ArrowUp") { e.preventDefault(); onStep(big); }
    else if (e.key === "ArrowLeft" || e.key === "ArrowDown") { e.preventDefault(); onStep(-big); }
    else if (e.key === "Home") { e.preventDefault(); onSeek(0); }
    else if (e.key === "End") { e.preventDefault(); onSeek(frames - 1); }
  };

  return (
    <div ref={ref} className="timeline" role="slider" tabIndex={0} aria-label="Playhead" aria-valuemin={0} aria-valuemax={frames - 1}
      aria-valuenow={frame} aria-valuetext={`${clock(frame / fps)}, frame ${frame + 1} of ${frames}`} onKeyDown={onKey}
      onPointerDown={(e) => { drag.current = true; e.currentTarget.setPointerCapture(e.pointerId); seekAt(e); }}
      onPointerMove={(e) => { if (drag.current) seekAt(e); }}
      onPointerUp={(e) => { drag.current = false; e.currentTarget.releasePointerCapture(e.pointerId); }}
      onPointerCancel={() => { drag.current = false; }}>
      <p className="tl-key small muted"><span><i className="k-ink" aria-hidden="true" />line drift, px (codec floor dashed)</span><span><i className="k-gold" aria-hidden="true" />room kept, % of cells with a verdict</span></p>
      <svg width={w} height={HEIGHT} viewBox={`0 0 ${w} ${HEIGHT}`} aria-hidden="true" focusable="false">
        {contacts.map((c) => (
          <g key={c.id}>
            <rect className="tl-contact" x={X(c.t)} y={PAD.top - 6} width={X(c.t_end ?? c.t) - X(c.t)} height={yK(kMin) - PAD.top + 6} />
            <text className="tl-label" x={X(c.t) + 4} y={PAD.top - 9}>{c.label}</text>
          </g>
        ))}
        <g className="tl-axis">
          <line x1={PAD.l} x2={w - PAD.r} y1={yD(0)} y2={yD(0)} />
          <line x1={PAD.l} x2={w - PAD.r} y1={yK(kMin)} y2={yK(kMin)} />
          <text x={PAD.l - 6} y={yD(dMax) + 9} textAnchor="end">{dMax.toFixed(1)}</text>
          <text x={PAD.l - 6} y={yD(0)} textAnchor="end">0</text>
          <text x={PAD.l - 6} y={yK(100) + 9} textAnchor="end">100</text>
          <text x={PAD.l - 6} y={yK(kMin)} textAnchor="end">{kMin}</text>
          {ticks.map((t) => (
            <g key={t}>
              <line x1={X(t)} x2={X(t)} y1={yK(kMin)} y2={yK(kMin) + 4} />
              <text x={X(t)} y={yK(kMin) + 16} textAnchor={t === 0 ? "start" : t >= dur - 0.01 ? "end" : "middle"}>{`${t}s`}</text>
            </g>
          ))}
        </g>
        <path className="tl-d0" d={d0Path} />
        <path className="tl-d" d={dPath} />
        <path className="tl-k" d={kPath} />
        {cues.map((c, i) => (
          <g key={c.id}>
            <line className="tl-cue" x1={X(c.t)} x2={X(c.t)} y1={PAD.top - 6} y2={yK(kMin)} />
            <rect className="tl-flag" x={X(c.t) - 8} y={PAD.top - 20} width={16} height={14} />
            <text className="tl-flagtext" x={X(c.t)} y={PAD.top - 13} dy=".36em" textAnchor="middle">{i + 1}</text>
          </g>
        ))}
        <line className="tl-head" x1={px} x2={px} y1={PAD.top - 6} y2={yK(kMin)} />
        <rect className="tl-headcap" x={px - 4} y={yK(kMin) - 1} width={8} height={5} />
      </svg>
    </div>
  );
}
