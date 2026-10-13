// Image heatmap: values are colorized on the CPU into a canvas, which an ECharts custom
// series draws in data coordinates. ECharts supplies axes, zoom, and pan; colormap,
// range, and quantity changes only re-colorize (a few ms), never re-fetch.
import { useEffect, useMemo, useRef, useState } from "react";
import { colorize, colorizeCategories, type Domain, drawBoundaries, type Scale, toCanvas } from "@/lib/colorize";
import { type ColormapName, cssGradient } from "@/lib/colormaps";
import { fmt, niceTicks } from "@/lib/format";
import { hexToRgba } from "@/lib/palette";
import { cn } from "@/lib/utils";
import { EChart, type EChartsInstance, type EChartsOption } from "./EChart";
import { useThemeColors } from "./theme";

export interface Categories {
  indices: ArrayLike<number>;
  colors: string[];
  names: string[];
}

export interface HeatmapProps {
  /** Row-major values (`height` rows of `width`); row 0 lies at y[0]. Omit for categorical maps. */
  values?: ArrayLike<number> | null;
  categories?: Categories | null;
  width: number;
  height: number;
  /** Pixel-centre coordinates along each axis. */
  x: ArrayLike<number>;
  y: ArrayLike<number>;
  /** y grows downward (depth axes). */
  yDown?: boolean;
  colormap?: ColormapName;
  domain?: Domain;
  scale?: Scale;
  /** Category indices whose changes are outlined (material boundaries). */
  boundaries?: ArrayLike<number> | null;
  boundaryColor?: string;
  xLabel: string;
  yLabel: string;
  valueLabel?: string;
  title?: string;
  equalAspect?: boolean;
  /** Extra tooltip line for a pixel. */
  describe?: (x: number, y: number, index: number) => string | null;
  formatValue?: (value: number) => string;
  className?: string;
}

const MARGIN = { left: 54, right: 14, top: 26, bottom: 38 };

function edges(c: ArrayLike<number>): [number, number] {
  const n = c.length;
  if (n === 0) return [0, 1];
  if (n === 1) return [c[0] - 0.5, c[0] + 0.5];
  const d0 = c[1] - c[0];
  const d1 = c[n - 1] - c[n - 2];
  return [c[0] - d0 / 2, c[n - 1] + d1 / 2];
}

export function Heatmap(props: HeatmapProps) {
  const {
    values,
    categories,
    width,
    height,
    x,
    y,
    yDown = false,
    colormap = "viridis",
    domain = { min: 0, max: 1 },
    scale = "linear",
    boundaries,
    boundaryColor,
    xLabel,
    yLabel,
    valueLabel,
    title,
    equalAspect = false,
    className,
  } = props;
  const colors = useThemeColors();
  const box = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ w: 0, h: 0 });
  const [tip, setTip] = useState<{ left: number; top: number; lines: string[] } | null>(null);
  const latest = useRef(props);
  latest.current = props;

  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const observer = new ResizeObserver(([entry]) =>
      setSize({ w: entry.contentRect.width, h: entry.contentRect.height }),
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  const [x0, x1] = useMemo(() => edges(x), [x]);
  const [y0, y1] = useMemo(() => edges(y), [y]);

  const canvas = useMemo(() => {
    if (!width || !height) return null;
    let image = categories
      ? colorizeCategories(
          categories.indices,
          width,
          height,
          categories.colors.map((c) => hexToRgba(c)),
        )
      : values
        ? colorize(values, width, height, colormap, domain, scale)
        : null;
    if (!image) return null;
    if (boundaries) image = drawBoundaries(image, boundaries, hexToRgba(boundaryColor ?? "#9fd3ff", 220));
    return toCanvas(image, !yDown);
  }, [values, categories, width, height, colormap, domain, scale, boundaries, boundaryColor, yDown]);

  const grid = useMemo(() => {
    const top = MARGIN.top + (title ? 0 : -14);
    if (!equalAspect || !size.w || !size.h)
      return { left: MARGIN.left, right: MARGIN.right, top, bottom: MARGIN.bottom };
    const availW = Math.max(size.w - MARGIN.left - MARGIN.right, 10);
    const availH = Math.max(size.h - top - MARGIN.bottom, 10);
    const aspect = Math.abs(x1 - x0) / Math.abs(y1 - y0);
    const w = Math.min(availW, availH * aspect);
    const h = w / aspect;
    return { left: MARGIN.left + (availW - w) / 2, top: top + (availH - h) / 2, width: w, height: h };
  }, [equalAspect, size, x0, x1, y0, y1, title]);

  const option = useMemo<EChartsOption>(
    () => ({
      animation: false,
      title: title ? { text: title, textStyle: { fontSize: 12 } } : undefined,
      grid,
      xAxis: {
        type: "value",
        min: x0,
        max: x1,
        name: xLabel,
        nameLocation: "middle",
        nameGap: 24,
        splitLine: { show: false },
        axisLabel: { formatter: (v: number) => fmt(v, 4), hideOverlap: true, showMinLabel: false, showMaxLabel: false },
      },
      yAxis: {
        type: "value",
        min: y0,
        max: y1,
        inverse: yDown,
        name: yLabel,
        nameLocation: "middle",
        nameGap: 40,
        splitLine: { show: false },
        axisLabel: { formatter: (v: number) => fmt(v, 4), hideOverlap: true, showMinLabel: false, showMaxLabel: false },
      },
      dataZoom: [
        { type: "inside", xAxisIndex: 0, filterMode: "none" },
        { type: "inside", yAxisIndex: 0, filterMode: "none" },
      ],
      series: [
        {
          type: "custom",
          silent: true,
          clip: true,
          data: [[0]],
          renderItem: (_params: unknown, api: { coord: (p: number[]) => number[] }) => {
            if (!canvas) return null;
            const a = api.coord([x0, y0]);
            const b = api.coord([x1, y1]);
            return {
              type: "image",
              style: {
                image: canvas,
                x: Math.min(a[0], b[0]),
                y: Math.min(a[1], b[1]),
                width: Math.abs(b[0] - a[0]),
                height: Math.abs(b[1] - a[1]),
              },
            };
          },
        },
      ],
    }),
    [canvas, grid, x0, x1, y0, y1, yDown, xLabel, yLabel, title],
  );

  const onInit = (chart: EChartsInstance) => {
    const zr = chart.getZr();
    const move = (event: { offsetX: number; offsetY: number }) => {
      const p = latest.current;
      const point = [event.offsetX, event.offsetY];
      if (!chart.containPixel("grid", point)) return setTip(null);
      const [xv, yv] = chart.convertFromPixel("grid", point) as number[];
      const [ax0, ax1] = edges(p.x);
      const [ay0, ay1] = edges(p.y);
      const i = Math.floor(((xv - ax0) / (ax1 - ax0)) * p.width);
      const j = Math.floor(((yv - ay0) / (ay1 - ay0)) * p.height);
      if (i < 0 || j < 0 || i >= p.width || j >= p.height) return setTip(null);
      const index = j * p.width + i;
      const lines = [`${p.xLabel.split(" (")[0]} ${fmt(xv, 4)} · ${p.yLabel.split(" (")[0]} ${fmt(yv, 4)}`];
      if (p.categories) lines.push(p.categories.names[p.categories.indices[index]] ?? "");
      else if (p.values) lines.push(`${p.valueLabel ?? "value"} = ${(p.formatValue ?? fmt)(p.values[index])}`);
      const extra = p.describe?.(xv, yv, index);
      if (extra) lines.push(extra);
      setTip({ left: event.offsetX + 14, top: event.offsetY + 12, lines });
    };
    const out = () => setTip(null);
    zr.on("mousemove", move);
    zr.on("globalout", out);
    return () => {
      zr.off("mousemove", move);
      zr.off("globalout", out);
    };
  };

  return (
    <div className={cn("flex h-full min-h-0 w-full", className)}>
      <div ref={box} className="relative min-w-0 flex-1">
        <EChart option={option} onInit={onInit} />
        {tip && (
          <div
            className="pointer-events-none absolute z-10 rounded-md border bg-popover px-2 py-1 text-[11px] leading-4 text-popover-foreground shadow-md tabular-nums"
            style={{ left: Math.min(tip.left, size.w - 190), top: tip.top }}
          >
            {tip.lines.map((line) => (
              <div key={line}>{line}</div>
            ))}
          </div>
        )}
      </div>
      {categories ? (
        <CategoryLegend categories={categories} />
      ) : (
        values && (
          <ColorBar
            colormap={colormap}
            domain={domain}
            scale={scale}
            label={valueLabel}
            top={grid.top}
            bottom={"height" in grid ? size.h - grid.top - (grid.height ?? 0) : MARGIN.bottom}
            muted={colors.muted}
          />
        )
      )}
    </div>
  );
}

function ColorBar(props: {
  colormap: ColormapName;
  domain: Domain;
  scale: Scale;
  label?: string;
  top: number;
  bottom: number;
  muted: string;
}) {
  const { colormap, domain, scale, label, top, bottom } = props;
  const ticks = useMemo(() => {
    if (scale === "log") {
      const lo = Math.log10(Math.max(domain.min, Number.MIN_VALUE));
      const hi = Math.log10(Math.max(domain.max, Number.MIN_VALUE));
      return niceTicks(lo, hi, 5).map((t) => ({ value: 10 ** t, f: (t - lo) / (hi - lo || 1) }));
    }
    return niceTicks(domain.min, domain.max, 5).map((t) => ({
      value: t,
      f: (t - domain.min) / (domain.max - domain.min || 1),
    }));
  }, [domain, scale]);
  return (
    <div className="relative w-[64px] shrink-0" style={{ paddingTop: top, paddingBottom: Math.max(bottom, 8) }}>
      <div className="relative ml-1 h-full w-2.5 rounded-sm" style={{ background: cssGradient(colormap) }}>
        {ticks.map((t) => (
          <div
            key={t.value}
            className="absolute left-3.5 text-[10px] whitespace-nowrap text-muted-foreground tabular-nums"
            style={{ bottom: `${t.f * 100}%`, transform: "translateY(50%)" }}
          >
            {fmt(t.value, 3)}
          </div>
        ))}
      </div>
      {label && (
        <div className="absolute top-0 left-0 w-full truncate text-[10px] text-muted-foreground" title={label}>
          {label}
        </div>
      )}
    </div>
  );
}

function CategoryLegend({ categories }: { categories: Categories }) {
  const present = useMemo(() => {
    const seen = new Set<number>();
    for (let i = 0; i < categories.indices.length; i++) seen.add(categories.indices[i]);
    return [...seen].sort((a, b) => a - b);
  }, [categories.indices]);
  return (
    <div className="flex w-[92px] shrink-0 flex-col gap-1 overflow-hidden pt-3 pl-2 text-[11px]">
      {present.map((i) => (
        <div key={i} className="flex items-center gap-1.5 truncate">
          <span
            className="size-2.5 shrink-0 rounded-[2px] border border-black/10"
            style={{ background: categories.colors[i] }}
          />
          <span className="truncate">{categories.names[i]}</span>
        </div>
      ))}
    </div>
  );
}
