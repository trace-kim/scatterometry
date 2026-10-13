// Fields inside the mask for the current run. The server returns complex E components;
// quantity, colormap, scale, and time phase are all computed in the browser, so they
// redraw instantly (the phase can even be animated).
import { PauseIcon, PlayIcon } from "@hugeicons/core-free-icons";
import { HugeiconsIcon } from "@hugeicons/react";
import { useEffect, useMemo, useState } from "react";
import { errorMessages } from "@/api/client";
import { useAbsorption, useFieldPlane, useFieldSection, useFlux, useModes, useRunSlices } from "@/api/hooks";
import { SelectField, ToolbarItem } from "@/components/controls";
import { PanelLayout, ViewCard } from "@/components/layout";
import { Button } from "@/components/ui/button";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
import { type Domain, extent, symmetricExtent } from "@/lib/colorize";
import { COLORMAPS, type ColormapName } from "@/lib/colormaps";
import { FIELD_QUANTITIES, type FieldQuantity, fieldQuantity, quantityKind } from "@/lib/field";
import { fixed, fmt } from "@/lib/format";
import { useView } from "@/state/view";
import { EChart, type EChartsOption } from "@/viz/EChart";
import { Heatmap } from "@/viz/Heatmap";
import { useThemeColors } from "@/viz/theme";
import { PolarizationPicker, SectionControls, usePol, useRunState, useSectionParams } from "./common";
import { chooseSlice, describeSlice, sliceAtDepth, sliceOptions } from "./GeometryPanel";
import { RunRequired } from "./RunRequired";

function autoColormap(q: FieldQuantity): ColormapName {
  const kind = quantityKind(q);
  return kind === "signed" ? "rdbu" : kind === "phase" ? "twilight" : "inferno";
}

function domainFor(values: Float32Array, q: FieldQuantity, scale: "linear" | "log"): Domain {
  const kind = quantityKind(q);
  if (kind === "phase") return { min: -180, max: 180 };
  if (kind === "signed") return symmetricExtent(values);
  if (scale === "log") return extent(values, "log");
  return { min: 0, max: extent(values).max };
}

/** Time phase ωt in degrees, animated at ~90°/s while playing. */
function usePhase(playing: boolean) {
  const [phase, setPhase] = useState(0);
  useEffect(() => {
    if (!playing) return;
    let frame = 0;
    let last = performance.now();
    const tick = (now: number) => {
      setPhase((p) => (p + ((now - last) / 1000) * 90) % 360);
      last = now;
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [playing]);
  return [phase, setPhase] as const;
}

export function NearFieldPanel() {
  const run = useRunState();
  const view = useView((s) => s.nearfield);
  const setView = useView((s) => s.setView);
  const pol = usePol("nearfield", run.pols);
  const colors = useThemeColors();
  const [playing, setPlaying] = useState(false);
  const [phase, setPhase] = usePhase(playing);

  const slices = useRunSlices(run.runId, run.done).data ?? [];
  const params = useSectionParams("nearfield", { lateral: 400, z: 360 }, slices.length ? slices : undefined);
  const section = useFieldSection(run.runId, run.done && !!params, pol, params ?? ({} as never));
  const total = slices.length ? slices[slices.length - 1].z_top_nm + slices[slices.length - 1].thickness_nm : 100;
  const firstPatterned = slices.find((s) => s.patterned);
  const depth =
    view.depth ?? (firstPatterned ? Math.round(firstPatterned.z_top_nm + firstPatterned.thickness_nm / 2) : 0);
  const plane = useFieldPlane(run.runId, run.done, pol, depth, view.section.periods, 160);
  const flux = useFlux(run.runId, run.done, pol);
  const absorption = useAbsorption(run.runId, run.done, pol);
  const modeSlice = chooseSlice(view.slice, slices);
  const modes = useModes(run.runId, run.done && slices.length > 0, pol, modeSlice);

  const quantity = view.quantity;
  const colormap = view.colormap === "auto" ? autoColormap(quantity) : view.colormap;
  const scale = quantityKind(quantity) === "magnitude" ? view.scale : "linear";

  const sectionValues = useMemo(
    () => (section.data ? fieldQuantity(section.data as never, quantity, phase) : null),
    [section.data, quantity, phase],
  );
  const planeValues = useMemo(
    () => (plane.data ? fieldQuantity(plane.data as never, quantity, phase) : null),
    [plane.data, quantity, phase],
  );
  // Fix the range while animating so the colors don't breathe with the phase.
  const sectionDomain = useMemo(() => {
    if (!section.data) return { min: 0, max: 1 };
    if (quantityKind(quantity) === "signed") {
      const magnitude = fieldQuantity(section.data as never, `|${quantity.slice(-2)}|` as FieldQuantity);
      const max = extent(magnitude).max;
      return { min: -max, max };
    }
    return sectionValues ? domainFor(sectionValues, quantity, scale) : { min: 0, max: 1 };
  }, [section.data, quantity, scale, sectionValues]);
  const planeDomain = useMemo(() => {
    if (!plane.data) return { min: 0, max: 1 };
    if (quantityKind(quantity) === "signed") {
      const max = extent(fieldQuantity(plane.data as never, `|${quantity.slice(-2)}|` as FieldQuantity)).max;
      return { min: -max, max };
    }
    return planeValues ? domainFor(planeValues, quantity, scale) : { min: 0, max: 1 };
  }, [plane.data, quantity, scale, planeValues]);

  const fluxOption = useMemo<EChartsOption>(() => {
    const f = flux.data;
    return {
      animation: false,
      grid: { left: 58, right: 18, top: 16, bottom: 40 },
      tooltip: {
        trigger: "axis",
        axisPointer: { type: "line", axis: "y" },
        formatter: (items: { data: number[] }[]) =>
          items[0] ? `depth ${fixed(items[0].data[1], 2)} nm<br/>flux ${fmt(items[0].data[0], 5)}` : "",
      },
      xAxis: {
        type: "value",
        name: "net downward flux (1 = incident)",
        nameLocation: "middle",
        nameGap: 26,
        scale: true,
      },
      yAxis: {
        type: "value",
        inverse: true,
        name: "depth z (nm)",
        nameLocation: "middle",
        nameGap: 42,
        min: "dataMin",
        max: "dataMax",
      },
      dataZoom: [{ type: "inside", yAxisIndex: 0, filterMode: "none" }],
      series: [
        {
          type: "line",
          showSymbol: false,
          data: f ? f.z_nm.map((z, i) => [f.flux[i], z]) : [],
          lineStyle: { width: 1.8 },
          markLine: f
            ? {
                silent: true,
                symbol: "none",
                label: { show: false },
                // A 40-pair multilayer has 80 interfaces; mark the first ones only, faintly.
                lineStyle: { color: colors.muted, type: "solid", width: 1, opacity: 0.25 },
                data: f.interfaces_nm.slice(0, 16).map((z) => ({ yAxis: z })),
              }
            : undefined,
        },
      ],
    };
  }, [flux.data, colors]);

  const budgetOption = useMemo<EChartsOption>(() => {
    const a = absorption.data;
    const names = a ? [...a.layers.map((l) => l.name), "Reflected", "Transmitted"] : [];
    const values = a ? [...a.layers.map((l) => l.absorbed), a.R, a.T] : [];
    return {
      animation: false,
      grid: { left: 52, right: 12, top: 18, bottom: 56 },
      tooltip: { trigger: "axis", valueFormatter: (v: number) => fmt(v, 5) },
      xAxis: { type: "category", data: names, axisLabel: { rotate: 30, interval: 0, fontSize: 10 } },
      yAxis: { type: "value", name: "fraction of incident power", nameLocation: "middle", nameGap: 38 },
      series: [
        {
          type: "bar",
          data: values.map((v, i) => ({
            value: v,
            itemStyle: {
              color: i >= names.length - 2 ? colors.series[i === names.length - 2 ? 0 : 2] : colors.series[3],
            },
          })),
          label: { show: true, position: "top", fontSize: 10, formatter: (p: { value: number }) => fmt(p.value, 3) },
          barMaxWidth: 34,
        },
      ],
    };
  }, [absorption.data, colors]);

  const modesOption = useMemo<EChartsOption>(() => {
    const m = modes.data;
    return {
      animation: false,
      grid: { left: 58, right: 16, top: 16, bottom: 42 },
      tooltip: {
        trigger: "item",
        formatter: (p: { data: number[] }) => `Re kz/k₀ = ${fmt(p.data[0], 5)}<br/>Im kz/k₀ = ${fmt(p.data[1], 5)}`,
      },
      xAxis: { type: "value", name: "Re(kz/k₀)", nameLocation: "middle", nameGap: 26, scale: true },
      yAxis: { type: "value", name: "Im(kz/k₀)  (< 0 decays)", nameLocation: "middle", nameGap: 42, scale: true },
      dataZoom: [
        { type: "inside", xAxisIndex: 0, filterMode: "none" },
        { type: "inside", yAxisIndex: 0, filterMode: "none" },
      ],
      series: [{ type: "scatter", symbolSize: 6, data: m ? m.kz_re.map((x, i) => [x, m.kz_im[i]]) : [] }],
    };
  }, [modes.data]);

  if (!run.done) return <RunRequired run={run} what="the fields inside the mask" />;

  const kind = quantityKind(quantity);
  const valueLabel: string = quantity;
  const boundaries = view.boundaries;
  const boundaryColor = kind === "signed" ? "#202020" : "#9fd3ff";

  return (
    <PanelLayout
      toolbar={
        <>
          <ToolbarItem label="Polarization">
            <PolarizationPicker panel="nearfield" pols={run.pols} />
          </ToolbarItem>
          <ToolbarItem label="Quantity">
            <SelectField
              size="sm"
              className="w-32"
              value={quantity}
              onChange={(q) => setView("nearfield", { quantity: q })}
              options={FIELD_QUANTITIES.map((q) => ({ value: q.value, label: q.label }))}
            />
          </ToolbarItem>
          {kind === "signed" && (
            <ToolbarItem label={<span className="inline-block w-[46px] tabular-nums">ωt {phase.toFixed(0)}°</span>}>
              <Button
                size="icon-sm"
                variant="outline"
                onClick={() => setPlaying((p) => !p)}
                title="Animate the time phase"
              >
                <HugeiconsIcon icon={playing ? PauseIcon : PlayIcon} />
              </Button>
              <Slider
                className="data-horizontal:w-28"
                min={0}
                max={360}
                step={1}
                value={[phase]}
                onValueChange={(v) => {
                  setPlaying(false);
                  setPhase((Array.isArray(v) ? v[0] : v) as number);
                }}
              />
            </ToolbarItem>
          )}
          <ToolbarItem label="Colormap">
            <SelectField
              size="sm"
              className="w-36"
              value={view.colormap}
              onChange={(c) => setView("nearfield", { colormap: c })}
              options={[
                { value: "auto" as const, label: "Auto" },
                ...COLORMAPS.map((c) => ({ value: c.value, label: c.label })),
              ]}
            />
          </ToolbarItem>
          {kind === "magnitude" && (
            <ToolbarItem label="Log">
              <Switch
                size="sm"
                checked={view.scale === "log"}
                onCheckedChange={(log) => setView("nearfield", { scale: log ? "log" : "linear" })}
              />
            </ToolbarItem>
          )}
          <ToolbarItem label="Boundaries">
            <Switch size="sm" checked={boundaries} onCheckedChange={(b) => setView("nearfield", { boundaries: b })} />
          </ToolbarItem>
          <SectionControls panel="nearfield" />
          {run.stale && (
            <span className="text-[11px] text-amber-600 dark:text-amber-400">Results are from earlier inputs</span>
          )}
        </>
      }
    >
      <div className="grid grid-cols-[repeat(auto-fit,minmax(420px,1fr))] gap-3">
        <ViewCard
          title="Field cross-section"
          subtitle={
            params
              ? `${params.axis}–z at ${params.axis === "x" ? "y" : "x"} = ${fixed(params.offset_nm, 1)} nm · ${pol}`
              : ""
          }
          className="col-span-full h-[460px]"
          loading={section.isFetching}
          errors={section.error ? errorMessages(section.error) : undefined}
        >
          {section.data && sectionValues && (
            <Heatmap
              values={sectionValues}
              width={section.data.Ex.shape[1]}
              height={section.data.Ex.shape[0]}
              x={section.data.lateral_nm.data}
              y={section.data.z_nm.data}
              yDown
              equalAspect
              colormap={colormap}
              domain={sectionDomain}
              scale={scale}
              boundaries={boundaries ? section.data.material.data : null}
              boundaryColor={boundaryColor}
              valueLabel={valueLabel}
              xLabel={`${params?.axis ?? "x"} (nm)`}
              yLabel="depth z (nm)"
              describe={(_x, y) => describeSlice(sliceAtDepth(slices, y))}
            />
          )}
        </ViewCard>
        <ViewCard
          title="Field top view"
          subtitle={`depth ${fixed(depth, 1)} nm · ${describeSlice(sliceAtDepth(slices, depth)) ?? (depth < 0 ? "above the mask" : "substrate")}`}
          className="h-[440px]"
          loading={plane.isFetching}
          errors={plane.error ? errorMessages(plane.error) : undefined}
          actions={
            <Slider
              className="data-horizontal:w-40"
              min={-30}
              max={Math.ceil(total + 10)}
              step={0.25}
              value={[depth]}
              onValueChange={(v) => setView("nearfield", { depth: (Array.isArray(v) ? v[0] : v) as number })}
              aria-label="Top-view depth"
            />
          }
        >
          {plane.data && planeValues && (
            <Heatmap
              values={planeValues}
              width={plane.data.Ex.shape[1]}
              height={plane.data.Ex.shape[0]}
              x={plane.data.x_nm.data}
              y={plane.data.y_nm.data}
              equalAspect
              colormap={colormap}
              domain={planeDomain}
              scale={scale}
              boundaries={boundaries ? plane.data.material.data : null}
              boundaryColor={boundaryColor}
              valueLabel={valueLabel}
              xLabel="x (nm)"
              yLabel="y (nm)"
            />
          )}
        </ViewCard>
        <ViewCard
          title="Power flow"
          subtitle="drops mark absorption"
          className="h-[440px]"
          loading={flux.isFetching}
          errors={flux.error ? errorMessages(flux.error) : undefined}
        >
          <EChart option={fluxOption} />
        </ViewCard>
        <ViewCard
          title="Power budget"
          subtitle={pol}
          className="h-[380px]"
          loading={absorption.isFetching}
          errors={absorption.error ? errorMessages(absorption.error) : undefined}
        >
          <EChart option={budgetOption} />
        </ViewCard>
        <ViewCard
          title="Layer modes"
          subtitle="propagation constants of the slice's eigenmodes"
          className="h-[380px]"
          loading={modes.isFetching}
          errors={modes.error ? errorMessages(modes.error) : undefined}
          actions={
            <SelectField
              size="sm"
              className="w-48"
              value={modeSlice}
              onChange={(slice) => setView("nearfield", { slice })}
              options={sliceOptions(slices)}
              aria-label="Slice for the mode plot"
            />
          }
        >
          <EChart option={modesOption} />
        </ViewCard>
      </div>
    </PanelLayout>
  );
}
