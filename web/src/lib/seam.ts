// The seam file: 2 bits per cell per analysis frame (Interfaces, p47-measure/1).
// Layout (this sketch's choice; align with seam/export.py when that exists): frame-major, row-major,
// four cells per byte with cell i in bits 2*(i%4).., each frame padded to a whole byte.
export const NONE = 0, KEPT = 1, LIMNED = 2, CREATURE = 3;
export type Code = 0 | 1 | 2 | 3;

export type CueEvent = { id: string; kind: "cue" | "contact"; t: number; t_end?: number; label: string };
export type SeamMeta = {
  schema: string; synthetic: boolean; label: string; note: string;
  video: { take: string; render: string; width: number; height: number };
  fps: number; frames: number; cell: number; cols: number; rows: number;
  tau: number; kappa_keep: number; min_line_px: number;
  seam: { file: string; format: string; bytes_per_frame: number };
  cues: CueEvent[];
  series: { t: number[]; D: number[]; D0: number[]; contact: number[] };
};

export type Counts = { none: number; kept: number; limned: number; creature: number };

export class Seam {
  readonly bytesPerFrame: number;
  constructor(readonly bytes: Uint8Array, readonly cols: number, readonly rows: number, readonly frames: number) {
    this.bytesPerFrame = Math.ceil((cols * rows) / 4);
    if (cols < 1 || rows < 1 || frames < 1) throw new Error("seam: cols, rows and frames must be positive");
    if (bytes.length !== this.bytesPerFrame * frames) {
      throw new Error(`seam: expected ${this.bytesPerFrame * frames} bytes (${frames} frames x ${this.bytesPerFrame}), got ${bytes.length}`);
    }
  }
  /** The code of the cell at (col, row) in a frame; frames outside the file clamp to its ends. */
  at(frame: number, col: number, row: number): Code {
    if (col < 0 || col >= this.cols || row < 0 || row >= this.rows) throw new RangeError("seam: cell out of range");
    const f = Math.max(0, Math.min(this.frames - 1, Math.trunc(frame)));
    const i = row * this.cols + col;
    return ((this.bytes[f * this.bytesPerFrame + (i >> 2)] >> ((i & 3) * 2)) & 3) as Code;
  }
  counts(frame: number): Counts {
    const c: Counts = { none: 0, kept: 0, limned: 0, creature: 0 };
    for (let r = 0; r < this.rows; r++) for (let q = 0; q < this.cols; q++) {
      const k = this.at(frame, q, r);
      if (k === KEPT) c.kept++; else if (k === LIMNED) c.limned++; else if (k === CREATURE) c.creature++; else c.none++;
    }
    return c;
  }
}

/** Share of the cells that got a verdict that were kept, in percent; null when none did. */
export const keptPercent = (c: Counts): number | null => (c.kept + c.limned === 0 ? null : (100 * c.kept) / (c.kept + c.limned));

export type Summary = {
  pct: (number | null)[];
  mean: number;
  low: { frame: number; pct: number };
  /** The first and last frame below `threshold` percent, if any. */
  below: { from: number; to: number } | null;
  threshold: number;
};

export function summarise(seam: Seam, threshold = 80): Summary {
  const pct: (number | null)[] = [];
  for (let f = 0; f < seam.frames; f++) pct.push(keptPercent(seam.counts(f)));
  const known = pct.map((p, f) => ({ p, f })).filter((x): x is { p: number; f: number } => x.p !== null);
  if (!known.length) throw new Error("seam: no frame has a verdict");
  const mean = known.reduce((a, x) => a + x.p, 0) / known.length;
  const lo = known.reduce((a, x) => (x.p < a.p ? x : a));
  const under = known.filter((x) => x.p < threshold);
  return { pct, mean, low: { frame: lo.f, pct: lo.p }, below: under.length ? { from: under[0].f, to: under[under.length - 1].f } : null, threshold };
}

export function clock(seconds: number): string {
  const s = Math.max(0, seconds);
  const m = Math.floor(s / 60);
  return `${m}:${(s - m * 60).toFixed(1).padStart(4, "0")}`;
}

/** One sentence that says what the overlay shows, for readers who cannot see it. */
export function describe(sum: Summary, fps: number): string {
  const when = (f: number) => clock(f / fps);
  const base = `Across the take, ${sum.mean.toFixed(0)}% of the room's lined cells were kept on average.`;
  const low = `The lowest was ${sum.low.pct.toFixed(0)}% at ${when(sum.low.frame)}.`;
  const dip = sum.below
    ? ` Kept fell below ${sum.threshold}% from ${when(sum.below.from)} to ${when(sum.below.to)}.`
    : ` Kept never fell below ${sum.threshold}%.`;
  return `${base} ${low}${dip}`;
}
