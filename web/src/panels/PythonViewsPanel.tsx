// Views defined in Python (maskserver/python_views.py): each returns an ECharts option,
// rendered here with the app's chart theme. New plots need no TypeScript.
import { errorMessages } from "@/api/client";
import { usePythonView, usePythonViews } from "@/api/hooks";
import { SelectField, ToolbarItem } from "@/components/controls";
import { EmptyState, PanelLayout, ViewCard } from "@/components/layout";
import { fmt } from "@/lib/format";
import { useProject } from "@/state/project";
import { useView } from "@/state/view";
import { EChart } from "@/viz/EChart";
import { PolarizationPicker, usePol, useRunState } from "./common";
import { RunRequired } from "./RunRequired";

type Option = Record<string, unknown>;

/** Give numeric axes the app's number formatting unless the view set its own. */
function withAxisDefaults(option: Option): Option {
  const fix = (axis: unknown, defaultType: string) => {
    if (!axis || typeof axis !== "object") return axis;
    const a = axis as Option;
    const type = (a.type as string | undefined) ?? defaultType;
    if (type !== "value" && type !== "log") return a;
    const label = (a.axisLabel ?? {}) as Option;
    return { ...a, axisLabel: { formatter: (v: number) => fmt(v, 4), hideOverlap: true, ...label } };
  };
  const all = (axes: unknown, defaultType: string) =>
    Array.isArray(axes) ? axes.map((a) => fix(a, defaultType)) : fix(axes, defaultType);
  return { ...option, xAxis: all(option.xAxis, "category"), yAxis: all(option.yAxis, "value") };
}

export function PythonViewsPanel() {
  const project = useProject();
  const views = usePythonViews().data ?? [];
  const chosen = useView((s) => s.python.view);
  const setView = useView((s) => s.setView);
  const run = useRunState();
  const pol = usePol("diffraction", run.pols);
  const view = views.find((v) => v.id === chosen) ?? views[0];
  const needsRun = view?.needs === "run";
  const result = usePythonView(
    view?.id ?? null,
    project,
    run.done ? run.runId : null,
    run.done ? pol : null,
    !needsRun || run.done,
  );

  return (
    <PanelLayout
      toolbar={
        <>
          <ToolbarItem label="View">
            <SelectField
              size="sm"
              className="w-80"
              value={view?.id ?? ""}
              onChange={(id) => setView("python", { view: id })}
              options={views.map((v) => ({ value: v.id, label: v.title }))}
            />
          </ToolbarItem>
          {needsRun && run.done && (
            <ToolbarItem label="Polarization">
              <PolarizationPicker panel="diffraction" pols={run.pols} />
            </ToolbarItem>
          )}
          <span className="text-[11px] text-muted-foreground">
            Add views in <code>server/maskserver/python_views.py</code>
          </span>
        </>
      }
    >
      {!view ? (
        <EmptyState title="No Python views registered" />
      ) : needsRun && !run.done ? (
        <RunRequired run={run} what="this view" />
      ) : (
        <ViewCard
          title={view.title}
          subtitle={view.description}
          className="h-[520px]"
          loading={result.isFetching}
          errors={result.error ? errorMessages(result.error) : undefined}
        >
          {result.data && <EChart option={withAxisDefaults(result.data.option)} />}
        </ViewCard>
      )}
    </PanelLayout>
  );
}
