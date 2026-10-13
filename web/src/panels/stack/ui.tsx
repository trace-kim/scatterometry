// Building blocks of the setup panel: collapsible sections whose headers summarize their
// settings, an input that commits on blur, material swatches, and pattern pictograms.
import { ArrowRight01Icon } from "@hugeicons/core-free-icons";
import { HugeiconsIcon } from "@hugeicons/react";
import { type ComponentProps, type ReactNode, useRef, useState } from "react";
import type { PatternKind } from "@/api/model";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import type { SetupSectionId } from "@/lib/stack";
import { cn } from "@/lib/utils";
import { SETUP_OPEN, useView } from "@/state/view";

const anchor = (id: SetupSectionId) => `setup-${id}`;

function setOpen(id: SetupSectionId, open: boolean) {
  const view = useView.getState();
  view.setView("setup", { open: { ...view.setup.open, [id]: open } });
}

/** Opens a section and scrolls it into view (e.g. from the problem list). */
export function revealSection(id: SetupSectionId) {
  setOpen(id, true);
  requestAnimationFrame(() => document.getElementById(anchor(id))?.scrollIntoView({ block: "start" }));
}

export function SetupSection({
  id,
  title,
  summary,
  problems = 0,
  warning,
  actions,
  children,
}: {
  id: SetupSectionId;
  title: string;
  /** One line describing the current settings, shown even when collapsed. */
  summary?: ReactNode;
  /** Validation problems that block a run. */
  problems?: number;
  /** A short caution that does not block a run (e.g. "orders cut off"). */
  warning?: string | null;
  /** Header buttons, shown while the section is open. */
  actions?: ReactNode;
  children: ReactNode;
}) {
  const open = useView((s) => s.setup.open[id] ?? SETUP_OPEN[id]);
  return (
    <Collapsible
      open={open}
      onOpenChange={(next) => setOpen(id, next)}
      render={<section id={anchor(id)} aria-label={title} className="border-b" />}
    >
      {/* Sticky within its section, so the open section stays labelled while scrolling. */}
      <div
        className={cn("sticky top-0 z-10 flex h-10 items-center gap-1 bg-background pr-2 pl-1", open && "shadow-xs")}
      >
        <h2 className="min-w-0 flex-1">
          <CollapsibleTrigger className="group/trigger flex h-8 w-full min-w-0 items-center gap-1.5 rounded-md px-1.5 text-left outline-none hover:bg-muted/60 focus-visible:ring-2 focus-visible:ring-ring/30">
            <HugeiconsIcon
              icon={ArrowRight01Icon}
              className="size-3.5 shrink-0 text-muted-foreground transition-transform group-data-[panel-open]/trigger:rotate-90 motion-reduce:transition-none"
            />
            <span className="shrink-0 text-[13px] font-semibold">{title}</span>
            {problems > 0 ? (
              <span className="flex shrink-0 items-center gap-1 text-[11px] font-medium text-destructive">
                <span className="size-1.5 rounded-full bg-destructive" />
                {problems === 1 ? "1 problem" : `${problems} problems`}
              </span>
            ) : (
              warning && (
                <span className="flex shrink-0 items-center gap-1 text-[11px] font-medium text-amber-700 dark:text-amber-400">
                  <span className="size-1.5 rounded-full bg-amber-500" />
                  {warning}
                </span>
              )
            )}
            <span className="ml-auto min-w-0 truncate pl-3 text-xs font-normal text-muted-foreground tabular-nums">
              {summary}
            </span>
          </CollapsibleTrigger>
        </h2>
        {open && actions && <div className="flex shrink-0 items-center gap-0.5">{actions}</div>}
      </div>
      <CollapsibleContent className="space-y-3 px-3 pt-1 pb-4">{children}</CollapsibleContent>
    </Collapsible>
  );
}

/** Text input that applies its value on blur or Enter (Escape reverts). */
export function CommitInput({
  value,
  onCommit,
  className,
  ...props
}: { value: string; onCommit: (value: string) => void } & Omit<ComponentProps<"input">, "value" | "onChange">) {
  const [draft, setDraft] = useState<string | null>(null);
  const cancelled = useRef(false);
  return (
    <input
      {...props}
      value={draft ?? value}
      spellCheck={false}
      onChange={(e) => setDraft(e.target.value)}
      onBlur={() => {
        if (!cancelled.current && draft !== null && draft !== value) onCommit(draft);
        cancelled.current = false;
        setDraft(null);
      }}
      onKeyDown={(e) => {
        if (e.key === "Enter") e.currentTarget.blur();
        if (e.key === "Escape") {
          cancelled.current = true;
          e.currentTarget.blur();
        }
      }}
      className={cn(
        "h-7 w-full min-w-0 truncate rounded-md border border-transparent bg-transparent px-1.5 text-xs outline-none hover:border-input focus:border-ring focus:bg-background focus:ring-2 focus:ring-ring/30",
        className,
      )}
    />
  );
}

/** Material color chip; hatched for semi-infinite media. */
export function Swatch({ color, hatched, className }: { color: string; hatched?: boolean; className?: string }) {
  return (
    <span
      aria-hidden
      className={cn("inline-block size-2.5 shrink-0 rounded-[3px] ring-1 ring-foreground/15", className)}
      style={{
        background: hatched
          ? `repeating-linear-gradient(135deg, ${color} 0 2px, color-mix(in srgb, ${color} 45%, transparent) 2px 4px)`
          : color,
      }}
    />
  );
}

/** Pictogram of a pattern type: the frame is the unit cell, filled shapes the layer material. */
export function PatternGlyph({ kind, className }: { kind: PatternKind; className?: string }) {
  const squares: Partial<Record<PatternKind, [number, number][]>> = {
    ch_square: [
      [4, 4],
      [12, 4],
      [4, 12],
      [12, 12],
    ],
    ch_staggered: [
      [3.5, 3.5],
      [12.5, 3.5],
      [8, 8],
      [3.5, 12.5],
      [12.5, 12.5],
    ],
  };
  return (
    <svg viewBox="0 0 20 20" aria-hidden className={cn("size-4", className)} fill="currentColor">
      <rect
        x="1.25"
        y="1.25"
        width="17.5"
        height="17.5"
        rx="2.5"
        fill={kind === "none" ? "currentColor" : "none"}
        fillOpacity={0.15}
        stroke="currentColor"
        strokeOpacity={0.55}
        strokeWidth="1.2"
      />
      {kind === "ls_v" && (
        <>
          <rect x="4.5" y="3.5" width="3.5" height="13" rx="0.6" />
          <rect x="12" y="3.5" width="3.5" height="13" rx="0.6" />
        </>
      )}
      {kind === "ls_h" && (
        <>
          <rect x="3.5" y="4.5" width="13" height="3.5" rx="0.6" />
          <rect x="3.5" y="12" width="13" height="3.5" rx="0.6" />
        </>
      )}
      {squares[kind]?.map(([x, y]) => (
        <rect key={`${x},${y}`} x={x} y={y} width="4" height="4" rx="0.6" />
      ))}
    </svg>
  );
}
