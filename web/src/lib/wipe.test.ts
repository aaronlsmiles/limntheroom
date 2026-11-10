import { describe, expect, it } from "vitest";
import { WIPE_MAX, WIPE_MIN, clampWipe, wipeFromPointer, wipeKey } from "./wipe";
import { parseParams } from "./params";

describe("wipe clamp", () => {
  it("keeps the divider inside the stage", () => {
    expect(clampWipe(-3)).toBe(WIPE_MIN);
    expect(clampWipe(7)).toBe(WIPE_MAX);
    expect(clampWipe(0.37)).toBe(0.37);
    expect(clampWipe(WIPE_MIN)).toBe(WIPE_MIN);
  });
  it("sends NaN and infinities to the middle", () => {
    expect(clampWipe(NaN)).toBe(0.5);
    expect(clampWipe(Infinity)).toBe(0.5);
    expect(clampWipe(-Infinity)).toBe(0.5);
  });
  it("turns a pointer into a position, clamped, and survives a zero-width stage", () => {
    expect(wipeFromPointer(300, 100, 400)).toBeCloseTo(0.5);
    expect(wipeFromPointer(50, 100, 400)).toBe(WIPE_MIN);
    expect(wipeFromPointer(9999, 100, 400)).toBe(WIPE_MAX);
    expect(wipeFromPointer(10, 0, 0)).toBe(0.5);
  });
  it("moves by arrow keys, in big steps with shift or page keys, and stops at the ends", () => {
    expect(wipeKey("ArrowRight", 0.5)).toBeCloseTo(0.52);
    expect(wipeKey("ArrowLeft", 0.5)).toBeCloseTo(0.48);
    expect(wipeKey("ArrowRight", 0.5, true)).toBeCloseTo(0.6);
    expect(wipeKey("PageDown", 0.5)).toBeCloseTo(0.4);
    expect(wipeKey("ArrowRight", WIPE_MAX)).toBe(WIPE_MAX);
    expect(wipeKey("Home", 0.5)).toBe(WIPE_MIN);
    expect(wipeKey("End", 0.5)).toBe(WIPE_MAX);
    expect(wipeKey("a", 0.5)).toBeNull();
  });
});

describe("deep-link parameters", () => {
  it("parses and clamps", () => {
    expect(parseParams("?frame=75&wipe=0.5&pause=1&view=take&overlay=0", 150))
      .toEqual({ frame: 75, wipe: 0.5, pause: true, view: "take", overlay: false, capture: false });
    expect(parseParams("?frame=9999&wipe=4", 150)).toMatchObject({ frame: 149, wipe: WIPE_MAX });
  });
  it("falls back on junk", () => {
    expect(parseParams("?frame=abc&wipe=&view=nope", 150)).toEqual({ frame: null, wipe: 0.5, pause: false, view: "wipe", overlay: true, capture: false });
    expect(parseParams("", 150).frame).toBeNull();
  });
});
