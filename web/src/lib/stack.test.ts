import { produce } from "immer";
import { describe, expect, it } from "vitest";
import type { LayerDoc, Project } from "@/api/model";
import {
  adjacentGroup,
  canMoveLayer,
  deleteLayer,
  insertLayer,
  joinGroup,
  layerBlocks,
  leaveGroup,
  materialUsage,
  minimumOrders,
  moveBlock,
  moveLayer,
  newGroup,
  problemSection,
  propagatingOrders,
  renameGroup,
  totalThickness,
  ungroup,
} from "./stack";

const layer = (name: string, thickness_nm: number, group = "", material = "Mo"): LayerDoc => ({
  name,
  material,
  thickness_nm,
  patterned: false,
  swa_deg: 90,
  steps: 1,
  group,
});

// The EUV line preset: absorber, cap, and a 40-pair Mo/Si mirror.
const euv: Project = {
  format: "masksim-project",
  version: 1,
  name: "EUV",
  materials: [
    { name: "Vacuum", n: 1, k: 0, color: null },
    { name: "Mo", n: 0.923791, k: 0.0064358, color: null },
    { name: "Si", n: 0.99900154, k: 0.0018265, color: null },
    { name: "Ru", n: 0.8864, k: 0.017066, color: null },
    { name: "TaBN", n: 0.95, k: 0.031, color: null },
  ],
  superstrate: "Vacuum",
  substrate: "Si",
  layers: [
    { ...layer("Absorber", 60, "", "TaBN"), patterned: true, swa_deg: 85, steps: 5 },
    layer("Cap", 2.5, "", "Ru"),
    layer("ML Si", 4.18, "ML", "Si"),
    layer("ML Mo", 2.71, "ML", "Mo"),
  ],
  repeats: { ML: 40 },
  pattern: {
    kind: "ls_v",
    pitch_x_nm: 128,
    pitch_y_nm: 128,
    cd_x_nm: 64,
    cd_y_nm: 64,
    hole_shape: "rect",
    tone: "holes",
    fill: "Vacuum",
    cd_reference: "top",
  },
  illumination: { wavelength_nm: 13.5, theta_deg: 6, phi_deg: 0, polarization: "TE" },
  numerics: { nx: 15, ny: 15, grid: 0 },
};

const names = (p: Project) => p.layers.map((l) => `${l.name}${l.group ? `@${l.group}` : ""}`);

describe("repeat groups", () => {
  it("splits the stack into runs and expands the thickness like the solver", () => {
    expect(layerBlocks(euv)).toEqual([
      { group: "", start: 0, end: 1, count: 1 },
      { group: "", start: 1, end: 2, count: 1 },
      { group: "ML", start: 2, end: 4, count: 40 },
    ]);
    // 60 + 2.5 + 40 x 6.89 nm, the figure the stack summary shows.
    expect(totalThickness(euv).toFixed(1)).toBe("338.1");
  });

  it("moves ungrouped layers over whole groups and grouped layers only inside their group", () => {
    expect(canMoveLayer(euv, 1, 1)).toBe(true);
    const below = produce(euv, (d) => moveLayer(d, 1, 1));
    expect(names(below)).toEqual(["Absorber", "ML Si@ML", "ML Mo@ML", "Cap"]);
    expect(names(produce(below, (d) => moveLayer(d, 3, -1)))).toEqual(names(euv));

    expect(canMoveLayer(euv, 2, -1)).toBe(false);
    expect(canMoveLayer(euv, 3, 1)).toBe(false);
    expect(names(produce(euv, (d) => moveLayer(d, 3, -1)))).toEqual(["Absorber", "Cap", "ML Mo@ML", "ML Si@ML"]);
    expect(canMoveLayer(euv, 0, -1)).toBe(false);
  });

  it("moves a group as a block", () => {
    const up = produce(euv, (d) => moveBlock(d, 2, -1));
    expect(names(up)).toEqual(["Absorber", "ML Si@ML", "ML Mo@ML", "Cap"]);
    expect(names(produce(up, (d) => moveBlock(d, 1, 1)))).toEqual(names(euv));
  });

  it("inserts siblings into the reference layer's group", () => {
    const inside = produce(euv, (d) => insertLayer(d, 2, "below", layer("Interlayer", 0.5)));
    expect(names(inside)).toEqual(["Absorber", "Cap", "ML Si@ML", "Interlayer@ML", "ML Mo@ML"]);
    const outside = produce(euv, (d) => insertLayer(d, 1, "above", layer("Oxide", 1, "ignored")));
    expect(names(outside)).toEqual(["Absorber", "Oxide", "Cap", "ML Si@ML", "ML Mo@ML"]);
  });

  it("creates, joins, leaves, renames, and dissolves groups", () => {
    expect(adjacentGroup(euv, 1, 1)).toBe("ML");
    expect(adjacentGroup(euv, 1, -1)).toBeNull();
    const joined = produce(euv, (d) => joinGroup(d, 1, 1));
    expect(names(joined)).toEqual(["Absorber", "Cap@ML", "ML Si@ML", "ML Mo@ML"]);

    // A middle layer leaving its group moves below it; an edge layer stays put.
    const left = produce(joined, (d) => leaveGroup(d, 2));
    expect(names(left)).toEqual(["Absorber", "Cap@ML", "ML Mo@ML", "ML Si"]);
    expect(names(produce(joined, (d) => leaveGroup(d, 1)))).toEqual(names(euv));

    const grouped = produce(euv, (d) => {
      expect(newGroup(d, 0)).toBe("Group 1");
    });
    expect(grouped.repeats).toEqual({ ML: 40, "Group 1": 2 });

    const renamed = produce(euv, (d) => renameGroup(d, 3, "Mirror"));
    expect(names(renamed)).toEqual(["Absorber", "Cap", "ML Si@Mirror", "ML Mo@Mirror"]);
    expect(renamed.repeats).toEqual({ Mirror: 40 });
    expect(produce(euv, (d) => renameGroup(d, 2, "  "))).toBe(euv);

    const flat = produce(euv, (d) => ungroup(d, 2));
    expect(names(flat)).toEqual(["Absorber", "Cap", "ML Si", "ML Mo"]);
    expect(flat.repeats).toEqual({});
    expect(produce(euv, (d) => deleteLayer(d, 2)).repeats).toEqual({ ML: 40 });
  });
});

describe("setup helpers", () => {
  it("lists where each material is used", () => {
    const usage = materialUsage(euv);
    expect(usage.get("Vacuum")).toEqual(["incident medium", "pattern fill"]);
    expect(usage.get("Si")).toEqual(["ML Si", "substrate"]);
    expect(usage.has("Ru")).toBe(true);
    expect(usage.has("Ni")).toBe(false);
  });

  it("finds the propagating orders the solver reports", () => {
    // 128 nm pitch at 13.5 nm and 6°: the order table lists m = -8 ... 10.
    expect(propagatingOrders(euv)).toEqual({ m: [-8, 10], n: [0, 0], count: 19 });
    const horizontal = produce(euv, (d) => {
      d.pattern.kind = "ls_h";
    });
    // Lines along x diffract along y; at φ = 0 the orders are symmetric.
    expect(propagatingOrders(horizontal)).toEqual({ m: [0, 0], n: [-9, 9], count: 19 });
    const holes = produce(euv, (d) => {
      d.pattern.kind = "ch_square";
    });
    const orders = propagatingOrders(holes);
    expect(orders?.m).toEqual([-8, 10]);
    expect(orders?.n).toEqual([-9, 9]);
    expect(orders?.count).toBeLessThan(19 * 19);
    const blank = produce(euv, (d) => {
      d.layers[0].patterned = false;
    });
    expect(propagatingOrders(blank)).toBeNull();

    // N must reach the farthest propagating order on each periodic axis.
    expect(minimumOrders(euv)).toEqual({ nx: 10, ny: 0 });
    expect(minimumOrders(horizontal)).toEqual({ nx: 9, ny: 0 });
    expect(minimumOrders(holes)).toEqual({ nx: 10, ny: 9 });
    expect(minimumOrders(blank)).toBeNull();
  });

  it("maps every validation message to its setup section", () => {
    const cases: [string, string][] = [
      ["Material names must be unique.", "materials"],
      ["Unknown material 'TaBN'.", "stack"],
      ["Unknown material 'Vacuum'.", "stack"],
      ["The stack needs at least one layer.", "stack"],
      ["Layer 'grid' needs a positive thickness.", "stack"],
      ["Layer 'Absorber': sidewall angle must be between 0 and 180 deg.", "stack"],
      ["Layer 'Absorber': steps must be at least 1.", "stack"],
      ["Pitches must be positive.", "pattern"],
      ["CD must be between 0 and the pitch.", "pattern"],
      ["Wavelength must be positive.", "illumination"],
      ["Angle of incidence must be in [0, 90) deg.", "illumination"],
      ["At most 64 materials are supported.", "materials"],
      ["Harmonic orders must be non-negative.", "accuracy"],
      ["Grid must be 0 (automatic) or a positive sample count.", "accuracy"],
      ["The stack expands to 120,000 slices; at most 20,000 are supported. Reduce repeat counts.", "stack"],
      ["40,401 harmonics; at most 10,000 are supported. Reduce Nx/Ny.", "accuracy"],
      ["The sampling grid has 9,000,000 points; at most 4,194,304 are supported.", "accuracy"],
    ];
    for (const [message, section] of cases) expect(problemSection(message, euv), message).toBe(section);
    const fill = produce(euv, (d) => {
      d.pattern.fill = "Air";
    });
    expect(problemSection("Unknown material 'Air'.", fill)).toBe("pattern");
  });
});
