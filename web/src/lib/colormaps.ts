// Colormap lookup tables (256 RGBA entries) built from the same stops Plotly/matplotlib use.

export type ColormapName = "inferno" | "magma" | "viridis" | "cividis" | "turbo" | "rdbu" | "twilight" | "gray";

const STOPS: Record<ColormapName, string[]> = {
  inferno: [
    "#000004",
    "#1b0c41",
    "#4a0c6b",
    "#781c6d",
    "#a52c60",
    "#cf4446",
    "#ed6925",
    "#fb9b06",
    "#f7d13d",
    "#fcffa4",
  ],
  magma: ["#000004", "#180f3d", "#440f76", "#721f81", "#9e2f7f", "#cd4071", "#f1605d", "#fd9668", "#feca8d", "#fcfdbf"],
  viridis: [
    "#440154",
    "#482878",
    "#3e4989",
    "#31688e",
    "#26828e",
    "#1f9e89",
    "#35b779",
    "#6ece58",
    "#b5de2b",
    "#fde725",
  ],
  cividis: [
    "#00224e",
    "#123570",
    "#3b496c",
    "#575d6d",
    "#707173",
    "#8a8678",
    "#a59c74",
    "#c3b369",
    "#e1cc55",
    "#fee838",
  ],
  turbo: [
    "#30123b",
    "#4145ab",
    "#4675ed",
    "#39a2fc",
    "#1bcfd4",
    "#24eca6",
    "#61fc6c",
    "#a4fc3b",
    "#d1e834",
    "#f3c63a",
    "#fe9b2d",
    "#f36315",
    "#d93806",
    "#b11901",
    "#7a0402",
  ],
  // Diverging, blue (negative) to red (positive): RdBu reversed.
  rdbu: [
    "#053061",
    "#2166ac",
    "#4393c3",
    "#92c5de",
    "#d1e5f0",
    "#f7f7f7",
    "#fddbc7",
    "#f4a582",
    "#d6604d",
    "#b2182b",
    "#67001f",
  ],
  // Cyclic, for phases.
  twilight: [
    "#e2d9e2",
    "#9ebbc9",
    "#6785be",
    "#5e43a5",
    "#421257",
    "#471340",
    "#8e2c50",
    "#ba6657",
    "#ceac94",
    "#e2d9e2",
  ],
  gray: ["#000000", "#ffffff"],
};

export const COLORMAPS: { value: ColormapName; label: string; kind: "sequential" | "diverging" | "cyclic" }[] = [
  { value: "inferno", label: "Inferno", kind: "sequential" },
  { value: "magma", label: "Magma", kind: "sequential" },
  { value: "viridis", label: "Viridis", kind: "sequential" },
  { value: "cividis", label: "Cividis", kind: "sequential" },
  { value: "turbo", label: "Turbo", kind: "sequential" },
  { value: "gray", label: "Gray", kind: "sequential" },
  { value: "rdbu", label: "Red–Blue (signed)", kind: "diverging" },
  { value: "twilight", label: "Twilight (phase)", kind: "cyclic" },
];

function hexToRgb(hex: string): [number, number, number] {
  const v = Number.parseInt(hex.slice(1), 16);
  return [(v >> 16) & 255, (v >> 8) & 255, v & 255];
}

const cache = new Map<ColormapName, Uint8Array>();

/** 256 x RGBA lookup table, linearly interpolated between the stops. */
export function lut(name: ColormapName): Uint8Array {
  const hit = cache.get(name);
  if (hit) return hit;
  const stops = STOPS[name].map(hexToRgb);
  const table = new Uint8Array(256 * 4);
  for (let i = 0; i < 256; i++) {
    const t = (i / 255) * (stops.length - 1);
    const k = Math.min(Math.floor(t), stops.length - 2);
    const f = t - k;
    for (let c = 0; c < 3; c++) table[i * 4 + c] = Math.round(stops[k][c] + f * (stops[k + 1][c] - stops[k][c]));
    table[i * 4 + 3] = 255;
  }
  cache.set(name, table);
  return table;
}

/** CSS gradient for colorbars (bottom = low). */
export function cssGradient(name: ColormapName, direction = "to top"): string {
  const stops = STOPS[name];
  return `linear-gradient(${direction}, ${stops.map((c, i) => `${c} ${((i / (stops.length - 1)) * 100).toFixed(1)}%`).join(", ")})`;
}

/** Colors for ECharts visualMaps and gradients. */
export function colormapStops(name: ColormapName): string[] {
  return STOPS[name];
}
