// Deep-link parameters: ?frame=75&wipe=0.5&pause=1&view=wipe|take|render&overlay=0
import { clampWipe } from "./wipe";

export type View = "wipe" | "take" | "render";
export type Params = { frame: number | null; wipe: number; pause: boolean; view: View; overlay: boolean; capture: boolean };

export function parseParams(search: string, frames: number): Params {
  const q = new URLSearchParams(search);
  const f = q.get("frame");
  const n = f === null || f.trim() === "" ? NaN : Number(f);
  const w = q.get("wipe");
  const v = q.get("view");
  return {
    frame: Number.isFinite(n) ? Math.max(0, Math.min(frames - 1, Math.trunc(n))) : null,
    wipe: w === null || w.trim() === "" ? 0.5 : clampWipe(Number(w)),
    pause: q.get("pause") === "1",
    view: v === "take" || v === "render" ? v : "wipe",
    overlay: q.get("overlay") !== "0",
    capture: q.get("capture") === "1",
  };
}
