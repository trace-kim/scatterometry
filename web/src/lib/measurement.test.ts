import { describe, expect, it } from "vitest";
import { bytes, contrastRange, frameStats, profiles, saturationLevel } from "./measurement";

describe("frameStats", () => {
  it("counts saturated pixels of integer frames only", () => {
    const frame = new Uint16Array([100, 200, 65535, 65535]);
    expect(frameStats(frame, saturationLevel("u2"))).toEqual({ min: 100, max: 65535, mean: 32842.5, saturated: 2 });
    expect(frameStats(new Float32Array([1, 2]), saturationLevel("f4")).saturated).toBeNull();
  });
});

describe("contrastRange", () => {
  const ramp = Float64Array.from({ length: 10001 }, (_, i) => i); // 0..10000

  it("is the extent without clipping", () => {
    expect(contrastRange(ramp, 0)).toEqual({ min: 0, max: 10000 });
  });

  it("clips the given percent at each end (to a histogram bin)", () => {
    const { min, max } = contrastRange(ramp, 1);
    const bin = 10000 / 4096;
    expect(Math.abs(min - 100)).toBeLessThanOrEqual(bin);
    expect(Math.abs(max - 9900)).toBeLessThanOrEqual(bin);
  });

  it("ignores a few hot pixels", () => {
    const frame = new Float64Array(10000).fill(500);
    for (let i = 0; i < 10000; i++) frame[i] += i % 100;
    frame[0] = 65535; // cosmic ray
    const { max } = contrastRange(frame, 0.1);
    expect(max).toBeLessThan(700);
  });

  it("uses positive pixels in log space for log scale", () => {
    const { min, max } = contrastRange([0, -5, 1, 10, 100, 1000], 0, "log");
    expect(min).toBeCloseTo(1);
    expect(max).toBeCloseTo(1000);
  });

  it("widens flat frames", () => {
    expect(contrastRange([7, 7, 7], 1)).toEqual({ min: 6.5, max: 7.5 });
  });
});

describe("profiles", () => {
  it("extracts a row and a column, clamping the indices", () => {
    const frame = [0, 1, 2, 10, 11, 12]; // 3 wide, 2 high
    const p = profiles(frame, 3, 2, 1, 1);
    expect(Array.from(p.row)).toEqual([10, 11, 12]);
    expect(Array.from(p.column)).toEqual([1, 11]);
    expect(Array.from(profiles(frame, 3, 2, 9, -1).column)).toEqual([2, 12]);
  });
});

describe("bytes", () => {
  it("formats sizes", () => {
    expect(bytes(512)).toBe("512 B");
    expect(bytes(8 * 2 ** 20)).toBe("8.0 MB");
    expect(bytes(1.5 * 2 ** 30)).toBe("1.5 GB");
  });
});
