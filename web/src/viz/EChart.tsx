// React wrapper around an ECharts instance (modular build: only the parts we use).
import { BarChart, CustomChart, LineChart, ScatterChart } from "echarts/charts";
import {
  DataZoomComponent,
  GraphicComponent,
  GridComponent,
  LegendComponent,
  MarkAreaComponent,
  MarkLineComponent,
  TitleComponent,
  TooltipComponent,
  VisualMapComponent,
} from "echarts/components";
import * as echarts from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import { type CSSProperties, useEffect, useMemo, useRef } from "react";
import { cn } from "@/lib/utils";
import { echartsTheme, useThemeColors } from "./theme";

echarts.use([
  BarChart,
  CustomChart,
  LineChart,
  ScatterChart,
  DataZoomComponent,
  GraphicComponent,
  GridComponent,
  LegendComponent,
  MarkAreaComponent,
  MarkLineComponent,
  TitleComponent,
  TooltipComponent,
  VisualMapComponent,
  CanvasRenderer,
]);

export type EChartsInstance = echarts.ECharts;
export type EChartsOption = echarts.EChartsCoreOption;

interface EChartProps {
  option: EChartsOption;
  className?: string;
  style?: CSSProperties;
  /** Replace the whole option on each update (default) instead of merging. */
  notMerge?: boolean;
  /** Called with each new chart instance; may return a cleanup function. */
  onInit?: (chart: EChartsInstance) => (() => void) | undefined;
}

export function EChart({ option, className, style, notMerge = true, onInit }: EChartProps) {
  const ref = useRef<HTMLDivElement>(null);
  const chartRef = useRef<EChartsInstance | null>(null);
  const colors = useThemeColors();
  const theme = useMemo(() => echartsTheme(colors), [colors]);
  const initRef = useRef(onInit);
  initRef.current = onInit;

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const chart = echarts.init(el, theme, { renderer: "canvas" });
    chartRef.current = chart;
    const cleanup = initRef.current?.(chart);
    const observer = new ResizeObserver(() => chart.resize());
    observer.observe(el);
    return () => {
      observer.disconnect();
      if (typeof cleanup === "function") cleanup();
      chart.dispose();
      chartRef.current = null;
    };
  }, [theme]);

  // biome-ignore lint/correctness/useExhaustiveDependencies: a theme change re-creates the chart above, which then needs the option again
  useEffect(() => {
    chartRef.current?.setOption(option, { notMerge, lazyUpdate: true });
  }, [option, notMerge, theme]);

  return <div ref={ref} className={cn("h-full w-full", className)} style={style} />;
}

/** Download the chart as PNG (2x pixel ratio, opaque background). */
export function saveChartImage(chart: EChartsInstance, name: string, background: string) {
  const url = chart.getDataURL({ type: "png", pixelRatio: 2, backgroundColor: background });
  const link = document.createElement("a");
  link.href = url;
  link.download = `${name}.png`;
  link.click();
}
