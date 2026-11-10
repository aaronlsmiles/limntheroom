// The seam overlay: gold tint on kept cells, ink hatching on limned ones, a thin outline on the creature's.
// Colours are fixed (not themed): the video underneath is always paper, so the overlay is always gold on paper.
import { CREATURE, KEPT, LIMNED, type Seam } from "./seam";

export const GOLD = "#c4922a";
export const GOLD_LINE = "#9a6a12";
export const INK = "#1c1915";

let hatch: { key: number; pattern: CanvasPattern } | null = null;
function hatchPattern(ctx: CanvasRenderingContext2D, scale: number): CanvasPattern | null {
  const size = Math.max(4, Math.round(6 * scale));
  if (hatch && hatch.key === size) return hatch.pattern;
  const c = document.createElement("canvas");
  c.width = c.height = size;
  const g = c.getContext("2d");
  if (!g) return null;
  g.strokeStyle = INK;
  g.globalAlpha = 0.8;
  g.lineWidth = Math.max(1, scale);
  g.beginPath();
  g.moveTo(-1, size + 1); g.lineTo(size + 1, -1);
  g.moveTo(-1, 1); g.lineTo(1, -1);
  g.moveTo(size - 1, size + 1); g.lineTo(size + 1, size - 1);
  g.stroke();
  const pattern = ctx.createPattern(c, "repeat");
  if (pattern) hatch = { key: size, pattern };
  return pattern;
}

export function drawOverlay(ctx: CanvasRenderingContext2D, seam: Seam | null, frame: number, cell: number, vw: number, vh: number) {
  const { width: W, height: H } = ctx.canvas;
  ctx.clearRect(0, 0, W, H);
  if (!seam) return;
  const sx = W / vw, sy = H / vh;
  const scale = Math.max(1, W / 1280);
  const pat = hatchPattern(ctx, scale);
  for (let r = 0; r < seam.rows; r++) {
    for (let c = 0; c < seam.cols; c++) {
      const k = seam.at(frame, c, r);
      if (k === 0) continue;
      const x = c * cell * sx, y = r * cell * sy, w = cell * sx, h = Math.min(cell, vh - r * cell) * sy;
      if (k === KEPT) {
        ctx.globalAlpha = 0.24; ctx.fillStyle = GOLD; ctx.fillRect(x, y, w, h);
        // the gold line runs only where a kept region ends, so a field of kept cells reads as one tint
        const edge = (dc: number, dr: number) => c + dc < 0 || c + dc >= seam.cols || r + dr < 0 || r + dr >= seam.rows || seam.at(frame, c + dc, r + dr) !== KEPT;
        ctx.globalAlpha = 0.7; ctx.strokeStyle = GOLD_LINE; ctx.lineWidth = Math.max(1, scale * 0.9);
        ctx.beginPath();
        if (edge(0, -1)) { ctx.moveTo(x, y + 0.5); ctx.lineTo(x + w, y + 0.5); }
        if (edge(0, 1)) { ctx.moveTo(x, y + h - 0.5); ctx.lineTo(x + w, y + h - 0.5); }
        if (edge(-1, 0)) { ctx.moveTo(x + 0.5, y); ctx.lineTo(x + 0.5, y + h); }
        if (edge(1, 0)) { ctx.moveTo(x + w - 0.5, y); ctx.lineTo(x + w - 0.5, y + h); }
        ctx.stroke();
      } else if (k === LIMNED) {
        ctx.globalAlpha = 0.5; ctx.fillStyle = "#ecebe7"; ctx.fillRect(x, y, w, h);
        ctx.globalAlpha = 1; if (pat) { ctx.fillStyle = pat; ctx.fillRect(x, y, w, h); }
      } else if (k === CREATURE) {
        ctx.globalAlpha = 0.55; ctx.strokeStyle = INK; ctx.lineWidth = Math.max(1, scale * 0.75);
        ctx.setLineDash([3 * scale, 3 * scale]); ctx.strokeRect(x + 0.5, y + 0.5, w - 1, h - 1); ctx.setLineDash([]);
      }
    }
  }
  ctx.globalAlpha = 1;
}
