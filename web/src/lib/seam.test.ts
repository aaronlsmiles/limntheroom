import { describe, expect, it } from "vitest";
import { CREATURE, KEPT, LIMNED, NONE, Seam, clock, describe as say, keptPercent, summarise } from "./seam";

/** Pack codes the way tools/make_sketch_fixture.py does: frame-major, four cells a byte, low bits first. */
function pack(frames: number[][]): Uint8Array {
  const per = Math.ceil(frames[0].length / 4);
  const out = new Uint8Array(per * frames.length);
  frames.forEach((codes, f) => codes.forEach((c, i) => { out[f * per + (i >> 2)] |= c << ((i & 3) * 2); }));
  return out;
}

describe("Seam decoder", () => {
  it("reads every code in the layout the fixture writes", () => {
    // 3 cols x 2 rows = 6 cells = 2 bytes a frame, the second byte half empty
    const f0 = [NONE, KEPT, LIMNED, CREATURE, KEPT, LIMNED];
    const f1 = [CREATURE, CREATURE, KEPT, NONE, NONE, LIMNED];
    const s = new Seam(pack([f0, f1]), 3, 2, 2);
    expect(s.bytesPerFrame).toBe(2);
    [f0, f1].forEach((codes, f) => codes.forEach((c, i) => expect(s.at(f, i % 3, Math.floor(i / 3))).toBe(c)));
  });

  it("pins the bit layout: cell 0 in the low two bits, cell 3 in the high two", () => {
    const s = new Seam(new Uint8Array([0b11_10_01_00]), 4, 1, 1);
    expect([0, 1, 2, 3].map((c) => s.at(0, c, 0))).toEqual([NONE, KEPT, LIMNED, CREATURE]);
  });

  it("clamps frames to the file and rejects cells outside the grid", () => {
    const s = new Seam(pack([[KEPT, KEPT], [LIMNED, LIMNED]]), 2, 1, 2);
    expect(s.at(-5, 0, 0)).toBe(KEPT);
    expect(s.at(99, 0, 0)).toBe(LIMNED);
    expect(() => s.at(0, 2, 0)).toThrow(RangeError);
    expect(() => s.at(0, 0, -1)).toThrow(RangeError);
  });

  it("refuses a file of the wrong length", () => {
    expect(() => new Seam(new Uint8Array(5), 3, 2, 2)).toThrow(/expected 4 bytes/);
    expect(() => new Seam(new Uint8Array(0), 0, 2, 1)).toThrow();
  });

  it("counts a frame and gives kept as a share of the cells with a verdict", () => {
    const s = new Seam(pack([[KEPT, KEPT, KEPT, LIMNED, CREATURE, NONE]]), 3, 2, 1);
    const c = s.counts(0);
    expect(c).toEqual({ none: 1, kept: 3, limned: 1, creature: 1 });
    expect(keptPercent(c)).toBe(75);
    expect(keptPercent({ none: 4, kept: 0, limned: 0, creature: 2 })).toBeNull();
  });

  it("summarises: mean, the low point and when kept fell under the threshold", () => {
    // 4 cells; kept share per frame: 100, 100, 50, 25, 100
    const fr = [
      [KEPT, KEPT, KEPT, KEPT], [KEPT, KEPT, KEPT, KEPT], [KEPT, KEPT, LIMNED, LIMNED],
      [KEPT, LIMNED, LIMNED, LIMNED], [KEPT, KEPT, KEPT, NONE],
    ];
    const sum = summarise(new Seam(pack(fr), 4, 1, 5), 80);
    expect(sum.pct).toEqual([100, 100, 50, 25, 100]);
    expect(sum.mean).toBeCloseTo(75);
    expect(sum.low).toEqual({ frame: 3, pct: 25 });
    expect(sum.below).toEqual({ from: 2, to: 3 });
    expect(say(sum, 1)).toContain("from 0:02.0 to 0:03.0");
    expect(summarise(new Seam(pack([[KEPT, KEPT]]), 2, 1, 1)).below).toBeNull();
  });

  it("formats a clock", () => {
    expect(clock(0)).toBe("0:00.0");
    expect(clock(5.04)).toBe("0:05.0");
    expect(clock(75.25)).toBe("1:15.3");
    expect(clock(-1)).toBe("0:00.0");
  });
});
