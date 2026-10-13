// Diffraction results of the current run: totals, per-order efficiencies, the pupil with
// the projection NA, and the full order table.
import { Download04Icon } from "@hugeicons/core-free-icons";
import { HugeiconsIcon } from "@hugeicons/react";
import type { ColDef } from "ag-grid-community";
import { useMemo, useRef } from "react";
import { errorMessages } from "@/api/client";
import { useOrders, usePupil } from "@/api/hooks";
import type { OrderRow, Polarization, RunSummary } from "@/api/model";
import { ToolbarItem } from "@/components/controls";
import { DataGrid } from "@/components/data-grid";
import { PanelLayout, Stat, ViewCard } from "@/components/layout";
import { NumberField } from "@/components/number-field";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { colormapStops } from "@/lib/colormaps";
import { downloadText, toCsv } from "@/lib/download";
import { fixed, fmt } from "@/lib/format";
import { squareGrid, useElementSize } from "@/lib/use-element-size";
import { useView } from "@/state/view";
import { EChart, type EChartsOption } from "@/viz/EChart";
import { useThemeColors } from "@/viz/theme";
import { PolarizationPicker, usePol, useRunState } from "./common";
import { RunRequired } from "./RunRequired";

const ORDER_COLUMNS: (keyof OrderRow)[] = [
  "m",
  "n",
  "r_theta_deg",
  "r_phi_deg",
  "R",
  "r_te_abs",
  "r_te_phase_deg",
  "r_tm_abs",
  "r_tm_phase_deg",
  "T",
];

export function DiffractionPanel() {
  const run = useRunState();
  const view = useView((s) => s.diffraction);
  const setView = useView((s) => s.setView);
  const pol = usePol("diffraction", run.pols);
  const te = useOrders(run.runId, run.done && run.pols.includes("TE"), "TE");
  const tm = useOrders(run.runId, run.done && run.pols.includes("TM"), "TM");
  const pupil = usePupil(run.runId, run.done, pol, view.na, view.reduction);
  const pupilBox = useRef<HTMLDivElement>(null);
  const pupilSize = useElementSize(pupilBox);
  const colors = useThemeColors();

  const current = (pol === "TE" ? te : tm).data?.orders ?? [];
  const byPol = useMemo(() => {
    const out: Partial<Record<Polarization, OrderRow[]>> = {};
    if (te.data) out.TE = te.data.orders;
    if (tm.data) out.TM = tm.data.orders;
    return out;
  }, [te.data, tm.data]);

  const barOption = useMemo<EChartsOption>(() => {
    const propagating = (byPol[pol] ?? []).filter((o) => o.r_propagating);
    const labels = propagating.map((o) => `(${o.m},${o.n})`);
    let smallest = Number.POSITIVE_INFINITY;
    const series = (Object.entries(byPol) as [Polarization, OrderRow[]][]).map(([p, rows]) => {
      const map = new Map(rows.map((o) => [`(${o.m},${o.n})`, o.R]));
      return {
        type: "bar",
        name: `R ${p}`,
        data: labels.map((l) => {
          const v = map.get(l) ?? null;
          if (v !== null && v > 0) smallest = Math.min(smallest, v);
          return view.log && v !== null && v <= 0 ? null : v;
        }),
        barMaxWidth: 26,
      };
    });
    const floor = Number.isFinite(smallest) ? 10 ** Math.floor(Math.log10(smallest)) : 1e-6;
    return {
      animation: false,
      grid: { left: 64, right: 16, top: 34, bottom: 46 },
      legend: { top: 4, right: 8 },
      tooltip: { trigger: "axis", valueFormatter: (v: number) => fmt(v, 5) },
      xAxis: { type: "category", data: labels, name: "order (m, n)", nameLocation: "middle", nameGap: 30 },
      yAxis: {
        type: view.log ? "log" : "value",
        // Log-scale bars rise from a decade below the smallest value instead of hanging from 1.
        ...(view.log ? { min: floor, startValue: floor } : {}),
        name: "efficiency",
        nameLocation: "middle",
        nameGap: 48,
        axisLabel: { formatter: (v: number) => fmt(v, 2) },
      },
      dataZoom: [{ type: "inside", xAxisIndex: 0 }],
      series,
    };
  }, [byPol, pol, view.log]);

  const pupilOption = useMemo<EChartsOption>(() => {
    const p = pupil.data;
    const circle = (cx: number, cy: number, r: number) =>
      Array.from({ length: 181 }, (_, i) => [
        cx + r * Math.cos((i / 90) * Math.PI),
        cy + r * Math.sin((i / 90) * Math.PI),
      ]);
    const rMax = p ? Math.max(...p.R, 1e-30) : 1;
    const series: object[] = [
      {
        type: "line",
        name: "propagation cutoff",
        data: circle(0, 0, 1),
        showSymbol: false,
        silent: true,
        lineStyle: { type: "dashed", width: 1, color: colors.muted },
      },
    ];
    if (p?.na_mask)
      series.push({
        type: "line",
        name: `NA ${view.na} / ${view.reduction}×`,
        data: circle(p.center[0], p.center[1], p.na_mask),
        showSymbol: false,
        silent: true,
        lineStyle: { width: 1.5, color: "#E45756" },
      });
    series.push({
      type: "scatter",
      name: "orders",
      data: p ? p.sx.map((x, i) => [x, p.sy[i], p.R[i], p.phase_deg[i] ?? 0, p.m[i], p.n[i]]) : [],
      symbolSize: (d: number[]) => 6 + 34 * Math.sqrt(Math.max(d[2], 0) / rMax),
      itemStyle: { borderColor: colors.foreground, borderWidth: 0.6 },
      z: 5,
    });
    return {
      animation: false,
      grid: squareGrid(pupilSize, { left: 48, right: 72, top: 14, bottom: 40 }),
      tooltip: {
        trigger: "item",
        formatter: (item: { seriesType: string; data: number[] }) =>
          item.seriesType === "scatter"
            ? `order (${item.data[4]},${item.data[5]})<br/>R = ${fmt(item.data[2], 5)}<br/>phase = ${fixed(item.data[3], 1)}°`
            : "",
      },
      xAxis: { type: "value", min: -1.05, max: 1.05, name: "kx / (k₀ n)", nameLocation: "middle", nameGap: 24 },
      yAxis: { type: "value", min: -1.05, max: 1.05, name: "ky / (k₀ n)", nameLocation: "middle", nameGap: 30 },
      visualMap: {
        type: "continuous",
        seriesIndex: series.length - 1,
        dimension: 3,
        min: -180,
        max: 180,
        calculable: false,
        orient: "vertical",
        right: 4,
        top: "middle",
        itemHeight: 140,
        text: ["180°", "−180°"],
        textStyle: { color: colors.muted, fontSize: 10 },
        inRange: { color: colormapStops("twilight") },
      },
      series,
    };
  }, [pupil.data, colors, view.na, view.reduction, pupilSize]);

  const columns = useMemo<ColDef<OrderRow>[]>(
    () => [
      { headerName: "m", field: "m", width: 56 },
      { headerName: "n", field: "n", width: 56 },
      { headerName: "θ out (°)", field: "r_theta_deg", width: 84, valueFormatter: (p) => fixed(p.value, 3) },
      { headerName: "φ out (°)", field: "r_phi_deg", width: 84, valueFormatter: (p) => fixed(p.value, 2) },
      { headerName: "R", field: "R", width: 96, valueFormatter: (p) => fmt(p.value, 5), sort: undefined },
      { headerName: "|r_TE|", field: "r_te_abs", width: 86, valueFormatter: (p) => fmt(p.value, 4) },
      { headerName: "∠r_TE (°)", field: "r_te_phase_deg", width: 92, valueFormatter: (p) => fixed(p.value, 2) },
      { headerName: "|r_TM|", field: "r_tm_abs", width: 86, valueFormatter: (p) => fmt(p.value, 4) },
      { headerName: "∠r_TM (°)", field: "r_tm_phase_deg", width: 92, valueFormatter: (p) => fixed(p.value, 2) },
      { headerName: "T", field: "T", width: 96, valueFormatter: (p) => fmt(p.value, 5) },
    ],
    [],
  );

  if (!run.done) return <RunRequired run={run} what="diffraction efficiencies, the pupil, and the order table" />;

  const power: Partial<RunSummary["power"]> = run.summary?.power ?? {};
  const unpolarized =
    run.pols.length > 1 ? run.pols.reduce((sum, p) => sum + (power[p]?.R_total ?? 0), 0) / run.pols.length : null;

  return (
    <PanelLayout
      toolbar={
        <>
          <ToolbarItem label="Polarization">
            <PolarizationPicker panel="diffraction" pols={run.pols} />
          </ToolbarItem>
          <ToolbarItem label="Log scale">
            <Switch checked={view.log} onCheckedChange={(log) => setView("diffraction", { log })} size="sm" />
          </ToolbarItem>
          <ToolbarItem label="Wafer NA">
            <NumberField
              className="w-20"
              value={view.na}
              onChange={(na) => setView("diffraction", { na })}
              min={0}
              max={1.35}
              step={0.01}
              digits={3}
            />
          </ToolbarItem>
          <ToolbarItem label="Reduction">
            <NumberField
              className="w-20"
              value={view.reduction}
              onChange={(reduction) => setView("diffraction", { reduction })}
              min={1}
              max={10}
              step={1}
              unit="×"
              digits={2}
            />
          </ToolbarItem>
          {run.stale && (
            <span className="text-[11px] text-amber-600 dark:text-amber-400">Results are from earlier inputs</span>
          )}
        </>
      }
    >
      <div className="space-y-3">
        <div className="grid grid-cols-[repeat(auto-fill,minmax(130px,1fr))] gap-2">
          {run.pols.map((p) => (
            <Stat key={`R${p}`} label={`R total (${p})`} value={fmt(power[p]?.R_total, 5)} />
          ))}
          {run.pols.map((p) => (
            <Stat key={`T${p}`} label={`T total (${p})`} value={fmt(power[p]?.T_total, 5)} />
          ))}
          {run.pols.map((p) => (
            <Stat key={`A${p}`} label={`Absorbed (${p})`} value={fmt(power[p]?.A_total, 5)} />
          ))}
          {unpolarized !== null && <Stat label="R unpolarized" value={fmt(unpolarized, 5)} />}
          {pupil.data?.captured !== null && pupil.data?.captured !== undefined && (
            <Stat
              label={`R inside NA (${pol})`}
              value={fmt(pupil.data.captured, 5)}
              hint={`mask-side NA ${fmt(pupil.data.na_mask, 3)}`}
            />
          )}
        </div>
        <div className="grid grid-cols-[repeat(auto-fit,minmax(420px,1fr))] gap-3">
          <ViewCard
            title="Reflected efficiency per order"
            subtitle="propagating orders"
            className="h-[400px]"
            loading={te.isFetching || tm.isFetching}
            errors={te.error || tm.error ? errorMessages(te.error ?? tm.error) : undefined}
          >
            <EChart option={barOption} />
          </ViewCard>
          <ViewCard
            title="Pupil"
            subtitle={`size ∝ √R, color = phase of the ${pupil.data?.basis ?? pol} component`}
            className="h-[400px]"
            loading={pupil.isFetching}
            errors={pupil.error ? errorMessages(pupil.error) : undefined}
          >
            <div ref={pupilBox} className="h-full w-full">
              <EChart option={pupilOption} />
            </div>
          </ViewCard>
        </div>
        <ViewCard
          title={`Orders (${pol})`}
          subtitle="amplitudes and phases at z = 0 in each order's own TE/TM basis"
          className="h-[360px]"
          actions={
            <Button
              size="sm"
              variant="ghost"
              onClick={() => downloadText(toCsv(current, ORDER_COLUMNS), `orders_${pol}.csv`)}
              disabled={!current.length}
            >
              <HugeiconsIcon icon={Download04Icon} data-icon="inline-start" />
              CSV
            </Button>
          }
        >
          <DataGrid<OrderRow> rowData={current} columnDefs={columns} className="h-full" />
        </ViewCard>
      </div>
    </PanelLayout>
  );
}
