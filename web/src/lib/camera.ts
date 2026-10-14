// Diffraction orders as a flat camera sensor sees them. The pupil plots direction cosines
// (kx, ky)/(k0 n), where the orders of a periodic mask form a lattice; a camera facing the
// reflected beam sees the same directions through a central (gnomonic) projection, which
// bends each lattice column into an arc at grazing incidence.

export interface CameraGeometry {
  /** Distance from the illuminated spot on the mask to the sensor centre, mm. */
  distance_mm: number;
  /** Sensor size, mm. */
  width_mm: number;
  height_mm: number;
  /** Direction of the camera axis (towards the sensor): polar angle from the mask normal, and azimuth. */
  theta_deg: number;
  phi_deg: number;
}

type Vec = [number, number, number];

const dot = (a: Vec, b: Vec) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
const cross = (a: Vec, b: Vec): Vec => [
  a[1] * b[2] - a[2] * b[1],
  a[2] * b[0] - a[0] * b[2],
  a[0] * b[1] - a[1] * b[0],
];
const unit = (a: Vec): Vec => {
  const n = Math.hypot(...a);
  return [a[0] / n, a[1] / n, a[2] / n];
};

/**
 * Camera axis `a` and sensor axes: `u` horizontal (parallel to the mask surface) and `v`
 * pointing away from the mask. For an axis in the x-z plane, u is +y.
 */
export function cameraBasis(theta_deg: number, phi_deg: number): { a: Vec; u: Vec; v: Vec } {
  const t = (theta_deg * Math.PI) / 180;
  const p = (phi_deg * Math.PI) / 180;
  const a: Vec = [Math.sin(t) * Math.cos(p), Math.sin(t) * Math.sin(p), Math.cos(t)];
  // Looking straight down the normal, "horizontal" is the in-plane direction normal to the azimuth.
  const u = Math.sin(t) < 1e-9 ? ([-Math.sin(p), Math.cos(p), 0] as Vec) : unit(cross([0, 0, 1], a));
  return { a, u, v: cross(a, u) };
}

/** Axis pointing at a given order: (sx, sy) are its direction cosines in the incident medium. */
export function aimAt(sx: number, sy: number): { theta_deg: number; phi_deg: number } {
  const s = Math.min(Math.hypot(sx, sy), 1);
  return { theta_deg: (Math.asin(s) * 180) / Math.PI, phi_deg: s > 0 ? (Math.atan2(sy, sx) * 180) / Math.PI : 0 };
}

export interface ProjectedOrders {
  /** Sensor-plane coordinates in mm (NaN behind the camera). */
  u: number[];
  v: number[];
  /** Angle between each order and the camera axis, degrees. */
  offAxis_deg: number[];
  /** Whether the order lands on the sensor rectangle. */
  onSensor: boolean[];
}

/** Project reflected orders with direction cosines (sx, sy), sz = √(1 − sx² − sy²), onto the sensor. */
export function projectOrders(sx: number[], sy: number[], cam: CameraGeometry): ProjectedOrders {
  const { a, u: eu, v: ev } = cameraBasis(cam.theta_deg, cam.phi_deg);
  const out: ProjectedOrders = { u: [], v: [], offAxis_deg: [], onSensor: [] };
  sx.forEach((x, i) => {
    const d: Vec = [x, sy[i], Math.sqrt(Math.max(1 - x * x - sy[i] * sy[i], 0))];
    const c = dot(d, a);
    const ahead = c > 1e-9;
    const u = ahead ? (cam.distance_mm * dot(d, eu)) / c : Number.NaN;
    const v = ahead ? (cam.distance_mm * dot(d, ev)) / c : Number.NaN;
    out.u.push(u);
    out.v.push(v);
    out.offAxis_deg.push((Math.acos(Math.max(-1, Math.min(1, c))) * 180) / Math.PI);
    out.onSensor.push(ahead && Math.abs(u) <= cam.width_mm / 2 && Math.abs(v) <= cam.height_mm / 2);
  });
  return out;
}

// ---- the pupil seen from the camera ----------------------------------------------------
// The pupil is the orthographic projection of the outgoing directions along the mask normal.
// The camera view is the same projection along the camera axis, in a frame rotated from the
// pupil's (kx right, ky up) by the minimal rotation taking z to the axis. At theta = 0 the two
// views coincide; at grazing incidence lattice columns become arcs, as a camera sees them.

/** Pupil axes x and y rotated by the minimal rotation that takes z to the camera axis. */
export function viewBasis(theta_deg: number, phi_deg: number): { a: Vec; e1: Vec; e2: Vec } {
  const { a } = cameraBasis(theta_deg, phi_deg);
  const s = Math.hypot(a[0], a[1]);
  const c = a[2];
  if (s < 1e-12) return { a, e1: [1, 0, 0], e2: [0, 1, 0] };
  const k: Vec = [-a[1] / s, a[0] / s, 0]; // z x a, normalized
  const rotate = (v: Vec): Vec => {
    const kv = cross(k, v);
    const kd = dot(k, v) * (1 - c);
    return [v[0] * c + kv[0] * s + k[0] * kd, v[1] * c + kv[1] * s + k[1] * kd, v[2] * c + kv[2] * s + k[2] * kd];
  };
  return { a, e1: rotate([1, 0, 0]), e2: rotate([0, 1, 0]) };
}

export interface ViewPoints {
  /** Orthographic view coordinates (direction cosines about the camera axis). */
  x: number[];
  y: number[];
  /** In front of the camera (less than 90° from its axis). */
  front: boolean[];
}

const viewOf = (d: Vec, e1: Vec, e2: Vec): [number, number] => [dot(d, e1), dot(d, e2)];

/** Orders with direction cosines (sx, sy) in the camera's view. */
export function viewOrders(sx: number[], sy: number[], cam: CameraGeometry): ViewPoints {
  const { a, e1, e2 } = viewBasis(cam.theta_deg, cam.phi_deg);
  const out: ViewPoints = { x: [], y: [], front: [] };
  sx.forEach((x, i) => {
    const d: Vec = [x, sy[i], Math.sqrt(Math.max(1 - x * x - sy[i] * sy[i], 0))];
    const [u, v] = viewOf(d, e1, e2);
    out.x.push(u);
    out.y.push(v);
    out.front.push(dot(d, a) > 1e-9);
  });
  return out;
}

/** The mask surface (sz = 0) in the camera's view: the edge of the reflected half-space, front half only. */
export function viewHorizon(cam: CameraGeometry, samples = 721): ([number, number] | null)[] {
  const { a, e1, e2 } = viewBasis(cam.theta_deg, cam.phi_deg);
  const points: ([number, number] | null)[] = [];
  for (let i = 0; i < samples; i++) {
    const t = (2 * Math.PI * i) / (samples - 1);
    const d: Vec = [Math.cos(t), Math.sin(t), 0];
    if (dot(d, a) < 0) {
      if (points.length && points[points.length - 1] !== null) points.push(null);
      continue;
    }
    points.push(viewOf(d, e1, e2));
  }
  return points;
}

/** Outline of the flat sensor (its directions seen from the mask) in the camera's view. */
export function viewSensor(cam: CameraGeometry, perEdge = 24): [number, number][] {
  const { a, u, v } = cameraBasis(cam.theta_deg, cam.phi_deg);
  const { e1, e2 } = viewBasis(cam.theta_deg, cam.phi_deg);
  const w = cam.width_mm / 2;
  const h = cam.height_mm / 2;
  const corners: [number, number][] = [
    [-w, -h],
    [w, -h],
    [w, h],
    [-w, h],
    [-w, -h],
  ];
  const points: [number, number][] = [];
  for (let c = 0; c < 4; c++) {
    const [u0, v0] = corners[c];
    const [u1, v1] = corners[c + 1];
    for (let i = 0; i <= perEdge; i++) {
      const f = i / perEdge;
      const pu = u0 + (u1 - u0) * f;
      const pv = v0 + (v1 - v0) * f;
      const d = unit([
        a[0] * cam.distance_mm + u[0] * pu + v[0] * pv,
        a[1] * cam.distance_mm + u[1] * pu + v[1] * pv,
        a[2] * cam.distance_mm + u[2] * pu + v[2] * pv,
      ]);
      points.push(viewOf(d, e1, e2));
    }
  }
  return points;
}
