// Parameter sweeps: efficiency and phase of selected orders vs one parameter. Points
// stream in as each value is solved.
import { Download04Icon, PlayIcon, StopIcon } from "@hugeicons/core-free-icons";
import { HugeiconsIcon } from "@hugeicons/react";
import { useEffect, useMemo } from "react";
import { ApiError, errorMessages } from "@/api/client";
import { FINISHED, useCancelJob, useJob, useSubmitSweep, useSweep } from "@/api/hooks";
import type { SweepRecord } from "@/api/model";
import { SelectField, ToolbarItem } from "@/components/controls";
import { EmptyState, PanelLayout, ViewCard } from "@/components/layout";
import { NumberField } from "@/components/number-field";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { Toggle } from "@/components/ui/toggle";
import { downloadText, toCsv } from "@/lib/download";
import { fixed, fmt } from "@/lib/format";
import { useProject } from "@/state/project";
import { useSession } from "@/state/session";
import { useView } from "@/state/view";
import { EChart, type EChartsOption } from "@/viz/EChart";
import { useThemeColors } from "@/viz/theme";
import { useStack } from "./common";

const orderLabel = (r: Pick<SweepRecord, "m" | "n">) => `(${r.m},${r.n})`;

/** [value, phase] points with 360° jumps removed (phases are only defined modulo 360°). */
function unwrapDegrees(points: SweepRecord[]): (number | null)[][] {
  const sorted = [...points].sort((a, b) => a.value - b.value);
  let offset = 0;
  let previous: number | null = null;
  return sorted.map((r) => {
    if (r.phase_deg === null || r.phase_deg === undefined) return [r.value, null];
    let phase = r.phase_deg + offset;
    if (previous !== null) {
      while (phase - previous > 180) {
        phase -= 360;
        offset -= 360;
      }
      while (phase - previous < -180) {
        phase += 360;
        offset += 360;
      }
    }
    previous = phase;
    return [r.value, phase];
  });
}

export function SweepPanel() {
  const project = useProject();
  const { check, errors } = useStack();
  const view = useView((s) => s.sweep);
  const setView = useView((s) => s.setView);
  const sweepId = useSession((s) => s.sweepId);
  const setSweep = useSession((s) => s.setSweep);
  const jobQuery = useJob(sweepId);
  const job = jobQuery.data;
  const sweep = useSweep(sweepId);
  useEffect(() => {
    if (jobQuery.error instanceof ApiError && jobQuery.error.status === 404) setSweep(null);
  }, [jobQuery.error, setSweep]);
  const submit = useSubmitSweep();
  const cancel = useCancelJob();
  const colors = useThemeColors();

  const parameters = check?.sweep_parameters ?? [];
  const parameter = parameters.find((p) => p.key === view.parameter) ?? parameters[0];

  // Adopt the parameter's default range when switching parameters.
  useEffect(() => {
    if (parameter && parameter.key !== view.parameter)
      setView("sweep", {
        parameter: parameter.key,
        start: parameter.start,
        stop: parameter.stop,
        points: parameter.points,
      });
  }, [parameter, view.parameter, setView]);

  const records = sweep.data?.records ?? [];
  const running = !!job && !FINISHED.has(job.status);

  const orderRanking = useMemo(() => {
    const best = new Map<string, number>();
    for (const r of records)
      if (r.m !== null && r.m !== undefined) best.set(orderLabel(r), Math.max(best.get(orderLabel(r)) ?? 0, r.R));
    return [...best.entries()].sort((a, b) => b[1] - a[1]).map(([label]) => label);
  }, [records]);
  const chosen = view.orders.filter((o) => orderRanking.includes(o));
  const shown = chosen.length ? chosen : orderRanking.slice(0, 3);

  const options = useMemo(() => {
    const pols = [...new Set(records.map((r) => r.pol))];
    const xName = sweep.data?.label ?? parameter?.label ?? "";
    const base = (yName: string): EChartsOption => ({
      animation: false,
      grid: { left: 64, right: 16, top: 34, bottom: 44 },
      legend: { top: 4, type: "scroll" },
      tooltip: { trigger: "axis", valueFormatter: (v: number) => fmt(v, 5) },
      xAxis: { type: "value", name: xName, nameLocation: "middle", nameGap: 28, scale: true },
      yAxis: { type: "value", name: yName, nameLocation: "middle", nameGap: 48, scale: true },
      dataZoom: [{ type: "inside", xAxisIndex: 0, filterMode: "none" }],
    });
    const efficiency = base("reflected efficiency");
    const phase = base("phase (deg)");
    const rSeries: object[] = [];
    const pSeries: object[] = [];
    pols.forEach((pol) => {
      const dashed = pol === "TM" ? "dashed" : "solid";
      const rows = records.filter((r) => r.pol === pol);
      rSeries.push({
        type: "line",
        name: `total ${pol}`,
        data: rows.filter((r) => r.m === null || r.m === undefined).map((r) => [r.value, r.R]),
        lineStyle: { type: dashed, color: colors.foreground },
        itemStyle: { color: colors.foreground },
      });
      shown.forEach((label, i) => {
        const pts = rows.filter((r) => r.m !== null && r.m !== undefined && orderLabel(r) === label);
        const color = colors.series[i % colors.series.length];
        rSeries.push({
          type: "line",
          name: `${label} ${pol}`,
          data: pts.map((r) => [r.value, r.R]),
          lineStyle: { type: dashed, color },
          itemStyle: { color },
        });
        pSeries.push({
          type: "line",
          name: `${label} ${pol}`,
          data: unwrapDegrees(pts),
          lineStyle: { type: dashed, color },
          itemStyle: { color },
          connectNulls: false,
        });
      });
    });
    return { efficiency: { ...efficiency, series: rSeries }, phase: { ...phase, series: pSeries } };
  }, [records, shown, sweep.data?.label, parameter?.label, colors]);

  const start = () => {
    if (!parameter) return;
    submit.mutate(
      { project, parameter: parameter.key, start: view.start, stop: view.stop, points: view.points },
      { onSuccess: (j) => setSweep(j.id) },
    );
  };

  return (
    <PanelLayout
      toolbar={
        <>
          <ToolbarItem label="Sweep">
            <SelectField
              size="sm"
              className="w-64"
              value={parameter?.key ?? ""}
              onChange={(key) => {
                const p = parameters.find((q) => q.key === key);
                if (p) setView("sweep", { parameter: p.key, start: p.start, stop: p.stop, points: p.points });
              }}
              options={parameters.map((p) => ({ value: p.key, label: p.label }))}
            />
          </ToolbarItem>
          <ToolbarItem label="from">
            <NumberField
              className="w-24"
              value={view.start}
              onChange={(v) => setView("sweep", { start: v })}
              step={0.5}
            />
          </ToolbarItem>
          <ToolbarItem label="to">
            <NumberField
              className="w-24"
              value={view.stop}
              onChange={(v) => setView("sweep", { stop: v })}
              step={0.5}
            />
          </ToolbarItem>
          <ToolbarItem label="points">
            <NumberField
              className="w-20"
              value={view.points}
              onChange={(v) => setView("sweep", { points: Math.max(2, Math.round(v)) })}
              min={2}
              max={401}
              digits={0}
            />
          </ToolbarItem>
          {running ? (
            <Button size="sm" variant="destructive" onClick={() => job && cancel.mutate(job)}>
              <HugeiconsIcon icon={StopIcon} data-icon="inline-start" />
              Stop
            </Button>
          ) : (
            <Button size="sm" onClick={start} disabled={!parameter || errors.length > 0 || submit.isPending}>
              <HugeiconsIcon icon={PlayIcon} data-icon="inline-start" />
              Run sweep
            </Button>
          )}
          {running && job && (
            <div className="flex w-48 items-center gap-2">
              <Progress value={Math.round(job.progress * 100)} className="flex-1" />
              <span className="text-[11px] text-muted-foreground tabular-nums">{Math.round(job.progress * 100)}%</span>
            </div>
          )}
          {submit.error && (
            <span className="text-[11px] text-destructive">{errorMessages(submit.error).join("; ")}</span>
          )}
          {job?.status === "failed" && <span className="text-[11px] text-destructive">{job.error}</span>}
        </>
      }
    >
      {!sweepId || (!records.length && !running) ? (
        <EmptyState title="No sweep yet">
          Pick a parameter and range, then <b>Run sweep</b>. Each point is a full solve of the current stack; curves
          fill in as points finish.
        </EmptyState>
      ) : (
        <div className="space-y-3">
          <div className="flex flex-wrap items-center gap-1">
            <span className="mr-1 text-[11px] text-muted-foreground">Orders</span>
            {orderRanking.slice(0, 16).map((label) => (
              <Toggle
                key={label}
                size="sm"
                variant="outline"
                pressed={shown.includes(label)}
                onPressedChange={(on) =>
                  setView("sweep", { orders: on ? [...shown, label] : shown.filter((o) => o !== label) })
                }
                className="h-6 px-1.5 text-[11px] tabular-nums"
              >
                {label}
              </Toggle>
            ))}
            <Button
              size="sm"
              variant="ghost"
              className="ml-auto"
              onClick={() => downloadText(toCsv(records), `sweep_${sweep.data?.parameter ?? "parameter"}.csv`)}
              disabled={!records.length}
            >
              <HugeiconsIcon icon={Download04Icon} data-icon="inline-start" />
              CSV
            </Button>
          </div>
          <div className="grid grid-cols-[repeat(auto-fit,minmax(420px,1fr))] gap-3">
            <ViewCard
              title="Reflected efficiency"
              subtitle={`${new Set(records.map((r) => r.value)).size} of ${job?.params?.values ? (job.params.values as number[]).length : "?"} points · TE solid, TM dashed`}
              className="h-[420px]"
              loading={sweep.isFetching}
            >
              <EChart option={options.efficiency} />
            </ViewCard>
            <ViewCard
              title="Reflected phase"
              subtitle="order's own TE (or TM) component, unwrapped"
              className="h-[420px]"
            >
              <EChart option={options.phase} />
            </ViewCard>
          </div>
          {job?.status === "done" && job.finished && job.started && (
            <div className="text-[11px] text-muted-foreground">
              Finished in {fixed(job.finished - job.started, 1)} s.
            </div>
          )}
        </div>
      )}
    </PanelLayout>
  );
}
