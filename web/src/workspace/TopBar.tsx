// Application bar: project file actions, undo/redo, run control and status, views, theme.
import {
  ComputerIcon,
  FloppyDiskIcon,
  FolderOpenIcon,
  Moon02Icon,
  PlayIcon,
  Redo02Icon,
  StopIcon,
  Sun03Icon,
  Undo02Icon,
} from "@hugeicons/core-free-icons";
import { HugeiconsIcon } from "@hugeicons/react";
import { useTheme } from "next-themes";
import { useEffect, useRef } from "react";
import { toast } from "sonner";
import { errorMessages } from "@/api/client";
import { FINISHED, fetchPreset, normalizeProject, useCancelJob, usePresets, useSubmitRun } from "@/api/hooks";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuShortcut,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Progress } from "@/components/ui/progress";
import { Separator } from "@/components/ui/separator";
import { downloadText } from "@/lib/download";
import { seconds } from "@/lib/format";
import { useRunState, useStack } from "@/panels/common";
import { isDirty, useProjectStore } from "@/state/project";
import { useSession } from "@/state/session";
import { PANELS, useWorkspace } from "./Workspace";

function isEditable(target: EventTarget | null): boolean {
  const el = target as HTMLElement | null;
  return !!el && (el.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(el.tagName));
}

export function TopBar({ connected }: { connected: boolean }) {
  const project = useProjectStore((s) => s.project);
  const dirty = useProjectStore(isDirty);
  const canUndo = useProjectStore((s) => s.past.length > 0);
  const canRedo = useProjectStore((s) => s.future.length > 0);
  const { undo, redo, load, markSaved } = useProjectStore.getState();
  const { errors } = useStack();
  const run = useRunState();
  const crosscheck = useSession((s) => s.crosscheck);
  const setCrosscheck = useSession((s) => s.setCrosscheck);
  const setRun = useSession((s) => s.setRun);
  const submit = useSubmitRun();
  const cancel = useCancelJob();
  const presets = usePresets();
  const workspace = useWorkspace();
  const { theme, setTheme } = useTheme();
  const fileInput = useRef<HTMLInputElement>(null);

  const running = !!run.job && !FINISHED.has(run.job.status);
  const canRun = !!project && errors.length === 0 && !running && !submit.isPending;

  const startRun = () => {
    if (!project || !canRun) return;
    submit.mutate(
      { project, crosscheck },
      {
        onSuccess: (job) => setRun(job.id),
        onError: (error) => toast.error("Couldn't start the run", { description: errorMessages(error).join("; ") }),
      },
    );
  };

  const save = () => {
    if (!project) return;
    const name = `${(project.name || "project").replace(/[^\w.-]+/g, "_")}.masksim.json`;
    downloadText(`${JSON.stringify(project, null, 2)}\n`, name, "application/json");
    markSaved(name);
  };

  const open = async (file: File) => {
    try {
      const document = JSON.parse(await file.text());
      load(await normalizeProject(document), file.name);
      toast.success(`Opened ${file.name}`);
    } catch (error) {
      toast.error(`Couldn't open ${file.name}`, { description: errorMessages(error).join("; ") });
    }
  };

  const loadPreset = async (id: string, name: string) => {
    if (dirty && !window.confirm("Replace the current project? Changes that are not saved to a file will be lost."))
      return;
    try {
      load(await fetchPreset(id));
      toast.success(`Loaded preset “${name}”`);
    } catch (error) {
      toast.error("Couldn't load the preset", { description: errorMessages(error).join("; ") });
    }
  };

  // Keyboard shortcuts. Text fields keep their own undo; everything else uses the project's.
  const actions = useRef({ startRun, save, undo, redo });
  actions.current = { startRun, save, undo, redo };
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!(e.ctrlKey || e.metaKey)) return;
      const key = e.key.toLowerCase();
      if (key === "enter") {
        e.preventDefault();
        actions.current.startRun();
      } else if (key === "s") {
        e.preventDefault();
        actions.current.save();
      } else if (key === "o") {
        e.preventDefault();
        fileInput.current?.click();
      } else if (!isEditable(e.target) && key === "z") {
        e.preventDefault();
        if (e.shiftKey) actions.current.redo();
        else actions.current.undo();
      } else if (!isEditable(e.target) && key === "y") {
        e.preventDefault();
        actions.current.redo();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const status = (() => {
    if (running && run.job)
      return (
        <div className="flex w-56 items-center gap-2">
          <Progress value={Math.round(run.job.progress * 100)} className="flex-1" />
          <span className="max-w-40 truncate text-[11px] text-muted-foreground" title={run.job.message}>
            {run.job.message}
          </span>
        </div>
      );
    if (run.job?.status === "failed")
      return (
        <Badge variant="destructive" title={run.job.error ?? ""}>
          Run failed
        </Badge>
      );
    if (run.done && run.summary)
      return (
        <div className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
          <span>
            Solved in {seconds(run.summary.elapsed)} · {run.pols.join("+")}
          </span>
          {run.stale && (
            <Badge variant="outline" className="border-amber-500/60 text-amber-700 dark:text-amber-400">
              inputs changed
            </Badge>
          )}
          {run.job?.check && (
            <span title="Largest per-order difference against the reference RCWASolver">
              · check ΔR {Number((run.job.check as { dR: number }).dR).toExponential(1)}
            </span>
          )}
        </div>
      );
    if (errors.length) return <span className="text-[11px] text-destructive">Fix the stack to run</span>;
    return null;
  })();

  return (
    <header className="flex h-11 shrink-0 items-center gap-2 border-b bg-background px-3">
      <div className="flex items-center gap-2">
        <div className="size-5 rounded-[5px] bg-gradient-to-br from-indigo-500 via-sky-500 to-teal-400" aria-hidden />
        <span className="text-sm font-semibold tracking-tight">Mask Simulator</span>
      </div>
      <Separator orientation="vertical" className="mx-1 h-5" />

      <DropdownMenu>
        <DropdownMenuTrigger render={<Button variant="ghost" size="sm" />}>File</DropdownMenuTrigger>
        <DropdownMenuContent align="start" className="w-64">
          <DropdownMenuGroup>
            <DropdownMenuLabel>New from preset</DropdownMenuLabel>
            {(presets.data ?? []).map((p) => (
              <DropdownMenuItem key={p.id} onClick={() => loadPreset(p.id, p.name)}>
                {p.name}
              </DropdownMenuItem>
            ))}
          </DropdownMenuGroup>
          <DropdownMenuSeparator />
          <DropdownMenuItem onClick={() => fileInput.current?.click()}>
            <HugeiconsIcon icon={FolderOpenIcon} />
            Open…
            <DropdownMenuShortcut>Ctrl+O</DropdownMenuShortcut>
          </DropdownMenuItem>
          <DropdownMenuItem onClick={save}>
            <HugeiconsIcon icon={FloppyDiskIcon} />
            Save
            <DropdownMenuShortcut>Ctrl+S</DropdownMenuShortcut>
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
      <DropdownMenu>
        <DropdownMenuTrigger render={<Button variant="ghost" size="sm" />}>View</DropdownMenuTrigger>
        <DropdownMenuContent align="start" className="w-52">
          {PANELS.map((p) => (
            <DropdownMenuItem key={p.id} onClick={() => workspace.openPanel(p.id)}>
              {p.title}
            </DropdownMenuItem>
          ))}
          <DropdownMenuSeparator />
          <DropdownMenuItem onClick={workspace.resetLayout}>Reset layout</DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
      <input
        ref={fileInput}
        type="file"
        accept=".json,application/json"
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) void open(file);
          e.target.value = "";
        }}
      />

      <Button size="icon-sm" variant="ghost" onClick={undo} disabled={!canUndo} title="Undo (Ctrl+Z)" aria-label="Undo">
        <HugeiconsIcon icon={Undo02Icon} />
      </Button>
      <Button size="icon-sm" variant="ghost" onClick={redo} disabled={!canRedo} title="Redo (Ctrl+Y)" aria-label="Redo">
        <HugeiconsIcon icon={Redo02Icon} />
      </Button>

      <div className="min-w-0 truncate text-xs text-muted-foreground" title={project?.name}>
        {project?.name}
        {dirty && <span title="Unsaved changes"> •</span>}
      </div>

      <div className="ml-auto flex items-center gap-2">
        {status}
        {running && run.job ? (
          <Button size="sm" variant="destructive" onClick={() => run.job && cancel.mutate(run.job)}>
            <HugeiconsIcon icon={StopIcon} data-icon="inline-start" />
            Stop
          </Button>
        ) : (
          <div className="flex items-center">
            <Button
              size="sm"
              onClick={startRun}
              disabled={!canRun}
              className="rounded-r-none"
              title="Solve (Ctrl+Enter)"
            >
              <HugeiconsIcon icon={PlayIcon} data-icon="inline-start" />
              Run
            </Button>
            <DropdownMenu>
              <DropdownMenuTrigger
                render={
                  <Button
                    size="sm"
                    className="rounded-l-none border-l border-primary-foreground/20 px-1.5"
                    aria-label="Run options"
                  />
                }
              >
                ▾
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-72">
                <DropdownMenuCheckboxItem checked={crosscheck} onCheckedChange={(v) => setCrosscheck(!!v)}>
                  Cross-check with the reference RCWASolver
                </DropdownMenuCheckboxItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        )}
        <span
          className={`size-2 rounded-full ${connected ? "bg-emerald-500" : "bg-amber-500"}`}
          title={connected ? "Connected to the solver server" : "Reconnecting to the solver server…"}
        />
        <DropdownMenu>
          <DropdownMenuTrigger render={<Button size="icon-sm" variant="ghost" aria-label="Theme" />}>
            <HugeiconsIcon icon={theme === "dark" ? Moon02Icon : theme === "light" ? Sun03Icon : ComputerIcon} />
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem onClick={() => setTheme("light")}>Light</DropdownMenuItem>
            <DropdownMenuItem onClick={() => setTheme("dark")}>Dark</DropdownMenuItem>
            <DropdownMenuItem onClick={() => setTheme("system")}>System</DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </header>
  );
}
