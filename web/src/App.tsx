import { useEffect, useState } from "react";
import { errorMessages } from "@/api/client";
import { useServerEvents } from "@/api/events";
import { fetchPreset, normalizeProject } from "@/api/hooks";
import { EmptyState } from "@/components/layout";
import { Button } from "@/components/ui/button";
import { restoreAutosave, useProjectStore } from "@/state/project";
import { TopBar } from "@/workspace/TopBar";
import { Workspace, WorkspaceProvider } from "@/workspace/Workspace";

const DEFAULT_PRESET = "euv-lines";

export function App() {
  const project = useProjectStore((s) => s.project);
  const connected = useServerEvents();
  const [startupError, setStartupError] = useState<string[] | null>(null);
  const [attempt, setAttempt] = useState(0);

  // Start from the browser's autosave (through the server so it is validated and upgraded),
  // falling back to the default preset. `attempt` re-runs this after a failed start.
  // biome-ignore lint/correctness/useExhaustiveDependencies: attempt is the retry trigger
  useEffect(() => {
    if (useProjectStore.getState().project) return;
    const load = useProjectStore.getState().load;
    const saved = restoreAutosave();
    (saved ? normalizeProject(saved).catch(() => fetchPreset(DEFAULT_PRESET)) : fetchPreset(DEFAULT_PRESET))
      .then((p) => load(p))
      .catch((error) => setStartupError(errorMessages(error)));
  }, [attempt]);

  if (!project)
    return (
      <div className="h-dvh">
        {startupError ? (
          <EmptyState title="Can't reach the solver server">
            <p className="mb-3">
              Start it with <code>python -m maskserver</code> (or <code>pnpm dev</code> for development), then retry.
            </p>
            <p className="mb-3 text-[11px]">{startupError.join("; ")}</p>
            <Button
              size="sm"
              onClick={() => {
                setStartupError(null);
                setAttempt((a) => a + 1);
              }}
            >
              Retry
            </Button>
          </EmptyState>
        ) : (
          <EmptyState title="Loading…" />
        )}
      </div>
    );

  return (
    <WorkspaceProvider>
      {(onReady) => (
        <div className="flex h-dvh flex-col">
          <TopBar connected={connected} />
          <main className="min-h-0 flex-1">
            <Workspace onReady={onReady} />
          </main>
        </div>
      )}
    </WorkspaceProvider>
  );
}
