// Placeholder for result panels before a run has finished (or after it failed / expired).
import { Loading03Icon, PlayIcon } from "@hugeicons/core-free-icons";
import { HugeiconsIcon } from "@hugeicons/react";
import { EmptyState } from "@/components/layout";
import { Progress } from "@/components/ui/progress";
import type { useRunState } from "./common";

export function RunRequired({ run, what }: { run: ReturnType<typeof useRunState>; what: string }) {
  const job = run.job;
  if (job && (job.status === "running" || job.status === "queued"))
    return (
      <EmptyState
        title="Solving…"
        icon={<HugeiconsIcon icon={Loading03Icon} className="size-6 animate-spin text-muted-foreground" />}
      >
        <div className="w-64 space-y-1.5">
          <Progress value={Math.round(job.progress * 100)} />
          <div className="text-[11px] text-muted-foreground">{job.message}</div>
        </div>
      </EmptyState>
    );
  if (job?.status === "failed")
    return (
      <EmptyState title="The run failed">
        <code className="text-[11px]">{job.error}</code>
      </EmptyState>
    );
  return (
    <EmptyState
      title="Nothing solved yet"
      icon={<HugeiconsIcon icon={PlayIcon} className="size-6 text-muted-foreground" />}
    >
      {run.missing
        ? "The previous run is no longer on the server. "
        : job?.status === "cancelled"
          ? "The last run was cancelled. "
          : ""}
      Press <b>Run</b> (Ctrl+Enter) to solve the stack and see {what}.
    </EmptyState>
  );
}
