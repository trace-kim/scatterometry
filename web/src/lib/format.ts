// Number formatting for labels, tooltips, and tables.

/** Significant-digit formatting that switches to exponent notation for very small/large values. */
export function fmt(value: number | null | undefined, digits = 4): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  if (value === 0) return "0";
  const abs = Math.abs(value);
  if (abs < 1e-3 || abs >= 1e5) return value.toExponential(Math.max(digits - 1, 0));
  return Number(value.toPrecision(digits)).toString();
}

/** Fixed decimals, e.g. lengths in nm. */
export function fixed(value: number | null | undefined, decimals = 1): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  return value.toFixed(decimals);
}

export function percent(value: number, decimals = 2): string {
  return `${(value * 100).toFixed(decimals)} %`;
}

export function seconds(value: number): string {
  return value < 1 ? `${(value * 1000).toFixed(0)} ms` : `${value.toFixed(2)} s`;
}

/** "Nice" tick values covering [min, max] (about `count` of them). */
export function niceTicks(min: number, max: number, count = 5): number[] {
  if (!(max > min)) return [min];
  const span = max - min;
  const step0 = 10 ** Math.floor(Math.log10(span / count));
  const err = (count * step0) / span;
  const step = step0 * (err <= 0.15 ? 10 : err <= 0.35 ? 5 : err <= 0.75 ? 2 : 1);
  const ticks: number[] = [];
  for (let v = Math.ceil(min / step) * step; v <= max + step * 1e-9; v += step) ticks.push(Number(v.toPrecision(12)));
  return ticks;
}
