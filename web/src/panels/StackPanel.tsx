// Simulation setup, in the order a mask simulation is defined: the layer stack, the
// pattern etched into it, the illumination, solver accuracy, and the material library.
// Section headers summarize their settings, so even collapsed the panel shows the whole
// setup; the footer says whether it can run and lists what blocks it. Every edit goes
// through the project store, so it is undoable and the views follow immediately.
import { Alert02Icon, CheckmarkCircle02Icon, Loading03Icon, PlayIcon, StopIcon } from "@hugeicons/core-free-icons";
import { HugeiconsIcon } from "@hugeicons/react";
import { type ReactNode, useMemo } from "react";
import { errorMessages } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { problemSection, type SetupSectionId } from "@/lib/stack";
import { useRunControl, useStack } from "./common";
import { LayersSection } from "./stack/LayersSection";
import { MaterialsSection } from "./stack/MaterialsSection";
import { AccuracySection, IlluminationSection } from "./stack/OpticsSections";
import { PatternSection } from "./stack/PatternSection";
import { revealSection } from "./stack/ui";

export function StackPanel() {
  const { project, errors } = useStack();
  const problems = useMemo(() => {
    const count: Record<SetupSectionId, number> = { stack: 0, pattern: 0, illumination: 0, accuracy: 0, materials: 0 };
    for (const e of errors) count[problemSection(e, project)]++;
    return count;
  }, [errors, project]);
  return (
    <div className="flex h-full min-h-0 flex-col bg-background">
      <div className="min-h-0 flex-1 overflow-y-auto">
        <LayersSection problems={problems.stack} />
        <PatternSection problems={problems.pattern} />
        <IlluminationSection problems={problems.illumination} />
        <AccuracySection problems={problems.accuracy} />
        <MaterialsSection problems={problems.materials} />
      </div>
      <RunFooter />
    </div>
  );
}

function RunFooter() {
  const { project, errors, check, summary, requestError } = useStack();
  const { run, running, canRun, start, stop } = useRunControl();

  let status: ReactNode;
  if (requestError) {
    status = <Status tone="danger">Can't check the setup: {errorMessages(requestError).join("; ")}</Status>;
  } else if (!check) {
    status = <Status icon={Loading03Icon}>Checking the setup…</Status>;
  } else if (errors.length) {
    status = null;
  } else if (running && run.job) {
    status = (
      <div className="flex items-center gap-2">
        <Progress value={Math.round(run.job.progress * 100)} className="w-24 shrink-0" />
        <span className="truncate text-[11px] text-muted-foreground" title={run.job.message}>
          {run.job.message}
        </span>
      </div>
    );
  } else if (run.job?.status === "failed") {
    status = <Status tone="danger">The last run failed{run.job.error ? `: ${run.job.error}` : "."}</Status>;
  } else if (run.done && run.stale) {
    status = <Status tone="warn">The setup changed since the last run. Run again to update the results.</Status>;
  } else if (run.done) {
    status = <Status icon={CheckmarkCircle02Icon}>The results match this setup.</Status>;
  } else {
    status = (
      <Status>
        <span className="font-medium text-foreground">Ready to run.</span>{" "}
        {summary &&
          `${summary.slice_count} slices, ${summary.harmonics} harmonics, ${summary.polarizations.join(" and ")}.`}
      </Status>
    );
  }

  return (
    <footer className="shrink-0 border-t bg-muted/30 px-3 py-2.5">
      {errors.length > 0 && (
        <div className="mb-2">
          <div className="flex items-center gap-1.5 text-xs font-medium text-destructive">
            <HugeiconsIcon icon={Alert02Icon} className="size-3.5" />
            {errors.length === 1 ? "Fix this to run:" : `Fix these ${errors.length} problems to run:`}
          </div>
          <ul className="mt-1 max-h-28 space-y-0.5 overflow-y-auto pl-5">
            {errors.map((e) => (
              <li key={e}>
                <button
                  type="button"
                  className="text-left text-[11px] underline-offset-2 hover:underline"
                  onClick={() => revealSection(problemSection(e, project))}
                  title="Show the setting"
                >
                  {e}
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
      <div className="flex items-center gap-3">
        <div className="min-w-0 flex-1">{status}</div>
        {running ? (
          <Button size="lg" variant="destructive" onClick={stop}>
            <HugeiconsIcon icon={StopIcon} data-icon="inline-start" />
            Stop
          </Button>
        ) : (
          <Button size="lg" onClick={start} disabled={!canRun} title="Solve (Ctrl+Enter)">
            <HugeiconsIcon icon={PlayIcon} data-icon="inline-start" />
            Run
          </Button>
        )}
      </div>
    </footer>
  );
}

function Status({
  tone = "muted",
  icon,
  children,
}: {
  tone?: "muted" | "warn" | "danger";
  icon?: typeof PlayIcon;
  children: ReactNode;
}) {
  const color =
    tone === "danger"
      ? "text-destructive"
      : tone === "warn"
        ? "text-amber-700 dark:text-amber-400"
        : "text-muted-foreground";
  return (
    <p className={`flex items-center gap-1.5 text-[11px] leading-snug ${color}`}>
      {icon && (
        <HugeiconsIcon
          icon={icon}
          className={`size-3.5 shrink-0 ${icon === Loading03Icon ? "animate-spin" : "text-emerald-600 dark:text-emerald-400"}`}
        />
      )}
      <span className="min-w-0">{children}</span>
    </p>
  );
}
