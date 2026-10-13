// Small compositions of the shadcn primitives used throughout the panels.
import type { ReactNode } from "react";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { cn } from "@/lib/utils";

export interface Option<T extends string | number> {
  value: T;
  label: ReactNode;
  hint?: string;
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
          <SelectItem key={String(o.value)} value={o.value} title={o.hint}>
            {o.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

/** Single-choice segmented control. */
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
      variant="outline"
      size="sm"
      spacing={0}
      className={className}
      aria-label={ariaLabel}
    >
      {options.map((o) => (
        <ToggleGroupItem key={o.value} value={o.value} title={o.hint} className="px-2 text-[11px]">
          {o.label}
        </ToggleGroupItem>
      ))}
    </ToggleGroup>
  );
}

/** Label/control row of a form grid. */
export function FieldRow({
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
    <div className={cn("grid grid-cols-[minmax(92px,38%)_1fr] items-center gap-2", className)}>
      <Label className="truncate text-xs font-normal text-muted-foreground" title={hint}>
        {label}
      </Label>
      <div className="flex min-w-0 items-center gap-1.5">{children}</div>
    </div>
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
