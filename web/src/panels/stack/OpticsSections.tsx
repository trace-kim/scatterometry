// Illumination (wavelength, angles, polarization) and solver accuracy (Fourier orders and
// sampling), with the diffraction orders the pattern actually sends back as a guide for N.
import { isContactHoles, type Project } from "@/api/model";
import { Note, Segmented, StackedField } from "@/components/controls";
import { NumberField } from "@/components/number-field";
import { fmt } from "@/lib/format";
import { isPatterned, minimumOrders, orderWindow, propagatingOrders } from "@/lib/stack";
import { editProject, useProject } from "@/state/project";
import { useStack } from "../common";
import { SetupSection } from "./ui";

const POLARIZATION = {
  TE: { label: "TE", note: "E perpendicular to the plane of incidence (s)." },
  TM: { label: "TM", note: "E in the plane of incidence (p)." },
  "TE+TM": { label: "TE + TM", note: "Solves both; results show each and their unpolarized average." },
} as const;

export function IlluminationSection({ problems }: { problems: number }) {
  const { illumination: ill } = useProject();
  const set = <K extends keyof Project["illumination"]>(field: K, value: Project["illumination"][K]) =>
    editProject((d) => {
      d.illumination[field] = value;
    }, `illumination:${field}`);
  return (
    <SetupSection
      id="illumination"
      title="Illumination"
      summary={`${fmt(ill.wavelength_nm)} nm, θ ${fmt(ill.theta_deg)}°, φ ${fmt(ill.phi_deg)}°, ${POLARIZATION[ill.polarization].label}`}
      problems={problems}
    >
      <div className="grid grid-cols-3 gap-2">
        <StackedField label="Wavelength λ">
          <NumberField
            value={ill.wavelength_nm}
            onChange={(v) => set("wavelength_nm", v)}
            min={0.01}
            step={0.1}
            unit="nm"
            aria-label="Wavelength"
          />
        </StackedField>
        <StackedField label="Incidence θ" hint="Angle from the surface normal">
          <NumberField
            value={ill.theta_deg}
            onChange={(v) => set("theta_deg", v)}
            min={0}
            max={89}
            step={0.5}
            unit="°"
            aria-label="Angle of incidence"
          />
        </StackedField>
        <StackedField label="Azimuth φ" hint="Direction of the plane of incidence in the mask plane">
          <NumberField
            value={ill.phi_deg}
            onChange={(v) => set("phi_deg", v)}
            min={-180}
            max={180}
            step={1}
            unit="°"
            aria-label="Azimuth"
          />
        </StackedField>
      </div>
      <Note>
        θ is measured from the surface normal. φ = 0° puts the plane of incidence in x–z, across vertical lines.
      </Note>
      <StackedField label="Polarization">
        <Segmented
          aria-label="Polarization"
          value={ill.polarization}
          onChange={(v) => set("polarization", v)}
          options={[
            { value: "TE", label: "TE" },
            { value: "TM", label: "TM" },
            { value: "TE+TM", label: "Both" },
          ]}
        />
        <Note className="ml-1">{POLARIZATION[ill.polarization].note}</Note>
      </StackedField>
    </SetupSection>
  );
}

const signed = (v: number) => (v < 0 ? `−${-v}` : String(v));
const span = ([lo, hi]: [number, number]) => `${signed(lo)} … ${signed(hi)}`;

const CENTERING = {
  pupil: "Orders are centred on the pupil (k_t = 0), so oblique and grazing incidence keep every propagating order.",
  specular: "Orders −N…N around the specular order, as in most RCWA codes; grazing incidence needs about twice the N.",
} as const;

export function AccuracySection({ problems }: { problems: number }) {
  const project = useProject();
  const { summary } = useStack();
  const { numerics: num, pattern } = project;
  const ch = isContactHoles(pattern.kind);
  const patterned = isPatterned(project);
  const orders = propagatingOrders(project);
  const need = minimumOrders(project);
  const window = orderWindow(project);
  const set = (field: Exclude<keyof Project["numerics"], "centering">, value: number) =>
    editProject((d) => {
      d.numerics[field] = Math.max(0, Math.round(value));
    }, `numerics:${field}`);

  const harmonics = ch ? (2 * num.nx + 1) * (2 * num.ny + 1) : 2 * num.nx + 1;
  const title = !patterned
    ? "Not needed without a pattern"
    : ch
      ? `Nx ${num.nx}, Ny ${num.ny}, ${harmonics} harmonics`
      : `N = ${num.nx}, ${harmonics} harmonics`;

  // Propagating orders outside the window would be missing from the result, power and all.
  const short = !!need && (num.nx < need.nx || (ch && num.ny < need.ny));
  let guide: string | null = null;
  if (orders && need) {
    const range =
      pattern.kind === "ls_v"
        ? `m = ${span(orders.m)}`
        : pattern.kind === "ls_h"
          ? `n = ${span(orders.n)}`
          : `m = ${span(orders.m)}, n = ${span(orders.n)}`;
    const minimum = ch ? `Nx ≥ ${need.nx} and Ny ≥ ${need.ny}` : `N ≥ ${need.nx}`;
    guide = short
      ? `${orders.count} orders propagate (${range}), but the solver keeps fewer, so their power is lost. Use ${minimum}.`
      : `${orders.count} orders propagate (${range}), so ${minimum} is the minimum; higher is more accurate and slower.`;
  }

  return (
    <SetupSection
      id="accuracy"
      title="Accuracy"
      summary={title}
      problems={problems}
      warning={short ? "orders cut off" : null}
    >
      <div className="grid grid-cols-3 gap-2">
        <StackedField
          label={ch ? "Orders Nx" : "Fourier orders N"}
          hint="Harmonics on each side of the window centre along the periodic axis; more are more accurate and slower"
        >
          <NumberField
            value={num.nx}
            onChange={(v) => set("nx", v)}
            min={0}
            max={80}
            digits={0}
            aria-label={ch ? "Fourier orders Nx" : "Fourier orders N"}
          />
        </StackedField>
        {ch && (
          <StackedField label="Orders Ny">
            <NumberField
              value={num.ny}
              onChange={(v) => set("ny", v)}
              min={0}
              max={40}
              digits={0}
              aria-label="Fourier orders Ny"
            />
          </StackedField>
        )}
        <StackedField
          label="Grid samples"
          hint="Real-space samples per period for the Fourier transform; 0 = automatic"
        >
          <NumberField
            value={num.grid}
            onChange={(v) => set("grid", v)}
            min={0}
            max={8192}
            step={64}
            digits={0}
            aria-label="Grid samples"
          />
        </StackedField>
      </div>
      {!patterned ? (
        <Note>Without a patterned layer only the specular order exists, so these settings are not used.</Note>
      ) : (
        <>
          {guide && <Note tone={short ? "warn" : "muted"}>{guide}</Note>}
          <StackedField label="Order window">
            <Segmented
              aria-label="Order window"
              value={num.centering}
              onChange={(centering) =>
                editProject((d) => {
                  d.numerics.centering = centering;
                }, "numerics:centering")
              }
              options={[
                { value: "pupil", label: "Pupil centre", hint: CENTERING.pupil },
                { value: "specular", label: "Specular", hint: CENTERING.specular },
              ]}
            />
            <Note className="ml-1">{CENTERING[num.centering]}</Note>
          </StackedField>
          {summary && summary.harmonics > 1 && window && (
            <Note>
              The solver keeps orders{" "}
              {pattern.kind === "ls_h"
                ? `n = ${span(window.n)}`
                : ch
                  ? `m = ${span(window.m)}, n = ${span(window.n)}`
                  : `m = ${span(window.m)}`}
              : {summary.harmonics} harmonics, {summary.matrix_size} × {summary.matrix_size} matrices, sampled on a{" "}
              {summary.grid[0]} × {summary.grid[1]} grid (grid samples 0 = automatic).
            </Note>
          )}
        </>
      )}
    </SetupSection>
  );
}
