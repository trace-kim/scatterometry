// Stack geometry: cross-section and top-view material maps plus the 3D stack. These need
// no solve, so they follow every edit in the stack editor.
import { lazy, Suspense, useMemo } from "react";
import { errorMessages } from "@/api/client";
import { useBoxes, useGeometryPlane, useGeometrySection } from "@/api/hooks";
import type { SliceInfo } from "@/api/model";
import { SelectField, ToolbarItem } from "@/components/controls";
import { EmptyState, PanelLayout, ViewCard } from "@/components/layout";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
import { fixed } from "@/lib/format";
import { useView } from "@/state/view";
import { Heatmap } from "@/viz/Heatmap";
import { SectionControls, useMaterialColors, useSectionParams, useStack } from "./common";

// three.js is the largest dependency; load it only when the 3D view is shown.
const Stack3D = lazy(() => import("@/viz/Stack3D").then((m) => ({ default: m.Stack3D })));

export function sliceAtDepth(slices: SliceInfo[], depth: number): SliceInfo | undefined {
  return slices.find((s) => depth >= s.z_top_nm && depth < s.z_top_nm + s.thickness_nm);
}

export function describeSlice(s: SliceInfo | undefined): string | null {
  if (!s) return null;
  const cd = s.patterned && s.cd_x_nm !== null ? `, CD ${fixed(s.cd_x_nm, 2)} nm` : "";
  return `${s.label}${cd}`;
}

/** Valid slice index for slice pickers: the stored choice, else the first patterned slice. */
export function chooseSlice(stored: number | null, slices: SliceInfo[]): number {
  if (stored !== null && stored < slices.length) return stored;
  const patterned = slices.findIndex((s) => s.patterned);
  return patterned >= 0 ? patterned : 0;
}

export function sliceOptions(slices: SliceInfo[], patternedOnly = false) {
  return slices
    .filter((s) => !patternedOnly || s.patterned)
    .slice(0, 400)
    .map((s) => ({ value: s.index, label: `${s.label} · ${fixed(s.z_top_nm, 1)} nm` }));
}

export function GeometryPanel() {
  const { project, slices, summary, errors } = useStack();
  const view = useView((s) => s.geometry);
  const setView = useView((s) => s.setView);
  const colors = useMaterialColors();
  const names = useMemo(() => project.materials.map((m) => m.name), [project.materials]);
  const ready = !!summary && errors.length === 0;

  const params = useSectionParams("geometry", { lateral: 480, z: 420 });
  const section = useGeometrySection(project, params ?? ({} as never), ready && !!params);
  const sliceIndex = chooseSlice(view.slice, slices);
  const plane = useGeometryPlane(project, sliceIndex, view.section.periods, 240, ready);
  const boxes = useBoxes(project, view.periods3d, null, 160, ready && view.show3d);

  if (!summary)
    return (
      <EmptyState title="No valid stack yet">Fix the issues listed in the stack editor to see the geometry.</EmptyState>
    );

  const sectionData = section.data;
  const planeData = plane.data;
  const topSlice = slices[sliceIndex];

  return (
    <PanelLayout
      toolbar={
        <>
          <SectionControls panel="geometry" />
          <ToolbarItem label="3D">
            <Switch checked={view.show3d} onCheckedChange={(show3d) => setView("geometry", { show3d })} size="sm" />
          </ToolbarItem>
        </>
      }
    >
      <div className="grid grid-cols-[repeat(auto-fit,minmax(420px,1fr))] gap-3">
        <ViewCard
          title="Cross-section"
          subtitle={
            params ? `${params.axis}–z at ${params.axis === "x" ? "y" : "x"} = ${fixed(params.offset_nm, 1)} nm` : ""
          }
          className="h-[440px]"
          loading={section.isFetching}
          errors={section.error ? errorMessages(section.error) : undefined}
        >
          {sectionData && (
            <Heatmap
              categories={{ indices: sectionData.material.data, colors, names }}
              width={sectionData.material.shape[1]}
              height={sectionData.material.shape[0]}
              x={sectionData.lateral_nm.data}
              y={sectionData.z_nm.data}
              yDown
              equalAspect
              xLabel={`${params?.axis ?? "x"} (nm)`}
              yLabel="depth z (nm)"
              describe={(_x, y) => describeSlice(sliceAtDepth(slices, y))}
            />
          )}
        </ViewCard>
        <ViewCard
          title="Top view"
          subtitle={
            topSlice
              ? `${topSlice.label}, depth ${fixed(topSlice.z_top_nm, 1)}–${fixed(topSlice.z_top_nm + topSlice.thickness_nm, 1)} nm`
              : ""
          }
          className="h-[440px]"
          loading={plane.isFetching}
          errors={plane.error ? errorMessages(plane.error) : undefined}
          actions={
            <SelectField
              size="sm"
              className="w-56"
              value={sliceIndex}
              onChange={(slice) => setView("geometry", { slice })}
              options={sliceOptions(slices)}
              aria-label="Slice for the top view"
            />
          }
        >
          {planeData && (
            <Heatmap
              categories={{ indices: planeData.material.data, colors, names }}
              width={planeData.material.shape[1]}
              height={planeData.material.shape[0]}
              x={planeData.x_nm.data}
              y={planeData.y_nm.data}
              equalAspect
              xLabel="x (nm)"
              yLabel="y (nm)"
            />
          )}
        </ViewCard>
        {view.show3d && (
          <ViewCard
            title="3D stack"
            subtitle="drag to orbit · scroll to zoom · right-drag to pan"
            className="col-span-full h-[520px]"
            loading={boxes.isFetching}
            errors={boxes.error ? errorMessages(boxes.error) : undefined}
            actions={
              <>
                <ToolbarItem label="Cut" className="mr-2">
                  <Slider
                    className="data-horizontal:w-28"
                    min={0.02}
                    max={1}
                    step={0.01}
                    value={[view.cut]}
                    onValueChange={(v) => setView("geometry", { cut: (Array.isArray(v) ? v[0] : v) as number })}
                  />
                </ToolbarItem>
                <ToolbarItem label="Periods">
                  <SelectField
                    size="sm"
                    className="w-14"
                    value={view.periods3d}
                    onChange={(periods3d) => setView("geometry", { periods3d })}
                    options={[1, 2, 3, 4].map((p) => ({ value: p, label: String(p) }))}
                  />
                </ToolbarItem>
              </>
            }
          >
            <Suspense fallback={null}>
              {boxes.data && <Stack3D data={boxes.data} colors={colors} cut={view.cut} />}
            </Suspense>
          </ViewCard>
        )}
      </div>
    </PanelLayout>
  );
}
