// Small compositions of the shadcn primitives used throughout the panels.
import type { ReactNode } from "react";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { cn } from "@/lib/utils";

export interface Option<T extends string | number> {
  value: T;
  label: ReactNode;
  hint?: string;
  disabled?: boolean;
  /** Shown before the label in a select's list (not in the closed select). */
  icon?: ReactNode;
}

export function SelectField<T extends string | number>({
  value,
  options,
  onChange,
  className,
  size = "default",
  "aria-label": ariaLabel,
}: {
  value: T;
  options: Option<T>[];
  onChange: (value: T) => void;
  className?: string;
  size?: "sm" | "default";
  "aria-label"?: string;
}) {
  return (
    <Select
      value={value}
      items={options.map((o) => ({ value: o.value, label: o.label }))}
      onValueChange={(next) => {
        if (next !== null && next !== undefined) onChange(next as T);
      }}
    >
      <SelectTrigger size={size} className={cn("w-full min-w-0", className)} aria-label={ariaLabel}>
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {options.map((o) => (
          <SelectItem key={String(o.value)} value={o.value} title={o.hint} disabled={o.disabled}>
            {o.icon}
            {o.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

/** Single-choice segmented control: a recessed track with the chosen segment raised. */
export function Segmented<T extends string>({
  value,
  options,
  onChange,
  className,
  "aria-label": ariaLabel,
}: {
  value: T;
  options: Option<T>[];
  onChange: (value: T) => void;
  className?: string;
  "aria-label"?: string;
}) {
  return (
    <ToggleGroup
      value={[value]}
      onValueChange={(next) => {
        if (next.length) onChange(next[0] as T);
      }}
      size="sm"
      spacing={0.5}
      className={cn("rounded-md bg-muted p-0.5 dark:bg-input/30", className)}
      aria-label={ariaLabel}
    >
      {options.map((o) => (
        <ToggleGroupItem
          key={o.value}
          value={o.value}
          title={o.hint}
          disabled={o.disabled}
          className="h-6 rounded-[5px] px-2 text-[11px] text-muted-foreground hover:bg-transparent hover:text-foreground aria-pressed:bg-background aria-pressed:font-semibold aria-pressed:text-foreground aria-pressed:shadow-sm hover:aria-pressed:bg-background dark:aria-pressed:bg-input/80 dark:hover:aria-pressed:bg-input/80"
        >
          {o.label}
        </ToggleGroupItem>
      ))}
    </ToggleGroup>
  );
}

/** Control with its label above it, for compact forms in narrow panels. */
export function StackedField({
  label,
  hint,
  children,
  className,
}: {
  label: ReactNode;
  hint?: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex min-w-0 flex-col gap-1", className)}>
      <span className="truncate text-[11px] font-medium text-muted-foreground" title={hint}>
        {label}
      </span>
      <div className="flex min-w-0 items-center gap-1.5">{children}</div>
    </div>
  );
}

/** A line of guidance under a form: neutral, a warning, or a problem. */
export function Note({
  tone = "muted",
  children,
  className,
}: {
  tone?: "muted" | "warn" | "danger";
  children: ReactNode;
  className?: string;
}) {
  return (
    <p
      className={cn(
        "text-[11px] leading-snug",
        tone === "muted" && "text-muted-foreground",
        tone === "warn" && "text-amber-700 dark:text-amber-400",
        tone === "danger" && "text-destructive",
        className,
      )}
    >
      {children}
    </p>
  );
}

/** Labelled control for toolbars. */
export function ToolbarItem({
  label,
  children,
  className,
}: {
  label?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex items-center gap-1.5", className)}>
      {label && <span className="text-[11px] whitespace-nowrap text-muted-foreground">{label}</span>}
      {children}
    </div>
  );
}
