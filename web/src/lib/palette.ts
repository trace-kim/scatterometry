// Material colors: one fixed hue per material (by order), a neutral tint for vacuum-like
// media, and per-material overrides stored in the project document.
import type { MaterialDoc } from "@/api/model";

const PALETTE = [
  "#4C78A8",
  "#F58518",
  "#54A24B",
  "#E45756",
  "#72B7B2",
  "#EECA3B",
  "#B279A2",
  "#FF9DA6",
  "#9D755D",
  "#BAB0AC",
];
const CLEAR_LIGHT = "#E6EDF5";
const CLEAR_DARK = "#2A3442";

export function isClear(m: Pick<MaterialDoc, "n" | "k">): boolean {
  return m.n === 1 && (m.k ?? 0) === 0;
}

/** Display color per material, index-aligned with `materials`. */
export function materialColors(materials: MaterialDoc[], dark: boolean): string[] {
  let i = 0;
  return materials.map((m) => {
    if (m.color) return m.color;
    if (isClear(m)) return dark ? CLEAR_DARK : CLEAR_LIGHT;
    return PALETTE[i++ % PALETTE.length];
  });
}

export function hexToRgba(hex: string, alpha = 255): number[] {
  const v = Number.parseInt(hex.replace("#", "").slice(0, 6), 16);
  return [(v >> 16) & 255, (v >> 8) & 255, v & 255, alpha];
}
