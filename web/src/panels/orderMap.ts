// The Pupil card's order map, shared by its Pupil and Camera modes so both read the same:
// a square window of direction cosines, marker size ∝ √R, color = phase.
import { colormapStops } from "@/lib/colormaps";
import { fixed, fmt } from "@/lib/format";
import type { EChartsOption } from "@/viz/EChart";
import type { ThemeColors } from "@/viz/theme";

export interface OrderPoint {
  x: number;
  y: number;
  R: number;
  phase: number;
  m: number;
  n: number;
  /** Drawn faded (e.g. off the sensor). */
  faded?: boolean;
  /** Extra tooltip line. */
  note?: string;
}

export interface Overlay {
  name: string;
  data: ([number, number] | null)[];
  /** "outline" is the dashed boundary of the reflected half-space; "aperture" the NA circle or sensor. */
  kind: "outline" | "aperture";
}

export function circle(cx: number, cy: number, r: number): [number, number][] {
  return Array.from({ length: 181 }, (_, i) => [
    cx + r * Math.cos((i / 90) * Math.PI),
    cy + r * Math.sin((i / 90) * Math.PI),
  ]);
}

export function orderMapOption({
  points,
  overlays,
  center,
  half,
  zoomed,
  axisNames,
  colors,
  grid,
}: {
  points: OrderPoint[];
  overlays: Overlay[];
  center: [number, number];
  half: number;
  /** Zoomed in, only a few orders are on screen: bigger markers, and labels. */
  zoomed: boolean;
  axisNames: [string, string];
  colors: ThemeColors;
  grid: { left: number; top: number; width: number; height: number };
}): EChartsOption {
  const rMax = Math.max(...points.map((p) => p.R), 1e-30);
  // Markers scale with the plot; zoomed in, the orders are far apart and can be larger.
  const maxSymbol = Math.min(Math.max(grid.width * (zoomed ? 0.12 : 0.075), 14), 64);
  const series: object[] = overlays.map((o) => ({
    type: "line",
    name: o.name,
    data: o.data,
    showSymbol: false,
    silent: true,
    connectNulls: false,
    lineStyle:
      o.kind === "outline" ? { type: "dashed", width: 1, color: colors.muted } : { width: 1.5, color: "#E45756" },
  }));
  series.push({
    type: "scatter",
    name: "orders",
    data: points.map((p) => ({
      value: [p.x, p.y, p.R, p.phase, p.m, p.n],
      note: p.note,
      itemStyle: p.faded ? { opacity: 0.45 } : undefined,
    })),
    symbolSize: (d: number[]) => 5 + (maxSymbol - 5) * Math.sqrt(Math.max(d[2], 0) / rMax),
    itemStyle: { borderColor: colors.foreground, borderWidth: 0.6 },
    label: {
      show: zoomed,
      position: "right",
      distance: 6,
      color: colors.muted,
      fontSize: 10,
      formatter: (item: { data: { value: number[] } }) => `(${item.data.value[4]},${item.data.value[5]})`,
    },
    z: 5,
  });
  const axis = (min: number, max: number, name: string, nameGap: number) => ({
    type: "value",
    min,
    max,
    name,
    nameLocation: "middle",
    nameGap,
    axisLabel: { showMinLabel: false, showMaxLabel: false, formatter: (v: number) => fmt(v, 3) },
  });
  return {
    animation: false,
    grid,
    tooltip: {
      trigger: "item",
      formatter: (item: { seriesType: string; data: { value: number[]; note?: string } }) => {
        if (item.seriesType !== "scatter") return "";
        const [, , R, phase, m, n] = item.data.value;
        const note = item.data.note ? `<br/>${item.data.note}` : "";
        return `order (${m},${n})<br/>R = ${fmt(R, 5)}<br/>phase = ${fixed(phase, 1)}°${note}`;
      },
    },
    xAxis: axis(center[0] - half, center[0] + half, axisNames[0], 26),
    yAxis: axis(center[1] - half, center[1] + half, axisNames[1], 40),
    visualMap: {
      type: "continuous",
      seriesIndex: series.length - 1,
      dimension: 3,
      min: -180,
      max: 180,
      calculable: false,
      orient: "vertical",
      right: 8,
      top: "middle",
      itemWidth: 12,
      itemHeight: Math.max(grid.height * 0.5, 80),
      text: ["180°", "−180°"],
      textStyle: { color: colors.muted, fontSize: 10 },
      inRange: { color: colormapStops("twilight") },
    },
    series,
  };
}
