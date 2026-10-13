// Permittivity: the geometry as drawn versus the truncated Fourier series the RCWA solve
// actually represents, and each slice's convolution matrix.
import { useMemo } from "react";
import { errorMessages } from "@/api/client";
import { useConvolution, useDielectricPlane, useDielectricSection } from "@/api/hooks";
import { Segmented, SelectField, ToolbarItem } from "@/components/controls";
import { EmptyState, PanelLayout, ViewCard } from "@/components/layout";
import { Switch } from "@/components/ui/switch";
import { extent } from "@/lib/colorize";
import { COLORMAPS } from "@/lib/colormaps";
import { complexLogAbs, complexPart } from "@/lib/field";
import { fixed, fmt } from "@/lib/format";
import { useView } from "@/state/view";
import { Heatmap } from "@/viz/Heatmap";
import { SectionControls, useSectionParams, useStack } from "./common";
import { chooseSlice, describeSlice, sliceAtDepth, sliceOptions } from "./GeometryPanel";

export function DielectricPanel() {
  const { project, slices, summary, errors } = useStack();
  const view = useView((s) => s.dielectric);
  const setView = useView((s) => s.setView);
  const ready = !!summary && errors.length === 0;

  const params = useSectionParams("dielectric", { lateral: 360, z: 320 });
  const sectionParams = useMemo(() => (params ? { ...params, fourier: view.fourier } : null), [params, view.fourier]);
  const section = useDielectricSection(project, sectionParams ?? ({} as never), ready && !!sectionParams);
  const sliceIndex = chooseSlice(view.slice, slices);
  const plane = useDielectricPlane(project, sliceIndex, view.section.periods, view.fourier, 200, ready);
  const conv = useConvolution(project, sliceIndex, ready);

  const sectionValues = useMemo(
    () => (section.data ? complexPart(section.data.eps, view.part) : null),
    [section.data, view.part],
  );
  const planeValues = useMemo(
    () => (plane.data ? complexPart(plane.data.eps, view.part) : null),
    [plane.data, view.part],
  );
  const convValues = useMemo(() => (conv.data ? complexLogAbs(conv.data.matrix) : null), [conv.data]);
  const convDomain = useMemo(() => {
    const e = convValues ? extent(convValues) : { min: -6, max: 0 };
    return { min: Math.max(e.min, e.max - 8), max: e.max };
  }, [convValues]);

  if (!summary)
    return (
      <EmptyState title="No valid stack yet">
        Fix the issues listed in the stack editor to see the permittivity.
      </EmptyState>
    );

  const part = view.part === "re" ? "Re ε" : "Im ε";
  const kind = view.fourier ? "truncated Fourier series" : "exact geometry";
  const nh = conv.data ? conv.data.mx.data.length : 0;
  const label = (i: number) => (conv.data ? `(${conv.data.mx.data[i]},${conv.data.my.data[i]})` : "");

  return (
    <PanelLayout
      toolbar={
        <>
          <ToolbarItem label="Part">
            <Segmented
              value={view.part}
              onChange={(p) => setView("dielectric", { part: p })}
              options={[
                { value: "re", label: "Re ε" },
                { value: "im", label: "Im ε", hint: "Loss gives Im ε < 0 (n − ik convention)" },
              ]}
            />
          </ToolbarItem>
          <ToolbarItem label="As RCWA sees it">
            <Switch
              checked={view.fourier}
              onCheckedChange={(fourier) => setView("dielectric", { fourier })}
              size="sm"
            />
          </ToolbarItem>
          <ToolbarItem label="Colormap">
            <SelectField
              size="sm"
              className="w-36"
              value={view.colormap}
              onChange={(colormap) => setView("dielectric", { colormap })}
              options={COLORMAPS.map((c) => ({ value: c.value, label: c.label }))}
            />
          </ToolbarItem>
          <SectionControls panel="dielectric" />
        </>
      }
    >
      <div className="grid grid-cols-[repeat(auto-fit,minmax(420px,1fr))] gap-3">
        <ViewCard
          title={`${part} cross-section`}
          subtitle={kind}
          className="col-span-full h-[420px]"
          loading={section.isFetching}
          errors={section.error ? errorMessages(section.error) : undefined}
        >
          {section.data && sectionValues && (
            <Heatmap
              values={sectionValues}
              width={section.data.eps.shape[1]}
              height={section.data.eps.shape[0]}
              x={section.data.lateral_nm.data}
              y={section.data.z_nm.data}
              yDown
              equalAspect
              colormap={view.colormap}
              domain={extent(sectionValues)}
              valueLabel={part}
              formatValue={(v) => fmt(v, 6)}
              xLabel={`${params?.axis ?? "x"} (nm)`}
              yLabel="depth z (nm)"
              describe={(_x, y) => describeSlice(sliceAtDepth(slices, y))}
            />
          )}
        </ViewCard>
        <ViewCard
          title={`${part} in a slice`}
          subtitle={kind}
          className="h-[420px]"
          loading={plane.isFetching}
          errors={plane.error ? errorMessages(plane.error) : undefined}
          actions={
            <SelectField
              size="sm"
              className="w-56"
              value={sliceIndex}
              onChange={(slice) => setView("dielectric", { slice })}
              options={sliceOptions(slices)}
              aria-label="Slice"
            />
          }
        >
          {plane.data && planeValues && (
            <Heatmap
              values={planeValues}
              width={plane.data.eps.shape[1]}
              height={plane.data.eps.shape[0]}
              x={plane.data.x_nm.data}
              y={plane.data.y_nm.data}
              equalAspect
              colormap={view.colormap}
              domain={extent(planeValues)}
              valueLabel={part}
              formatValue={(v) => fmt(v, 6)}
              xLabel="x (nm)"
              yLabel="y (nm)"
            />
          )}
        </ViewCard>
        <ViewCard
          title="Convolution matrix [ε]"
          subtitle={nh ? `${nh} × ${nh}, log₁₀|ε_pq| · ${slices[sliceIndex]?.label ?? ""}` : ""}
          className="h-[420px]"
          loading={conv.isFetching}
          errors={conv.error ? errorMessages(conv.error) : undefined}
        >
          {conv.data && convValues && (
            <Heatmap
              values={convValues}
              width={nh}
              height={nh}
              x={Array.from({ length: nh }, (_, i) => i)}
              y={Array.from({ length: nh }, (_, i) => i)}
              yDown
              equalAspect
              colormap="viridis"
              domain={convDomain}
              valueLabel="log₁₀|ε_pq|"
              xLabel="column q"
              yLabel="row p"
              formatValue={(v) => fixed(v, 2)}
              describe={(_x, _y, index) => `p = ${label(Math.floor(index / nh))}, q = ${label(index % nh)}`}
            />
          )}
        </ViewCard>
      </div>
    </PanelLayout>
  );
}
