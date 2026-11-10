// The wipe divider: its position as a share of the stage width, 0 (all render) to 1 (all take).
// The ends stay a hair inside so the handle never leaves the stage.
export const WIPE_MIN = 0.02;
export const WIPE_MAX = 0.98;
export const WIPE_STEP = 0.02;
export const WIPE_STEP_BIG = 0.1;

/** Clamp a position; NaN and Infinity fall back to the middle. */
export function clampWipe(x: number): number {
  if (!Number.isFinite(x)) return 0.5;
  return Math.min(WIPE_MAX, Math.max(WIPE_MIN, x));
}

/** A pointer's x on the stage as a wipe position. A stage with no width gives the middle. */
export function wipeFromPointer(clientX: number, left: number, width: number): number {
  return width > 0 ? clampWipe((clientX - left) / width) : 0.5;
}

/** A key on the slider: the new position, or null when the key is not ours. */
export function wipeKey(key: string, x: number, shift = false): number | null {
  const step = shift ? WIPE_STEP_BIG : WIPE_STEP;
  switch (key) {
    case "ArrowLeft": case "ArrowDown": return clampWipe(x - step);
    case "ArrowRight": case "ArrowUp": return clampWipe(x + step);
    case "PageDown": return clampWipe(x - WIPE_STEP_BIG);
    case "PageUp": return clampWipe(x + WIPE_STEP_BIG);
    case "Home": return WIPE_MIN;
    case "End": return WIPE_MAX;
    default: return null;
  }
}
