// Per-panel view settings (section planes, colormaps, toggles), remembered across visits.
import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { Polarization } from "@/api/model";
import type { CameraGeometry } from "@/lib/camera";
import type { Scale } from "@/lib/colorize";
import type { ColormapName } from "@/lib/colormaps";
import type { FieldQuantity } from "@/lib/field";
import type { SetupSectionId } from "@/lib/stack";

export interface SectionView {
  axis: "x" | "y";
  /** Position of the section plane as a fraction of the unit cell (0-1). */
  offset: number;
  periods: number;
  /** Depth range in nm; null = automatic (just past the patterned layers). */
  zMin: number | null;
  zMax: number | null;
}

export interface CameraSettings extends CameraGeometry {
  /** Point the camera at the specular order, or at theta_deg / phi_deg. */
  aim: "specular" | "manual";
  /** Window: every order in front of the camera, or just the sensor. */
  zoom: "all" | "sensor";
}

export interface ViewState {
  /** Expanded sections of the setup panel (missing ids use SETUP_OPEN). */
  setup: { open: Partial<Record<SetupSectionId, boolean>> };
  geometry: { section: SectionView; slice: number | null; show3d: boolean; cut: number; periods3d: number };
  dielectric: {
    section: SectionView;
    part: "re" | "im";
    fourier: boolean;
    colormap: ColormapName;
    slice: number | null;
  };
  diffraction: {
    log: boolean;
    na: number;
    reduction: number;
    pol: Polarization | null;
    pupilZoom: "full" | "na";
    /** The Pupil card shows direction cosines, or the orders on a flat camera sensor. */
    pupilMode: "pupil" | "camera";
    camera: CameraSettings;
  };
  nearfield: {
    section: SectionView;
    pol: Polarization | null;
    quantity: FieldQuantity;
    colormap: ColormapName | "auto";
    scale: Scale;
    phase: number;
    depth: number | null;
    boundaries: boolean;
    slice: number | null;
  };
  sweep: { parameter: string | null; start: number; stop: number; points: number; orders: string[] };
  python: { view: string | null };
  measurement: {
    colormap: ColormapName;
    scale: Scale;
    /** Percentiles clipped at each end of the color range (0 = min-max). */
    clip: number;
    /** Show the mean of all frames instead of one. */
    average: boolean;
  };
}

const section = (): SectionView => ({ axis: "x", offset: 0.5, periods: 2, zMin: null, zMax: null });

export const SETUP_OPEN: Record<SetupSectionId, boolean> = {
  stack: true,
  pattern: true,
  illumination: true,
  accuracy: true,
  materials: false,
};

const DEFAULTS: ViewState = {
  setup: { open: {} },
  geometry: { section: section(), slice: null, show3d: true, cut: 1, periods3d: 2 },
  dielectric: { section: section(), part: "re", fourier: true, colormap: "viridis", slice: null },
  diffraction: {
    log: true,
    na: 0.33,
    reduction: 4,
    pol: null,
    pupilZoom: "full",
    pupilMode: "pupil",
    camera: {
      distance_mm: 100,
      width_mm: 27.6,
      height_mm: 27.6,
      aim: "specular",
      theta_deg: 85,
      phi_deg: 0,
      zoom: "all",
    },
  },
  nearfield: {
    section: section(),
    pol: null,
    quantity: "|E|²",
    colormap: "auto",
    scale: "linear",
    phase: 0,
    depth: null,
    boundaries: true,
    slice: null,
  },
  sweep: { parameter: null, start: 0, stop: 12, points: 13, orders: [] },
  python: { view: null },
  measurement: { colormap: "inferno", scale: "linear", clip: 0.1, average: false },
};

interface ViewStore extends ViewState {
  setView: <K extends keyof ViewState>(panel: K, patch: Partial<ViewState[K]>) => void;
  setSection: (panel: "geometry" | "dielectric" | "nearfield", patch: Partial<SectionView>) => void;
}

export const useView = create<ViewStore>()(
  persist(
    (set) => ({
      ...DEFAULTS,
      setView: (panel, patch) => set((s) => ({ [panel]: { ...s[panel], ...patch } }) as Partial<ViewStore>),
      setSection: (panel, patch) =>
        set((s) => ({ [panel]: { ...s[panel], section: { ...s[panel].section, ...patch } } }) as Partial<ViewStore>),
    }),
    {
      name: "masksim.view.v1",
      merge: (persisted, current) => {
        // Shallow-merge each panel so settings added in later versions get defaults.
        const saved = (persisted ?? {}) as Partial<ViewState>;
        const out = { ...current };
        for (const key of Object.keys(DEFAULTS) as (keyof ViewState)[]) {
          Object.assign(out, { [key]: { ...current[key], ...(saved[key] ?? {}) } });
        }
        return out;
      },
    },
  ),
);
