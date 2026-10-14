// Domain types used across the UI. Generated API types (./gen) mark fields with server
// defaults as optional; documents in the app are always complete (the server fills
// defaults via /api/project/normalize), so these are the fully-populated versions.
import type * as gen from "./gen";

type Complete<T> = { [K in keyof T]-?: Exclude<T[K], undefined> };

export type MaterialDoc = Complete<gen.MaterialDoc>;
export type LayerDoc = Complete<gen.LayerDoc>;
export type PatternDoc = Complete<gen.PatternDoc>;
export type IlluminationDoc = Complete<gen.IlluminationDoc>;
export type NumericsDoc = Complete<gen.NumericsDoc>;
export type PatternKind = PatternDoc["kind"];
export type Polarization = "TE" | "TM";

export type Project = Omit<Complete<gen.Project>, "materials" | "layers" | "pattern" | "illumination" | "numerics"> & {
  materials: MaterialDoc[];
  layers: LayerDoc[];
  pattern: PatternDoc;
  illumination: IlluminationDoc;
  numerics: NumericsDoc;
};

export type CheckResult = gen.CheckResult;
export type SliceInfo = gen.SliceInfo;
export type StackSummary = gen.StackSummary;
export type SweepParameter = gen.SweepParameter;
export type JobInfo = gen.JobInfo;
export type PresetInfo = gen.PresetInfo;
export type OrderRow = gen.OrderRow;
export type OrdersResponse = gen.OrdersResponse;
export type PupilResponse = gen.PupilResponse;
export type FluxResponse = gen.FluxResponse;
export type AbsorptionResponse = gen.AbsorptionResponse;
export type ModesResponse = gen.ModesResponse;
export type BoxesResponse = gen.BoxesResponse;
export type SweepRecord = gen.SweepRecord;
export type SweepResult = gen.SweepResult;
export type PythonViewInfo = gen.PythonViewInfo;
export type PythonViewResult = gen.PythonViewResult;
export type MeasurementInfo = Complete<gen.MeasurementInfo>;
export type MeasurementRegion = gen.MeasurementRegion;
export type MeasurementTrace = gen.MeasurementTrace;
export type SettingRow = gen.SettingRow;

export interface RunSummary {
  elapsed: number;
  power: Record<Polarization, { R_total: number; T_total: number; A_total: number }>;
  harmonics: number;
  slices: number;
}

export interface CrossCheck {
  pol: Polarization;
  seconds: number;
  dR: number;
  dT: number;
}

export const PATTERN_KINDS: { value: PatternKind; label: string }[] = [
  { value: "none", label: "Unpatterned (blank)" },
  { value: "ls_v", label: "L/S vertical (lines along y)" },
  { value: "ls_h", label: "L/S horizontal (lines along x)" },
  { value: "ch_square", label: "C/H square array" },
  { value: "ch_staggered", label: "C/H staggered array" },
];

export function isContactHoles(kind: PatternKind): boolean {
  return kind === "ch_square" || kind === "ch_staggered";
}
