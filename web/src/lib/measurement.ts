// Camera frame helpers for the measurement viewer: statistics, percentile contrast
// limits, and line profiles. Frames are row-major, `width` pixels per row.
import type { Domain, Scale } from "./colorize";
import type { NpyDtype } from "./npz";

export interface FrameStats {
  min: number;
  max: number;
  mean: number;
  /** Pixels at the pixel type's full scale (null for float data and averages). */
  saturated: number | null;
}

/** Full-scale value of an integer pixel type: such pixels are clipped by the camera's ADC. */
export function saturationLevel(dtype: NpyDtype): number | null {
  return dtype === "u1" ? 255 : dtype === "u2" ? 65535 : dtype === "u4" ? 4294967295 : null;
}

export function frameStats(values: ArrayLike<number>, saturation: number | null = null): FrameStats {
  let min = Number.POSITIVE_INFINITY;
  let max = Number.NEGATIVE_INFINITY;
  let sum = 0;
  let count = 0;
  let saturated = 0;
  for (let i = 0; i < values.length; i++) {
    const v = values[i];
    if (!Number.isFinite(v)) continue;
    if (v < min) min = v;
    if (v > max) max = v;
    if (saturation !== null && v >= saturation) saturated++;
    sum += v;
    count++;
  }
  if (!count) return { min: 0, max: 0, mean: 0, saturated: saturation === null ? null : 0 };
  return { min, max, mean: sum / count, saturated: saturation === null ? null : saturated };
}

const BINS = 4096;

/**
 * Color range that clips `clip` percent of the pixels at each end. It comes from a
 * 4096-bin histogram (in log10 space for log scale, positive pixels only), so the limits
 * are accurate to 1/4096 of the range.
 */
export function contrastRange(values: ArrayLike<number>, clip: number, scale: Scale = "linear"): Domain {
  const log = scale === "log";
  let lo = Number.POSITIVE_INFINITY;
  let hi = Number.NEGATIVE_INFINITY;
  for (let i = 0; i < values.length; i++) {
    const v = values[i];
    if (!Number.isFinite(v) || (log && v <= 0)) continue;
    const t = log ? Math.log10(v) : v;
    if (t < lo) lo = t;
    if (t > hi) hi = t;
  }
  const back = (t: number) => (log ? 10 ** t : t);
  if (lo > hi) return log ? { min: 1, max: 10 } : { min: 0, max: 1 };
  if (lo === hi) return log ? { min: back(lo - 0.5), max: back(hi + 0.5) } : { min: lo - 0.5, max: hi + 0.5 };
  if (clip <= 0) return { min: back(lo), max: back(hi) };

  const counts = new Float64Array(BINS);
  const k = BINS / (hi - lo);
  let total = 0;
  for (let i = 0; i < values.length; i++) {
    const v = values[i];
    if (!Number.isFinite(v) || (log && v <= 0)) continue;
    const t = log ? Math.log10(v) : v;
    counts[Math.min(BINS - 1, Math.floor((t - lo) * k))]++;
    total++;
  }
  const cut = (clip / 100) * total;
  let below = 0;
  let first = 0;
  while (first < BINS - 1 && below + counts[first] <= cut) below += counts[first++];
  let above = 0;
  let last = BINS - 1;
  while (last > first && above + counts[last] <= cut) above += counts[last--];
  const min = lo + first / k;
  const max = lo + (last + 1) / k;
  return { min: back(min), max: back(max) };
}

/** Pixel values along row `row` (y index) and column `column` (x index). */
export function profiles(values: ArrayLike<number>, width: number, height: number, column: number, row: number) {
  const r = Math.max(0, Math.min(height - 1, row));
  const c = Math.max(0, Math.min(width - 1, column));
  const rowValues = new Float64Array(width);
  for (let i = 0; i < width; i++) rowValues[i] = values[r * width + i];
  const columnValues = new Float64Array(height);
  for (let j = 0; j < height; j++) columnValues[j] = values[j * width + c];
  return { row: rowValues, column: columnValues };
}

/** "1.5 MB" style sizes. */
export function bytes(n: number): string {
  if (n < 1024) return `${n} B`;
  const units = ["kB", "MB", "GB"];
  let v = n / 1024;
  let u = 0;
  while (v >= 1024 && u < units.length - 1) {
    v /= 1024;
    u++;
  }
  return `${v.toFixed(v < 10 ? 1 : 0)} ${units[u]}`;
}
