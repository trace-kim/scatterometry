// Panel scaffolding: a toolbar over a scrolling body, titled view cards, and the
// loading / error / empty states every view shares.
import { Alert02Icon, Loading03Icon } from "@hugeicons/core-free-icons";
import { HugeiconsIcon } from "@hugeicons/react";
import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

export function PanelLayout({
  toolbar,
  children,
  className,
}: {
  toolbar?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className="flex h-full min-h-0 flex-col bg-background">
      {toolbar && (
        <div className="flex shrink-0 flex-wrap items-center gap-x-4 gap-y-1.5 border-b bg-muted/30 px-3 py-1.5">
          {toolbar}
        </div>
      )}
      <div className={cn("min-h-0 flex-1 overflow-auto p-3", className)}>{children}</div>
    </div>
  );
}

export function ViewCard({
  title,
  subtitle,
  actions,
  children,
  className,
  bodyClassName,
  loading,
  errors,
}: {
  title: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
  loading?: boolean;
  errors?: string[];
}) {
  return (
    <section className={cn("flex min-h-0 min-w-0 flex-col overflow-hidden rounded-lg border bg-card", className)}>
      <header className="flex h-8 shrink-0 items-center gap-2 border-b px-2.5">
        <h3 className="shrink-0 text-xs font-semibold">{title}</h3>
        {subtitle && <span className="truncate text-[11px] text-muted-foreground">{subtitle}</span>}
        {loading && (
          <HugeiconsIcon icon={Loading03Icon} className="size-3.5 shrink-0 animate-spin text-muted-foreground" />
        )}
        <div className="ml-auto flex shrink-0 items-center gap-1">{actions}</div>
      </header>
      <div className={cn("relative min-h-0 flex-1", bodyClassName)}>
        {children}
        {errors && errors.length > 0 && <ErrorOverlay errors={errors} />}
      </div>
    </section>
  );
}

export function ErrorOverlay({ errors }: { errors: string[] }) {
  return (
    <div className="absolute inset-0 z-20 flex items-center justify-center bg-background/80 p-4 backdrop-blur-[1px]">
      <div className="max-w-md rounded-md border border-destructive/40 bg-card p-3 text-xs">
        <div className="mb-1 flex items-center gap-1.5 font-medium text-destructive">
          <HugeiconsIcon icon={Alert02Icon} className="size-3.5" />
          Can't show this view
        </div>
        <ul className="list-inside list-disc space-y-0.5 text-muted-foreground">
          {errors.map((e) => (
            <li key={e}>{e}</li>
          ))}
        </ul>
      </div>
    </div>
  );
}

export function EmptyState({ title, children, icon }: { title: ReactNode; children?: ReactNode; icon?: ReactNode }) {
  return (
    <div className="flex h-full min-h-40 flex-col items-center justify-center gap-2 p-6 text-center">
      {icon}
      <div className="text-sm font-medium">{title}</div>
      {children && <div className="max-w-sm text-xs text-muted-foreground">{children}</div>}
    </div>
  );
}

export function Stat({
  label,
  value,
  hint,
  className,
}: {
  label: ReactNode;
  value: ReactNode;
  hint?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("min-w-0 rounded-md border bg-card px-2.5 py-1.5", className)}>
      <div className="truncate text-[11px] text-muted-foreground">{label}</div>
      <div className="truncate text-sm font-semibold tabular-nums">{value}</div>
      {hint && <div className="truncate text-[10px] text-muted-foreground">{hint}</div>}
    </div>
  );
}
