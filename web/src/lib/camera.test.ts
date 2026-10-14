import { describe, expect, it } from "vitest";
import { aimAt, cameraBasis, projectOrders, viewHorizon, viewOrders, viewSensor } from "./camera";

const sin85 = Math.sin((85 * Math.PI) / 180);

describe("camera projection", () => {
  it("builds a right-handed basis with u parallel to the mask and v away from it", () => {
    const { a, u, v } = cameraBasis(85, 0);
    expect(u[0]).toBeCloseTo(0);
    expect(u[1]).toBeCloseTo(1);
    expect(u[2]).toBeCloseTo(0);
    expect(v[2]).toBeGreaterThan(0);
    expect(a[0] * u[0] + a[1] * u[1] + a[2] * u[2]).toBeCloseTo(0);
    // Straight down the normal the basis is still defined.
    const top = cameraBasis(0, 30);
    expect(Math.hypot(...top.u)).toBeCloseTo(1);
  });

  it("puts the order it aims at in the sensor centre", () => {
    const aim = aimAt(sin85, 0);
    expect(aim.theta_deg).toBeCloseTo(85);
    const p = projectOrders([sin85], [0], { distance_mm: 100, width_mm: 10, height_mm: 10, ...aim });
    expect(p.u[0]).toBeCloseTo(0);
    expect(p.v[0]).toBeCloseTo(0);
    expect(p.offAxis_deg[0]).toBeCloseTo(0);
    expect(p.onSensor[0]).toBe(true);
  });

  it("turns a pupil column (fixed kx) into a circle seen along x", () => {
    // Orders sharing kx/k0 = 0.8907 lie on a cone around x; looking along x it is a circle of radius L tan ψ.
    const c = 0.8907;
    const sy = [-0.4, -0.2, 0, 0.2, 0.4];
    const p = projectOrders(Array(sy.length).fill(c), sy, {
      distance_mm: 50,
      width_mm: 100,
      height_mm: 100,
      theta_deg: 90,
      phi_deg: 0,
    });
    const radius = (50 * Math.sqrt(1 - c * c)) / c;
    for (let i = 0; i < sy.length; i++) expect(Math.hypot(p.u[i], p.v[i])).toBeCloseTo(radius, 9);
  });

  it("drops orders behind the camera and off the sensor", () => {
    const p = projectOrders([-0.9, 0.95], [0, 0.2], {
      distance_mm: 50,
      width_mm: 5,
      height_mm: 5,
      theta_deg: 85,
      phi_deg: 0,
    });
    expect(Number.isNaN(p.u[0])).toBe(true);
    expect(p.onSensor).toEqual([false, false]);
  });

  it("matches the pupil when looking down the normal", () => {
    const sx = [0.3, -0.5, 0.0];
    const sy = [0.1, 0.4, -0.7];
    const view = viewOrders(sx, sy, { distance_mm: 10, width_mm: 1, height_mm: 1, theta_deg: 0, phi_deg: 0 });
    for (let i = 0; i < sx.length; i++) {
      expect(view.x[i]).toBeCloseTo(sx[i], 12);
      expect(view.y[i]).toBeCloseTo(sy[i], 12);
    }
  });

  it("keeps the pupil's orientation at grazing incidence", () => {
    const cam = { distance_mm: 100, width_mm: 10, height_mm: 10, ...aimAt(sin85, 0) };
    // Specular in the centre, the mask surface (+x, grazing) to its right, ky still vertical.
    const view = viewOrders([sin85, 0.8907, 0.8907], [0, 0, 0.3], cam);
    expect(view.x[0]).toBeCloseTo(0, 12);
    expect(view.y[0]).toBeCloseTo(0, 12);
    expect(view.x[1]).toBeLessThan(0);
    expect(view.y[2]).toBeCloseTo(0.3, 12);
    const edge = viewHorizon(cam).filter((p): p is [number, number] => p !== null);
    expect(Math.max(...edge.map((p) => p[0]))).toBeGreaterThan(0);
    // The sensor footprint surrounds the specular order.
    const sensor = viewSensor(cam);
    expect(Math.min(...sensor.map((p) => p[0]))).toBeLessThan(0);
    expect(Math.max(...sensor.map((p) => p[0]))).toBeGreaterThan(0);
  });

  it("shows a pupil column as a circle when looking along x", () => {
    const c = 0.8907;
    const sy = [-0.4, 0, 0.3];
    const view = viewOrders(Array(sy.length).fill(c), sy, {
      distance_mm: 1,
      width_mm: 1,
      height_mm: 1,
      theta_deg: 90,
      phi_deg: 0,
    });
    for (let i = 0; i < sy.length; i++) expect(Math.hypot(view.x[i], view.y[i])).toBeCloseTo(Math.sqrt(1 - c * c), 12);
  });
});
