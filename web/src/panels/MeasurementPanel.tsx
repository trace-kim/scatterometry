// Measured CCD frames from SPE files (Princeton Instruments / LightField). Files upload to
// the server, which keeps them in memory and serves frames as arrays; contrast, colormap,
// profiles, and statistics are computed here, so they redraw without a round trip.
import { Delete02Icon, FolderOpenIcon } from "@hugeicons/core-free-icons";
import { HugeiconsIcon } from "@hugeicons/react";
import { type DragEvent, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import { errorMessages } from "@/api/client";
import {
  useDeleteMeasurement,
  useMeasurementFrame,
  useMeasurementSettings,
  useMeasurements,
  useMeasurementTrace,
  useUploadMeasurement,
} from "@/api/hooks";
import type { MeasurementInfo, SettingRow } from "@/api/model";
import { Note, Segmented, SelectField, ToolbarItem } from "@/components/controls";
import { DataGrid } from "@/components/data-grid";
import { EmptyState, PanelLayout, Stat, ViewCard } from "@/components/layout";
import { NumberField } from "@/components/number-field";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
import { COLORMAPS } from "@/lib/colormaps";
import { fixed, fmt, seconds } from "@/lib/format";
import { bytes, contrastRange, frameStats, profiles, saturationLevel } from "@/lib/measurement";
import { cn } from "@/lib/utils";
import { useSession } from "@/state/session";
import { useView } from "@/state/view";
import { EChart, type EChartsInstance, type EChartsOption } from "@/viz/EChart";
import { Heatmap } from "@/viz/Heatmap";
import { useThemeColors } from "@/viz/theme";

const CLIP_OPTIONS = [
  { value: 0, label: "Full range" },
  { value: 0.01, label: "Clip 0.01 %" },
  { value: 0.1, label: "Clip 0.1 %" },
  { value: 1, label: "Clip 1 %" },
];

/** The uploaded measurements and the one shown (the session's choice, else the newest). */
function useCurrentMeasurement() {
  const list = useMeasurements();
  const chosenId = useSession((s) => s.measurementId);
  const items = list.data ?? [];
  const current = items.find((m) => m.id === chosenId) ?? items[items.length - 1] ?? null;
  return { list, items, current };
}

export function MeasurementPanel() {
  const { list, items, current } = useCurrentMeasurement();
  const setMeasurement = useSession((s) => s.setMeasurement);
  const view = useView((s) => s.measurement);
  const setView = useView((s) => s.setView);
  const upload = useUploadMeasurement();
  const remove = useDeleteMeasurement();
  const fileInput = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  const open = (files: FileList | File[] | null) => {
    for (const file of Array.from(files ?? [])) {
      upload.mutate(file, {
        onSuccess: (info) => {
          setMeasurement(info.id);
          toast.success(`Opened ${info.name}`, {
            description: info.warnings.length ? info.warnings.join("; ") : undefined,
          });
        },
        onError: (error) => toast.error(`Couldn't open ${file.name}`, { description: errorMessages(error).join("; ") }),
      });
    }
  };

  const onDrop = (event: DragEvent) => {
    event.preventDefault();
    setDragging(false);
    open(event.dataTransfer.files);
  };

  return (
    <PanelLayout
      toolbar={
        <>
          <Button size="sm" variant="outline" onClick={() => fileInput.current?.click()} disabled={upload.isPending}>
            <HugeiconsIcon icon={FolderOpenIcon} data-icon="inline-start" />
            {upload.isPending ? "Uploading…" : "Open .spe"}
          </Button>
          {items.length > 0 && current && (
            <ToolbarItem label="File">
              <SelectField
                size="sm"
                className="w-56"
                value={current.id}
                onChange={setMeasurement}
                options={items.map((m) => ({ value: m.id, label: m.name }))}
                aria-label="Measurement"
              />
              <Button
                size="icon-xs"
                variant="ghost"
                title="Remove this file from the server"
                aria-label="Remove file"
                onClick={() => remove.mutate(current.id, { onSuccess: () => setMeasurement(null) })}
              >
                <HugeiconsIcon icon={Delete02Icon} />
              </Button>
            </ToolbarItem>
          )}
          <ToolbarItem label="Scale">
            <Segmented
              value={view.scale}
              onChange={(scale) => setView("measurement", { scale })}
              options={[
                { value: "linear", label: "Linear" },
                { value: "log", label: "Log" },
              ]}
              aria-label="Intensity scale"
            />
          </ToolbarItem>
          <ToolbarItem label="Contrast">
            <SelectField
              size="sm"
              className="w-28"
              value={view.clip}
              onChange={(clip) => setView("measurement", { clip })}
              options={CLIP_OPTIONS}
              aria-label="Contrast"
            />
          </ToolbarItem>
          <ToolbarItem label="Colormap">
            <SelectField
              size="sm"
              className="w-32"
              value={view.colormap}
              onChange={(colormap) => setView("measurement", { colormap })}
              options={COLORMAPS.map((c) => ({ value: c.value, label: c.label }))}
            />
          </ToolbarItem>
          <input
            ref={fileInput}
            type="file"
            accept=".spe,.SPE"
            multiple
            hidden
            data-testid="measurement-file"
            onChange={(e) => {
              open(e.target.files);
              e.target.value = "";
            }}
          />
        </>
      }
      className="p-0"
    >
      <section
        aria-label="Measurement drop zone"
        className={cn(
          "h-full overflow-auto p-3",
          dragging && "bg-primary/5 outline-2 -outline-offset-4 outline-primary",
        )}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
      >
        {current ? (
          <MeasurementView key={current.id} info={current} />
        ) : (
          <EmptyState
            title={list.isLoading ? "Loading…" : "No measurement open"}
            icon={<HugeiconsIcon icon={FolderOpenIcon} className="size-6 text-muted-foreground" />}
          >
            Drop a camera file (.spe, from LightField or WinView) here, or use <b>Open .spe</b>. Files are kept by the
            server until it restarts.
          </EmptyState>
        )}
      </section>
    </PanelLayout>
  );
}

function MeasurementView({ info }: { info: MeasurementInfo }) {
  const view = useView((s) => s.measurement);
  const setView = useView((s) => s.setView);
  const colors = useThemeColors();
  const [region, setRegion] = useState(0);
  const [frame, setFrame] = useState(0);
  const [pick, setPick] = useState<[number, number] | null>(null);
  const multiFrame = info.frames > 1;
  const average = multiFrame && view.average;

  const data = useMeasurementFrame(info.id, region, frame, average);
  const trace = useMeasurementTrace(info.id, region, multiFrame);
  const counts = data.data?.counts;
  const xs = data.data?.x_px.data;
  const ys = data.data?.y_px.data;
  const height = counts?.shape[0] ?? 0;
  const width = counts?.shape[1] ?? 0;

  // Pick the brightest pixel until the user clicks one (the zero order, usually).
  useEffect(() => {
    if (!counts || pick) return;
    let best = 0;
    for (let i = 1; i < counts.data.length; i++) if (counts.data[i] > counts.data[best]) best = i;
    setPick([best % width, Math.floor(best / width)]);
  }, [counts, pick, width]);

  const stats = useMemo(
    () => (counts ? frameStats(counts.data, average ? null : saturationLevel(counts.dtype)) : null),
    [counts, average],
  );
  const domain = useMemo(
    () => (counts ? contrastRange(counts.data, view.clip, view.scale) : { min: 0, max: 1 }),
    [counts, view.clip, view.scale],
  );
  const lines = useMemo(
    () => (counts && pick ? profiles(counts.data, width, height, pick[0], pick[1]) : null),
    [counts, pick, width, height],
  );
  const marker = useMemo<[number, number] | null>(
    () => (pick && xs && ys && pick[0] < xs.length && pick[1] < ys.length ? [xs[pick[0]], ys[pick[1]]] : null),
    [pick, xs, ys],
  );

  const regionInfo = info.regions[region];
  const binned = regionInfo && (regionInfo.x_binning > 1 || regionInfo.y_binning > 1);
  const frameLabel = average ? `mean of ${info.frames} frames` : `frame ${frame + 1} of ${info.frames}`;

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5">
        {info.regions.length > 1 && (
          <ToolbarItem label="Region">
            <SelectField
              size="sm"
              className="w-44"
              value={region}
              onChange={(r) => {
                setRegion(r);
                setPick(null);
              }}
              options={info.regions.map((r) => ({ value: r.index, label: `${r.index + 1}: ${r.width} × ${r.height}` }))}
            />
          </ToolbarItem>
        )}
        {multiFrame && (
          <>
            <ToolbarItem label="Frame">
              <Slider
                className="data-horizontal:w-48"
                min={0}
                max={info.frames - 1}
                step={1}
                value={[frame]}
                disabled={average}
                onValueChange={(v) => setFrame((Array.isArray(v) ? v[0] : v) as number)}
              />
              <NumberField
                className="w-20"
                value={frame + 1}
                min={1}
                max={info.frames}
                digits={0}
                onChange={(v) => setFrame(Math.max(0, Math.min(info.frames - 1, Math.round(v) - 1)))}
                aria-label="Frame number"
              />
            </ToolbarItem>
            <ToolbarItem label="Mean of all frames">
              <Switch
                aria-label="Mean of all frames"
                size="sm"
                checked={view.average}
                onCheckedChange={(on) => setView("measurement", { average: on })}
              />
            </ToolbarItem>
          </>
        )}
        {stats && (
          <span className="ml-auto text-[11px] text-muted-foreground tabular-nums">
            min {fmt(stats.min, 5)} · max {fmt(stats.max, 5)} · mean {fmt(stats.mean, 5)}
            {stats.saturated ? (
              <span className="ml-1 font-medium text-destructive">· {stats.saturated} saturated px</span>
            ) : null}
          </span>
        )}
      </div>
      {info.warnings.map((w) => (
        <Note key={w} tone="warn">
          {w}
        </Note>
      ))}

      <div className="grid grid-cols-[repeat(auto-fit,minmax(420px,1fr))] gap-3">
        <ViewCard
          title="Frame"
          subtitle={`${width} × ${height} px · ${frameLabel} · ${average ? "float32" : info.dtype}${binned ? ` · binned ${regionInfo.x_binning}×${regionInfo.y_binning}` : ""}`}
          className="col-span-full h-[580px]"
          loading={data.isFetching}
          errors={data.error ? errorMessages(data.error) : undefined}
        >
          {counts && xs && ys && (
            <Heatmap
              values={counts.data}
              width={width}
              height={height}
              x={xs}
              y={ys}
              yDown
              equalAspect
              colormap={view.colormap}
              domain={domain}
              scale={view.scale}
              valueLabel="counts"
              formatValue={(v) => fmt(v, 6)}
              xLabel="x (sensor px)"
              yLabel="y (sensor px)"
              describe={(_x, _y, index) => `column ${index % width}, row ${Math.floor(index / width)}`}
              onPick={(column, row) => setPick([column, row])}
              marker={marker}
            />
          )}
        </ViewCard>
        <ViewCard
          title="Row profile"
          subtitle={marker ? `y = ${fixed(marker[1], 1)} px · click the frame to move` : ""}
          className="h-[300px]"
        >
          {lines && xs && (
            <ProfileChart x={xs} values={lines.row} xName="x (sensor px)" log={view.scale === "log"} at={marker?.[0]} />
          )}
        </ViewCard>
        <ViewCard title="Column profile" subtitle={marker ? `x = ${fixed(marker[0], 1)} px` : ""} className="h-[300px]">
          {lines && ys && (
            <ProfileChart
              x={ys}
              values={lines.column}
              xName="y (sensor px)"
              log={view.scale === "log"}
              at={marker?.[1]}
            />
          )}
        </ViewCard>
        {multiFrame && (
          <ViewCard
            title="Frame series"
            subtitle="total and peak counts per frame · click to show a frame"
            className="h-[300px]"
            loading={trace.isFetching}
            errors={trace.error ? errorMessages(trace.error) : undefined}
          >
            {trace.data && (
              <TraceChart
                total={trace.data.total}
                peak={trace.data.max}
                time={trace.data.time_s ?? null}
                current={average ? null : frame}
                onPick={(f) => {
                  setFrame(f);
                  setView("measurement", { average: false });
                }}
                colors={colors.series}
              />
            )}
          </ViewCard>
        )}
        <AcquisitionCard info={info} />
        <SettingsCard id={info.id} count={info.setting_count} />
      </div>
    </div>
  );
}

function ProfileChart(props: {
  x: ArrayLike<number>;
  values: ArrayLike<number>;
  xName: string;
  log: boolean;
  at?: number;
}) {
  const { x, values, xName, log, at } = props;
  const colors = useThemeColors();
  const option = useMemo<EChartsOption>(() => {
    const points: [number, number | null][] = [];
    for (let i = 0; i < values.length; i++) points.push([x[i], log && values[i] <= 0 ? null : values[i]]);
    return {
      animation: false,
      grid: { left: 64, right: 16, top: 16, bottom: 40 },
      tooltip: { trigger: "axis", valueFormatter: (v: number) => fmt(v, 6) },
      xAxis: { type: "value", name: xName, nameLocation: "middle", nameGap: 26, min: "dataMin", max: "dataMax" },
      yAxis: { type: log ? "log" : "value", name: "counts", nameLocation: "middle", nameGap: 48, scale: true },
      dataZoom: [{ type: "inside", xAxisIndex: 0, filterMode: "none" }],
      series: [
        {
          type: "line",
          name: "counts",
          data: points,
          showSymbol: false,
          step: "middle",
          lineStyle: { width: 1, color: colors.series[0] },
          itemStyle: { color: colors.series[0] },
          markLine:
            at === undefined
              ? undefined
              : {
                  silent: true,
                  symbol: "none",
                  label: { show: false },
                  lineStyle: { color: "#4fc3f7", type: "dashed" },
                  data: [{ xAxis: at }],
                },
        },
      ],
    };
  }, [x, values, xName, log, at, colors.series]);
  return <EChart option={option} />;
}

function TraceChart(props: {
  total: number[];
  peak: number[];
  time: number[] | null;
  current: number | null;
  onPick: (frame: number) => void;
  colors: string[];
}) {
  const { total, peak, time, current, colors } = props;
  const latest = useRef(props);
  latest.current = props;
  const option = useMemo<EChartsOption>(
    () => ({
      animation: false,
      grid: { left: 64, right: 64, top: 30, bottom: 40 },
      legend: { top: 2 },
      tooltip: {
        trigger: "axis",
        formatter: (items: { dataIndex: number }[]) => {
          const i = items[0]?.dataIndex ?? 0;
          const at = time ? ` · t = ${seconds(time[i])}` : "";
          return `frame ${i + 1}${at}<br/>total ${fmt(total[i], 6)}<br/>peak ${fmt(peak[i], 6)}`;
        },
      },
      xAxis: {
        type: "value",
        name: "frame",
        nameLocation: "middle",
        nameGap: 26,
        min: 1,
        max: Math.max(total.length, 2),
      },
      yAxis: [
        { type: "value", name: "total counts", nameLocation: "middle", nameGap: 48, scale: true },
        { type: "value", name: "peak", nameLocation: "middle", nameGap: 44, scale: true, splitLine: { show: false } },
      ],
      series: [
        {
          type: "line",
          name: "total",
          data: total.map((v, i) => [i + 1, v]),
          showSymbol: total.length < 60,
          lineStyle: { color: colors[0] },
          itemStyle: { color: colors[0] },
          markLine:
            current === null
              ? undefined
              : { silent: true, symbol: "none", label: { show: false }, data: [{ xAxis: current + 1 }] },
        },
        {
          type: "line",
          name: "peak",
          yAxisIndex: 1,
          data: peak.map((v, i) => [i + 1, v]),
          showSymbol: false,
          lineStyle: { color: colors[1], width: 1 },
          itemStyle: { color: colors[1] },
        },
      ],
    }),
    [total, peak, time, current, colors],
  );
  const onInit = (chart: EChartsInstance) => {
    const zr = chart.getZr();
    const click = (event: { offsetX: number; offsetY: number }) => {
      const point = [event.offsetX, event.offsetY];
      if (!chart.containPixel("grid", point)) return;
      const [x] = chart.convertFromPixel({ gridIndex: 0 }, point) as number[];
      const n = latest.current.total.length;
      latest.current.onPick(Math.max(0, Math.min(n - 1, Math.round(x) - 1)));
    };
    zr.on("click", click);
    return () => zr.off("click", click);
  };
  return <EChart option={option} onInit={onInit} />;
}

const SUMMARY_LABELS: Record<string, [string, (v: unknown) => string]> = {
  created: ["Acquired", (v) => String(v).replace("T", " ").slice(0, 19)],
  camera: ["Camera", String],
  exposure_s: ["Exposure", (v) => seconds(Number(v))],
  temperature_c: ["Sensor temperature", (v) => `${fixed(Number(v), 1)} °C`],
  temperature_set_c: ["Temperature set point", (v) => `${fixed(Number(v), 1)} °C`],
  adc_speed_mhz: ["ADC speed", (v) => `${fmt(Number(v), 4)} MHz`],
  adc_gain: ["ADC gain", String],
  adc_quality: ["ADC quality", String],
  em_gain: ["EM gain", (v) => fmt(Number(v), 4)],
  readout: ["Readout", String],
  accumulations: ["Accumulations", (v) => String(v)],
  readout_time_ms: ["Readout time", (v) => `${fmt(Number(v), 4)} ms`],
  adc_rate: ["ADC rate code", String],
  geometric: ["Geometric correction", String],
  software: ["Written by", String],
};

function AcquisitionCard({ info }: { info: MeasurementInfo }) {
  const entries = Object.entries(info.summary).filter(([key]) => key !== "comments");
  const comments = info.summary.comments as string | undefined;
  return (
    <ViewCard
      title="Acquisition"
      subtitle={`SPE ${info.version.toFixed(1)} · ${bytes(info.size_bytes)}`}
      bodyClassName="overflow-auto p-2.5"
    >
      <div className="grid grid-cols-[repeat(auto-fill,minmax(150px,1fr))] gap-2">
        <Stat label="Frames" value={info.frames} />
        {info.sensor && <Stat label="Sensor" value={`${info.sensor[0]} × ${info.sensor[1]} px`} />}
        {info.regions.map((r) => (
          <Stat
            key={r.index}
            label={info.regions.length > 1 ? `Region ${r.index + 1}` : "Region"}
            value={`${r.width} × ${r.height} px`}
            hint={`at (${r.x}, ${r.y}) · bin ${r.x_binning}×${r.y_binning}`}
          />
        ))}
        {entries.map(([key, value]) => {
          const [label, format] = SUMMARY_LABELS[key] ?? [key, String];
          return <Stat key={key} label={label} value={format(value)} />;
        })}
      </div>
      {comments && <Note className="mt-2 break-all">Comments: {comments}</Note>}
    </ViewCard>
  );
}

const SETTING_COLUMNS = [
  { field: "path" as const, headerName: "Setting", flex: 2, minWidth: 200 },
  { field: "value" as const, headerName: "Value", flex: 1, minWidth: 120 },
];

function SettingsCard({ id, count }: { id: string; count: number }) {
  const settings = useMeasurementSettings(id);
  const [filter, setFilter] = useState("");
  const rows = useMemo<SettingRow[]>(() => {
    const words = filter.toLowerCase().split(/\s+/).filter(Boolean);
    const all = settings.data ?? [];
    if (!words.length) return all;
    return all.filter((r) => {
      const text = `${r.path} ${r.value}`.toLowerCase();
      return words.every((w) => text.includes(w));
    });
  }, [settings.data, filter]);
  return (
    <ViewCard
      title="All settings"
      subtitle={`${rows.length} of ${count}`}
      className="col-span-full h-[420px]"
      bodyClassName="flex flex-col gap-2 p-2.5"
      loading={settings.isFetching}
      errors={settings.error ? errorMessages(settings.error) : undefined}
      actions={
        <Input
          className="h-6 w-56 text-xs"
          placeholder="Filter, e.g. exposure"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          aria-label="Filter settings"
        />
      }
    >
      <DataGrid<SettingRow> className="min-h-0 flex-1" rowData={rows} columnDefs={SETTING_COLUMNS} />
    </ViewCard>
  );
}
