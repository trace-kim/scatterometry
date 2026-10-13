// Pieces shared by the view panels: stack info, section-plane controls, run status.
import { useEffect, useMemo } from "react";
import { ApiError } from "@/api/client";
import { type SectionParams, useCheck, useJob } from "@/api/hooks";
import type { CheckResult, JobInfo, Polarization, RunSummary, SliceInfo } from "@/api/model";
import { Segmented, SelectField, ToolbarItem } from "@/components/controls";
import { NumberField } from "@/components/number-field";
import { Button } from "@/components/ui/button";
import { Slider } from "@/components/ui/slider";
import { fixed } from "@/lib/format";
import { materialColors } from "@/lib/palette";
import { useProject } from "@/state/project";
import { useSession } from "@/state/session";
import { useView } from "@/state/view";
import { useDark } from "@/viz/theme";

export type SectionPanel = "geometry" | "dielectric" | "nearfield";

/** Validation, summary, and slices of the current project (one shared query). */
export function useStack() {
  const project = useProject();
  const check = useCheck(project);
  const data: CheckResult | undefined = check.data;
  return {
    project,
    check: data,
    summary: data?.summary ?? null,
    slices: data?.slices ?? [],
    errors: data?.errors ?? [],
    loading: check.isFetching,
    requestError: check.error,
  };
}

export function useMaterialColors(): string[] {
  const project = useProject();
  const dark = useDark();
  return useMemo(() => materialColors(project.materials, dark), [project.materials, dark]);
}

/** Bottom of the deepest patterned slice plus a margin: the default lower edge of section views. */
export function defaultDepth(slices: SliceInfo[]): number {
  const patterned = slices.filter((s) => s.patterned);
  if (!patterned.length) return 60;
  const last = patterned[patterned.length - 1];
  return Math.round(last.z_top_nm + last.thickness_nm + 25);
}

export function useSectionParams(panel: SectionPanel, n: { lateral: number; z: number }, slices?: SliceInfo[]) {
  const view = useView((s) => s[panel].section);
  const stack = useStack();
  const usedSlices = slices ?? stack.slices;
  const summary = stack.summary;
  return useMemo<SectionParams | null>(() => {
    if (!summary || !usedSlices.length) return null;
    const [Lx, Ly] = summary.unit_cell_nm;
    const across = view.axis === "x" ? Ly : Lx;
    return {
      axis: view.axis,
      offset_nm: Number((view.offset * across).toFixed(3)),
      periods: view.periods,
      z_min_nm: view.zMin ?? -20,
      z_max_nm: view.zMax ?? defaultDepth(usedSlices),
      n_lateral: n.lateral,
      n_z: n.z,
    };
  }, [summary, usedSlices, view, n.lateral, n.z]);
}

export function SectionControls({ panel }: { panel: SectionPanel }) {
  const view = useView((s) => s[panel].section);
  const setSection = useView((s) => s.setSection);
  const { summary, slices } = useStack();
  const [Lx, Ly] = summary?.unit_cell_nm ?? [100, 100];
  const across = view.axis === "x" ? Ly : Lx;
  const total = summary?.total_thickness_nm ?? 100;
  const zMax = view.zMax ?? defaultDepth(slices);
  return (
    <>
      <ToolbarItem label="Plane">
        <Segmented
          value={view.axis}
          onChange={(axis) => setSection(panel, { axis })}
          options={[
            { value: "x", label: "x–z" },
            { value: "y", label: "y–z" },
          ]}
        />
      </ToolbarItem>
      <ToolbarItem label={`at ${view.axis === "x" ? "y" : "x"} = ${fixed(view.offset * across, 1)} nm`}>
        <Slider
          className="data-horizontal:w-28"
          min={0}
          max={1}
          step={0.005}
          value={[view.offset]}
          onValueChange={(v) => setSection(panel, { offset: (Array.isArray(v) ? v[0] : v) as number })}
          disabled={summary?.periodic_axes === "none"}
        />
      </ToolbarItem>
      <ToolbarItem label="Periods">
        <SelectField
          size="sm"
          className="w-14"
          value={view.periods}
          onChange={(periods) => setSection(panel, { periods })}
          options={[1, 2, 3, 4].map((p) => ({ value: p, label: String(p) }))}
        />
      </ToolbarItem>
      <ToolbarItem label="Depth">
        <NumberField
          className="w-24"
          value={view.zMin ?? -20}
          onChange={(zMin) => setSection(panel, { zMin })}
          step={5}
          unit="nm"
          aria-label="Section top depth"
        />
        <span className="text-[11px] text-muted-foreground">to</span>
        <NumberField
          className="w-24"
          value={zMax}
          onChange={(value) => setSection(panel, { zMax: value })}
          step={5}
          max={total + 200}
          unit="nm"
          aria-label="Section bottom depth"
        />
        <Button
          size="xs"
          variant="ghost"
          onClick={() => setSection(panel, { zMin: null, zMax: null })}
          title="Reset the depth range"
        >
          Auto
        </Button>
        <Button size="xs" variant="ghost" onClick={() => setSection(panel, { zMin: -20, zMax: Math.ceil(total + 20) })}>
          All
        </Button>
      </ToolbarItem>
    </>
  );
}

/** The run shown in result panels, its status, and whether it still matches the inputs. */
export function useRunState() {
  const runId = useSession((s) => s.runId);
  const setRun = useSession((s) => s.setRun);
  const job = useJob(runId);
  // Results live in the server's memory; forget runs it no longer has (e.g. after a restart).
  useEffect(() => {
    if (job.error instanceof ApiError && job.error.status === 404) setRun(null);
  }, [job.error, setRun]);
  const { check } = useStack();
  const info: JobInfo | undefined = job.data;
  const done = info?.status === "done";
  const summary = (done ? info?.summary : null) as RunSummary | null;
  const pols = (summary ? Object.keys(summary.power) : []) as Polarization[];
  return {
    runId: job.error ? null : runId,
    job: info,
    done,
    summary,
    pols,
    stale: !!(done && check && info && info.project_digest !== check.digest),
    missing: !!job.error,
  };
}

export function usePol(panel: "diffraction" | "nearfield", pols: Polarization[]): Polarization {
  const chosen = useView((s) => s[panel].pol);
  return chosen && pols.includes(chosen) ? chosen : (pols[0] ?? "TE");
}

export function PolarizationPicker({ panel, pols }: { panel: "diffraction" | "nearfield"; pols: Polarization[] }) {
  const pol = usePol(panel, pols);
  const setView = useView((s) => s.setView);
  if (pols.length < 2) return <span className="text-[11px] text-muted-foreground">{pol}</span>;
  return (
    <Segmented
      value={pol}
      onChange={(value) => setView(panel, { pol: value })}
      options={pols.map((p) => ({ value: p, label: p }))}
    />
  );
}
