import { zipSync } from "fflate";
import { describe, expect, it } from "vitest";
import { colorize, colorizeCategories, drawBoundaries, extent, symmetricExtent } from "./colorize";
import { lut } from "./colormaps";
import { fieldQuantity } from "./field";
import { niceTicks } from "./format";
import { hashValue, stableStringify } from "./hash";
import { type NpyArray, parseNpy, parseNpz } from "./npz";

function npy(descr: string, shape: number[], payload: ArrayBufferView): Uint8Array {
  const shapeText = shape.length === 1 ? `(${shape[0]},)` : `(${shape.join(", ")})`;
  let header = `{'descr': '${descr}', 'fortran_order': False, 'shape': ${shapeText}, }`;
  const unpadded = 10 + header.length + 1;
  header += `${" ".repeat((64 - (unpadded % 64)) % 64)}\n`;
  const out = new Uint8Array(10 + header.length + payload.byteLength);
  out.set([0x93, ..."NUMPY".split("").map((c) => c.charCodeAt(0)), 1, 0], 0);
  new DataView(out.buffer).setUint16(8, header.length, true);
  out.set(new TextEncoder().encode(header), 10);
  out.set(new Uint8Array(payload.buffer, payload.byteOffset, payload.byteLength), 10 + header.length);
  return out;
}

describe("npz", () => {
  it("reads float, complex, and integer arrays with their shapes", () => {
    const f = parseNpy(npy("<f4", [2, 3], new Float32Array([1, 2, 3, 4, 5, 6])));
    expect(f.shape).toEqual([2, 3]);
    expect(Array.from(f.data)).toEqual([1, 2, 3, 4, 5, 6]);

    const archive = zipSync({
      "E.npy": npy("<c8", [2], new Float32Array([1, -1, 0.5, 2])),
      "idx.npy": npy("|u1", [3], new Uint8Array([0, 2, 1])),
      "mx.npy": npy("<i2", [3], new Int16Array([-1, 0, 1])),
      "ccd.npy": npy("<u2", [2], new Uint16Array([0, 65535])),
      "big.npy": npy("<u4", [1], new Uint32Array([4000000000])),
    });
    const arrays = parseNpz(archive.buffer as ArrayBuffer);
    expect(arrays.E.dtype).toBe("c8");
    expect(Array.from(arrays.E.data)).toEqual([1, -1, 0.5, 2]);
    expect(Array.from(arrays.idx.data)).toEqual([0, 2, 1]);
    expect(Array.from(arrays.mx.data)).toEqual([-1, 0, 1]);
    expect(Array.from(arrays.ccd.data)).toEqual([0, 65535]);
    expect(Array.from(arrays.big.data)).toEqual([4000000000]);
  });

  it("rejects non-npy data", () => {
    expect(() => parseNpy(new Uint8Array([1, 2, 3, 4, 5, 6, 7, 8, 9, 10]))).toThrow();
  });
});

describe("colorize", () => {
  it("maps the domain ends to the colormap ends and NaN to transparent", () => {
    const image = colorize([0, 1, Number.NaN], 3, 1, "viridis", { min: 0, max: 1 });
    const table = lut("viridis");
    expect(Array.from(image.rgba.slice(0, 4))).toEqual(Array.from(table.slice(0, 4)));
    expect(Array.from(image.rgba.slice(4, 8))).toEqual(Array.from(table.slice(255 * 4, 256 * 4)));
    expect(image.rgba[11]).toBe(0);
  });

  it("supports log scale, categories, and boundaries", () => {
    const log = colorize([1, 10, 100, 0], 4, 1, "gray", { min: 1, max: 100 }, "log");
    expect(log.rgba[4]).toBeGreaterThan(120);
    expect(log.rgba[4]).toBeLessThan(135); // 10 sits halfway in log space
    expect(log.rgba[15]).toBe(0); // non-positive values are not drawable on a log scale

    const cats = colorizeCategories([0, 1, 1, 0], 2, 2, [
      [255, 0, 0],
      [0, 0, 255],
    ]);
    expect(Array.from(cats.rgba.slice(4, 8))).toEqual([0, 0, 255, 255]);
    const outlined = drawBoundaries(cats, [0, 1, 1, 0], [0, 255, 0, 255]);
    expect(Array.from(outlined.rgba.slice(4, 7))).toEqual([0, 255, 0]); // (1,0) differs from its left neighbour
    expect(Array.from(outlined.rgba.slice(0, 3))).toEqual([255, 0, 0]); // (0,0) has no neighbour above/left
  });

  it("finds extents", () => {
    expect(extent([3, -2, Number.NaN, 7])).toEqual({ min: -2, max: 7 });
    expect(extent([0, -1, 0.01, 10], "log")).toEqual({ min: 0.01, max: 10 });
    expect(symmetricExtent([-1, 4])).toEqual({ min: -4, max: 4 });
  });
});

describe("field quantities", () => {
  const c = (values: number[]): NpyArray => ({
    dtype: "c8",
    shape: [values.length / 2],
    data: new Float32Array(values),
  });
  const field = { Ex: c([3, 4, 0, 0]), Ey: c([0, 0, 0, 1]), Ez: c([0, 0, 0, 0]) };

  it("computes intensity, magnitudes, phases, and time snapshots", () => {
    expect(Array.from(fieldQuantity(field, "|E|²"))).toEqual([25, 1]);
    expect(Array.from(fieldQuantity(field, "|Ex|"))).toEqual([5, 0]);
    expect(fieldQuantity(field, "arg Ey")[1]).toBeCloseTo(90);
    // Re(E e^{jωt}) at ωt = 90° for E = 3 + 4j is -4.
    expect(fieldQuantity(field, "Re Ex", 90)[0]).toBeCloseTo(-4);
  });
});

describe("helpers", () => {
  it("hashes values independent of key order", () => {
    expect(stableStringify({ b: 1, a: [2, { d: 3, c: 4 }] })).toBe('{"a":[2,{"c":4,"d":3}],"b":1}');
    expect(hashValue({ a: 1, b: 2 })).toBe(hashValue({ b: 2, a: 1 }));
    expect(hashValue({ a: 1 })).not.toBe(hashValue({ a: 2 }));
  });

  it("makes nice ticks", () => {
    expect(niceTicks(0, 1, 5)).toEqual([0, 0.2, 0.4, 0.6, 0.8, 1]);
    expect(niceTicks(-180, 180, 4)).toEqual([-200, -100, 0, 100, 200].filter((t) => t >= -180 && t <= 180));
  });
});
