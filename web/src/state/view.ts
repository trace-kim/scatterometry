// Per-panel view settings (section planes, colormaps, toggles), remembered across visits.
import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { Polarization } from "@/api/model";
import type { Scale } from "@/lib/colorize";
import type { ColormapName } from "@/lib/colormaps";
import type { FieldQuantity } from "@/lib/field";

export interface SectionView {
  axis: "x" | "y";
  /** Position of the section plane as a fraction of the unit cell (0-1). */
  offset: number;
  periods: number;
  /** Depth range in nm; null = automatic (just past the patterned layers). */
  zMin: number | null;
  zMax: number | null;
}

export interface ViewState {
  geometry: { section: SectionView; slice: number | null; show3d: boolean; cut: number; periods3d: number };
  dielectric: {
    section: SectionView;
    part: "re" | "im";
    fourier: boolean;
    colormap: ColormapName;
    slice: number | null;
  };
  diffraction: { log: boolean; na: number; reduction: number; pol: Polarization | null };
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
}

const section = (): SectionView => ({ axis: "x", offset: 0.5, periods: 2, zMin: null, zMax: null });

const DEFAULTS: ViewState = {
  geometry: { section: section(), slice: null, show3d: true, cut: 1, periods3d: 2 },
  dielectric: { section: section(), part: "re", fourier: true, colormap: "viridis", slice: null },
  diffraction: { log: true, na: 0.33, reduction: 4, pol: null },
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
