// Bridges the CSS design tokens (OKLCH variables in index.css) to canvas-based renderers
// (ECharts, three.js), which need concrete RGB colors. Re-evaluated when the theme
// changes, so restyling index.css restyles every chart.
import { useMemo, useSyncExternalStore } from "react";

const SERIES = [
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

let probe: CanvasRenderingContext2D | null = null;

/** Any CSS color (including oklch() and var-resolved tokens) as an rgba() string. */
export function toRgba(color: string): string {
  probe ??= document.createElement("canvas").getContext("2d", { willReadFrequently: true });
  if (!probe) return color;
  probe.clearRect(0, 0, 1, 1);
  probe.fillStyle = "#000";
  probe.fillStyle = color;
  probe.fillRect(0, 0, 1, 1);
  const [r, g, b, a] = probe.getImageData(0, 0, 1, 1).data;
  return `rgba(${r}, ${g}, ${b}, ${(a / 255).toFixed(3)})`;
}

export function token(name: string): string {
  return toRgba(getComputedStyle(document.documentElement).getPropertyValue(name).trim() || "#888");
}

export interface ThemeColors {
  dark: boolean;
  foreground: string;
  muted: string;
  border: string;
  grid: string;
  background: string;
  popover: string;
  primary: string;
  series: string[];
  font: string;
}

// next-themes switches the `dark` class on <html> in an effect that runs after children
// render, so reading tokens during render could still see the old theme. Watching the
// class attribute itself guarantees the tokens are read after the switch.
function subscribeToThemeClass(onChange: () => void): () => void {
  const observer = new MutationObserver(onChange);
  observer.observe(document.documentElement, { attributes: true, attributeFilter: ["class", "style"] });
  return () => observer.disconnect();
}

const isDarkClass = () => document.documentElement.classList.contains("dark");

export function useDark(): boolean {
  return useSyncExternalStore(subscribeToThemeClass, isDarkClass, () => false);
}

export function useThemeColors(): ThemeColors {
  const dark = useDark();
  return useMemo(
    () => ({
      dark,
      foreground: token("--foreground"),
      muted: token("--muted-foreground"),
      border: token("--border"),
      grid: dark ? "rgba(255,255,255,0.06)" : "rgba(0,0,0,0.06)",
      background: token("--background"),
      popover: token("--popover"),
      primary: token("--primary"),
      series: SERIES,
      font: getComputedStyle(document.documentElement).fontFamily || "sans-serif",
    }),
    [dark],
  );
}

/** ECharts theme object derived from the tokens. */
export function echartsTheme(c: ThemeColors): object {
  const axis = {
    axisLine: { lineStyle: { color: c.border } },
    axisTick: { lineStyle: { color: c.border } },
    axisLabel: { color: c.muted, fontSize: 10 },
    splitLine: { lineStyle: { color: c.grid } },
    nameTextStyle: { color: c.muted, fontSize: 11 },
  };
  return {
    color: c.series,
    backgroundColor: "transparent",
    textStyle: { color: c.foreground, fontFamily: c.font, fontSize: 11 },
    title: { textStyle: { color: c.foreground, fontSize: 12, fontWeight: 600 }, left: 8, top: 4 },
    legend: { textStyle: { color: c.muted, fontSize: 11 }, itemWidth: 14, itemHeight: 8 },
    tooltip: {
      backgroundColor: c.popover,
      borderColor: c.border,
      textStyle: { color: c.foreground, fontSize: 11 },
      extraCssText: "box-shadow: 0 4px 16px rgba(0,0,0,0.15); border-radius: 6px;",
    },
    valueAxis: axis,
    categoryAxis: axis,
    logAxis: axis,
    line: { symbolSize: 5, lineStyle: { width: 1.6 } },
  };
}
