// Readers for NumPy .npy / .npz data (the server's array transport, see maskserver/arrays.py).
import { unzipSync } from "fflate";

export type NpyDtype = "f4" | "f8" | "c8" | "c16" | "u1" | "b1" | "i2" | "i4" | "u2" | "u4";

export interface NpyArray {
  dtype: NpyDtype;
  shape: number[];
  /** Row-major values; complex dtypes are interleaved (re, im) pairs. */
  data: Float32Array | Float64Array | Uint8Array | Int16Array | Int32Array | Uint16Array | Uint32Array;
}

const ITEM_SIZE: Record<NpyDtype, number> = { f4: 4, f8: 8, c8: 8, c16: 16, u1: 1, b1: 1, i2: 2, i4: 4, u2: 2, u4: 4 };

export function parseNpy(bytes: Uint8Array): NpyArray {
  const magic = String.fromCharCode(...bytes.subarray(1, 6));
  if (bytes[0] !== 0x93 || magic !== "NUMPY") throw new Error("not a .npy array");
  const major = bytes[6];
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const headerStart = major === 1 ? 10 : 12;
  const headerLength = major === 1 ? view.getUint16(8, true) : view.getUint32(8, true);
  const header = new TextDecoder("latin1").decode(bytes.subarray(headerStart, headerStart + headerLength));

  const descr = /'descr':\s*'([<>|=])(\w+)'/.exec(header);
  if (!descr) throw new Error(`unreadable .npy header: ${header}`);
  if (descr[1] === ">") throw new Error("big-endian arrays are not supported");
  const dtype = descr[2] as NpyDtype;
  if (!(dtype in ITEM_SIZE)) throw new Error(`unsupported dtype ${descr[2]}`);
  if (/'fortran_order':\s*True/.test(header)) throw new Error("Fortran-ordered arrays are not supported");
  const shapeText = /'shape':\s*\(([^)]*)\)/.exec(header)?.[1] ?? "";
  const shape = shapeText
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean)
    .map(Number);

  const count = shape.reduce((a, b) => a * b, 1);
  const start = bytes.byteOffset + headerStart + headerLength;
  // Copy into a fresh buffer: typed-array views need aligned offsets.
  const buffer = bytes.buffer.slice(start, start + count * ITEM_SIZE[dtype]) as ArrayBuffer;
  const data =
    dtype === "f4" || dtype === "c8"
      ? new Float32Array(buffer)
      : dtype === "f8" || dtype === "c16"
        ? new Float64Array(buffer)
        : dtype === "i2"
          ? new Int16Array(buffer)
          : dtype === "i4"
            ? new Int32Array(buffer)
            : dtype === "u2"
              ? new Uint16Array(buffer)
              : dtype === "u4"
                ? new Uint32Array(buffer)
                : new Uint8Array(buffer);
  return { dtype, shape, data };
}

export function parseNpz(buffer: ArrayBuffer): Record<string, NpyArray> {
  const files = unzipSync(new Uint8Array(buffer));
  const out: Record<string, NpyArray> = {};
  for (const [name, bytes] of Object.entries(files)) {
    out[name.replace(/\.npy$/, "")] = parseNpy(bytes);
  }
  return out;
}

/** Plain number[] of a real 1D array (axes). */
export function toNumbers(array: NpyArray): number[] {
  return Array.from(array.data as ArrayLike<number>);
}
