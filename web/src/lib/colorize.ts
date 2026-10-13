// Turn value grids into RGBA pixels on the CPU. A 512 x 400 field map takes ~2 ms, so
// colormap, range, scale, and quantity changes redraw without asking the server.
import type { ColormapName } from "./colormaps";
import { lut } from "./colormaps";

export type Scale = "linear" | "log";

export interface Domain {
  min: number;
  max: number;
}

export interface Image {
  width: number;
  height: number;
  rgba: Uint8ClampedArray;
}

/** Finite min/max; for log scale only positive values count. */
export function extent(values: ArrayLike<number>, scale: Scale = "linear"): Domain {
  let min = Number.POSITIVE_INFINITY;
  let max = Number.NEGATIVE_INFINITY;
  for (let i = 0; i < values.length; i++) {
    const v = values[i];
    if (!Number.isFinite(v) || (scale === "log" && v <= 0)) continue;
    if (v < min) min = v;
    if (v > max) max = v;
  }
  if (min > max) return { min: 0, max: 1 };
  if (min === max) return { min: min - (Math.abs(min) || 1) * 0.5, max: max + (Math.abs(max) || 1) * 0.5 };
  return { min, max };
}

/** Domain symmetric about zero (for signed quantities and diverging colormaps). */
export function symmetricExtent(values: ArrayLike<number>): Domain {
  const { min, max } = extent(values);
  const m = Math.max(Math.abs(min), Math.abs(max)) || 1;
  return { min: -m, max: m };
}

export function colorize(
  values: ArrayLike<number>,
  width: number,
  height: number,
  colormap: ColormapName,
  domain: Domain,
  scale: Scale = "linear",
): Image {
  const table = lut(colormap);
  const rgba = new Uint8ClampedArray(width * height * 4);
  const log = scale === "log";
  const lo = log ? Math.log10(Math.max(domain.min, Number.MIN_VALUE)) : domain.min;
  const hi = log ? Math.log10(Math.max(domain.max, Number.MIN_VALUE)) : domain.max;
  const k = hi > lo ? 255 / (hi - lo) : 0;
  for (let i = 0; i < width * height; i++) {
    let v = values[i];
    if (!Number.isFinite(v) || (log && v <= 0)) continue; // transparent
    if (log) v = Math.log10(v);
    const idx = Math.max(0, Math.min(255, Math.round((v - lo) * k))) * 4;
    const o = i * 4;
    rgba[o] = table[idx];
    rgba[o + 1] = table[idx + 1];
    rgba[o + 2] = table[idx + 2];
    rgba[o + 3] = 255;
  }
  return { width, height, rgba };
}

/** Color by category index (e.g. material maps). */
export function colorizeCategories(
  indices: ArrayLike<number>,
  width: number,
  height: number,
  colors: number[][],
): Image {
  const rgba = new Uint8ClampedArray(width * height * 4);
  for (let i = 0; i < width * height; i++) {
    const c = colors[indices[i]] ?? [128, 128, 128, 255];
    rgba.set([c[0], c[1], c[2], c[3] ?? 255], i * 4);
  }
  return { width, height, rgba };
}

/** Paint pixels where the category changes from the left or upper neighbour (material boundaries). */
export function drawBoundaries(image: Image, indices: ArrayLike<number>, color: number[]): Image {
  const { width, height, rgba } = image;
  const out = new Uint8ClampedArray(rgba);
  const [r, g, b, a = 255] = color;
  const alpha = a / 255;
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      const i = y * width + x;
      const edge = (x > 0 && indices[i] !== indices[i - 1]) || (y > 0 && indices[i] !== indices[i - width]);
      if (!edge) continue;
      const o = i * 4;
      out[o] = out[o] * (1 - alpha) + r * alpha;
      out[o + 1] = out[o + 1] * (1 - alpha) + g * alpha;
      out[o + 2] = out[o + 2] * (1 - alpha) + b * alpha;
      out[o + 3] = Math.max(out[o + 3], a);
    }
  }
  return { width, height, rgba: out };
}

/**
 * Canvas holding the image. Rows are drawn top to bottom unless `flipY` (then row 0 is
 * at the bottom, for y axes pointing up). Small images are upscaled with nearest-neighbour
 * sampling so the browser's smoothing doesn't blur discrete cells (e.g. matrices).
 */
export function toCanvas(image: Image, flipY = false): HTMLCanvasElement {
  const { width, height, rgba } = image;
  const largest = Math.max(width, height, 1);
  const factor = largest < 128 ? Math.ceil(256 / largest) : 1;
  const canvas = document.createElement("canvas");
  canvas.width = width * factor;
  canvas.height = height * factor;
  const ctx = canvas.getContext("2d");
  if (!ctx) return canvas;
  const pixels = ctx.createImageData(canvas.width, canvas.height);
  const out = pixels.data;
  const rowBytes = width * 4;
  if (factor === 1) {
    // Common case (field maps): whole rows are block copies.
    for (let y = 0; y < height; y++) {
      const src = (flipY ? height - 1 - y : y) * rowBytes;
      out.set(rgba.subarray(src, src + rowBytes), y * rowBytes);
    }
  } else {
    for (let y = 0; y < canvas.height; y++) {
      const srcRow = flipY ? height - 1 - Math.floor(y / factor) : Math.floor(y / factor);
      for (let x = 0; x < canvas.width; x++) {
        const s = (srcRow * width + Math.floor(x / factor)) * 4;
        const d = (y * canvas.width + x) * 4;
        out[d] = rgba[s];
        out[d + 1] = rgba[s + 1];
        out[d + 2] = rgba[s + 2];
        out[d + 3] = rgba[s + 3];
      }
    }
  }
  ctx.putImageData(pixels, 0, 0);
  return canvas;
}
