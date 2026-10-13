// Field quantities from complex components, computed in the browser so switching the
// quantity or the time phase redraws instantly.
import type { NpyArray } from "./npz";

export type FieldQuantity =
  | "|E|²"
  | "|Ex|"
  | "|Ey|"
  | "|Ez|"
  | "Re Ex"
  | "Re Ey"
  | "Re Ez"
  | "arg Ex"
  | "arg Ey"
  | "arg Ez";

export const FIELD_QUANTITIES: { value: FieldQuantity; label: string; kind: "magnitude" | "signed" | "phase" }[] = [
  { value: "|E|²", label: "|E|²  (intensity)", kind: "magnitude" },
  { value: "|Ex|", label: "|Ex|", kind: "magnitude" },
  { value: "|Ey|", label: "|Ey|", kind: "magnitude" },
  { value: "|Ez|", label: "|Ez|", kind: "magnitude" },
  { value: "Re Ex", label: "Re Ex(t)", kind: "signed" },
  { value: "Re Ey", label: "Re Ey(t)", kind: "signed" },
  { value: "Re Ez", label: "Re Ez(t)", kind: "signed" },
  { value: "arg Ex", label: "arg Ex", kind: "phase" },
  { value: "arg Ey", label: "arg Ey", kind: "phase" },
  { value: "arg Ez", label: "arg Ez", kind: "phase" },
];

export function quantityKind(q: FieldQuantity): "magnitude" | "signed" | "phase" {
  return FIELD_QUANTITIES.find((f) => f.value === q)?.kind ?? "magnitude";
}

export interface ComplexField {
  Ex: NpyArray;
  Ey: NpyArray;
  Ez: NpyArray;
}

/**
 * Evaluate a quantity on every pixel. `phaseDeg` is the time phase ωt for the "Re"
 * quantities: with exp(+jωt) time dependence, E(t) = Re(E e^{jωt}).
 */
export function fieldQuantity(field: ComplexField, quantity: FieldQuantity, phaseDeg = 0): Float32Array {
  const n = field.Ex.data.length / 2;
  const out = new Float32Array(n);
  if (quantity === "|E|²") {
    const comps = [field.Ex.data, field.Ey.data, field.Ez.data];
    for (let i = 0; i < n; i++) {
      let s = 0;
      for (const c of comps) s += c[2 * i] * c[2 * i] + c[2 * i + 1] * c[2 * i + 1];
      out[i] = s;
    }
    return out;
  }
  const component = /E([xyz])/.exec(quantity)?.[1] ?? "x";
  const c = field[`E${component}` as keyof ComplexField].data;
  if (quantity.startsWith("|")) {
    for (let i = 0; i < n; i++) out[i] = Math.hypot(c[2 * i], c[2 * i + 1]);
  } else if (quantity.startsWith("Re")) {
    const phi = (phaseDeg * Math.PI) / 180;
    const cos = Math.cos(phi);
    const sin = Math.sin(phi);
    for (let i = 0; i < n; i++) out[i] = c[2 * i] * cos - c[2 * i + 1] * sin;
  } else {
    for (let i = 0; i < n; i++) out[i] = (Math.atan2(c[2 * i + 1], c[2 * i]) * 180) / Math.PI;
  }
  return out;
}

/** Real or imaginary part of a complex array. */
export function complexPart(array: NpyArray, part: "re" | "im"): Float32Array {
  const n = array.data.length / 2;
  const out = new Float32Array(n);
  const k = part === "re" ? 0 : 1;
  for (let i = 0; i < n; i++) out[i] = array.data[2 * i + k];
  return out;
}

/** log10 |z| of a complex array (convolution-matrix magnitudes). */
export function complexLogAbs(array: NpyArray, floor = 1e-16): Float32Array {
  const n = array.data.length / 2;
  const out = new Float32Array(n);
  for (let i = 0; i < n; i++) out[i] = Math.log10(Math.hypot(array.data[2 * i], array.data[2 * i + 1]) + floor);
  return out;
}
