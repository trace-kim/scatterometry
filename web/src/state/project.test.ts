import { beforeEach, describe, expect, it } from "vitest";
import type { Project } from "@/api/model";
import { isDirty, useProjectStore } from "./project";

const project: Project = {
  format: "masksim-project",
  version: 1,
  name: "Test",
  materials: [
    { name: "Air", n: 1, k: 0, color: null },
    { name: "Film", n: 2, k: 0.1, color: null },
  ],
  superstrate: "Air",
  substrate: "Air",
  layers: [{ name: "L1", material: "Film", thickness_nm: 10, patterned: true, swa_deg: 90, steps: 1, group: "" }],
  repeats: {},
  pattern: {
    kind: "ls_v",
    pitch_x_nm: 100,
    pitch_y_nm: 100,
    cd_x_nm: 50,
    cd_y_nm: 50,
    hole_shape: "rect",
    tone: "holes",
    fill: "Air",
    cd_reference: "top",
  },
  illumination: { wavelength_nm: 13.5, theta_deg: 6, phi_deg: 0, polarization: "TE" },
  numerics: { nx: 5, ny: 5, grid: 0, centering: "pupil" },
};

const store = () => useProjectStore.getState();

describe("project store", () => {
  beforeEach(() => store().load(project));

  it("undoes and redoes edits", () => {
    store().edit((d) => {
      d.pattern.cd_x_nm = 60;
    });
    store().edit((d) => {
      d.layers.push({ ...d.layers[0], name: "L2" });
    });
    expect(store().project?.layers).toHaveLength(2);

    store().undo();
    expect(store().project?.layers).toHaveLength(1);
    expect(store().project?.pattern.cd_x_nm).toBe(60);
    store().undo();
    expect(store().project?.pattern.cd_x_nm).toBe(50);
    store().redo();
    expect(store().project?.pattern.cd_x_nm).toBe(60);
  });

  it("coalesces rapid edits that share a key into one undo step", () => {
    for (const cd of [51, 52, 53]) {
      store().edit((d) => {
        d.pattern.cd_x_nm = cd;
      }, "pattern:cd_x_nm");
    }
    expect(store().past).toHaveLength(1);
    store().undo();
    expect(store().project?.pattern.cd_x_nm).toBe(50);
  });

  it("tracks unsaved changes by content and leaves the original document untouched", () => {
    expect(isDirty(store())).toBe(false);
    store().edit((d) => {
      d.name = "Renamed";
    });
    expect(isDirty(store())).toBe(true);
    expect(project.name).toBe("Test");
    store().undo();
    expect(isDirty(store())).toBe(false); // back to the loaded content
    store().redo();
    store().markSaved("a.json");
    expect(isDirty(store())).toBe(false);
  });

  it("ignores no-op edits", () => {
    store().edit((d) => {
      d.pattern.cd_x_nm = 50;
    });
    expect(store().past).toHaveLength(0);
  });
});
