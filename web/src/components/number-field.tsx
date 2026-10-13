// Numeric input with units: Base UI NumberField styled like the shadcn input.
// Arrow keys step (Shift = large step, Alt = small step); dragging the label or unit scrubs
// the value, which pairs with the live geometry views.
import { NumberField as Field } from "@base-ui/react/number-field";
import { cn } from "@/lib/utils";

interface NumberFieldProps {
  value: number;
  onChange: (value: number) => void;
  min?: number;
  max?: number;
  step?: number;
  smallStep?: number;
  largeStep?: number;
  /** Unit suffix ("nm", "°"); dragging it scrubs the value. */
  unit?: string;
  /** Short prefix label ("x", "CD"); dragging it scrubs the value. */
  label?: string;
  /** Maximum fraction digits shown. */
  digits?: number;
  disabled?: boolean;
  className?: string;
  id?: string;
  "aria-label"?: string;
}

export function NumberField({
  value,
  onChange,
  min,
  max,
  step = 1,
  smallStep,
  largeStep,
  unit,
  label,
  digits = 6,
  disabled,
  className,
  id,
  "aria-label": ariaLabel,
}: NumberFieldProps) {
  const scrub = "flex h-full cursor-ew-resize items-center px-1.5 text-[11px] text-muted-foreground select-none";
  return (
    <Field.Root
      id={id}
      value={Number.isFinite(value) ? value : null}
      onValueChange={(next) => {
        if (next !== null && Number.isFinite(next)) onChange(next);
      }}
      min={min}
      max={max}
      step={step}
      smallStep={smallStep ?? step / 10}
      largeStep={largeStep ?? step * 10}
      format={{ maximumFractionDigits: digits, useGrouping: false }}
      disabled={disabled}
      className={cn("w-full min-w-0", className)}
    >
      <Field.Group className="flex h-7 w-full items-center overflow-hidden rounded-md border border-input bg-input/20 transition-colors focus-within:border-ring focus-within:ring-2 focus-within:ring-ring/30 data-disabled:opacity-50 dark:bg-input/30">
        {label && (
          <Field.ScrubArea direction="horizontal" pixelSensitivity={3} className={cn(scrub, "border-r border-input")}>
            {label}
          </Field.ScrubArea>
        )}
        <Field.Input
          aria-label={ariaLabel ?? label}
          className="h-full w-full min-w-0 bg-transparent px-2 text-xs tabular-nums outline-none"
        />
        {unit && (
          <Field.ScrubArea direction="horizontal" pixelSensitivity={3} className={cn(scrub, "pr-2 pl-0")}>
            {unit}
          </Field.ScrubArea>
        )}
      </Field.Group>
    </Field.Root>
  );
}
