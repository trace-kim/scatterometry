// The Pupil card's camera mode: the pupil seen from the camera. Same window, scale and style
// as the pupil (direction cosines, size ∝ √R, color = phase), projected along the camera axis
// instead of the mask normal, so at grazing incidence the lattice columns become arcs. The
// sensor is drawn by its exact footprint. Projection runs in the browser (lib/camera).
import type { PupilResponse } from "@/api/model";
import { Segmented, ToolbarItem } from "@/components/controls";
import { NumberField } from "@/components/number-field";
import { aimAt, type CameraGeometry, projectOrders, viewHorizon, viewOrders, viewSensor } from "@/lib/camera";
import { fixed } from "@/lib/format";
import type { CameraSettings } from "@/state/view";
import type { EChartsOption } from "@/viz/EChart";
import type { ThemeColors } from "@/viz/theme";
import { type OrderPoint, orderMapOption } from "./orderMap";

export function cameraGeometry(settings: CameraSettings, pupil: PupilResponse | undefined): CameraGeometry {
  const aim =
    settings.aim === "specular" && pupil
      ? aimAt(pupil.center[0], pupil.center[1])
      : { theta_deg: settings.theta_deg, phi_deg: settings.phi_deg };
  return { ...settings, ...aim };
}

export interface CameraSummary {
  onSensor: number;
  total: number;
  /** Orders going away from the camera (more than 90° off its axis), not drawn. */
  behind: number;
  /** Reflected power (fraction of incident) landing on the sensor. */
  power: number;
}

export function cameraOption(
  pupil: PupilResponse | undefined,
  settings: CameraSettings,
  colors: ThemeColors,
  grid: { left: number; top: number; width: number; height: number },
): { option: EChartsOption; summary: CameraSummary | null } {
  const cam = cameraGeometry(settings, pupil);
  const sensor = viewSensor(cam);
  let center: [number, number] = [0, 0];
  let half = 1.05;
  if (settings.zoom === "sensor") {
    const xs = sensor.map((p) => p[0]);
    const ys = sensor.map((p) => p[1]);
    center = [(Math.min(...xs) + Math.max(...xs)) / 2, (Math.min(...ys) + Math.max(...ys)) / 2];
    half = Math.max(Math.max(...xs) - Math.min(...xs), Math.max(...ys) - Math.min(...ys), 1e-6) * 0.625;
  }

  const points: OrderPoint[] = [];
  let summary: CameraSummary | null = null;
  if (pupil) {
    const view = viewOrders(pupil.sx, pupil.sy, cam);
    const flat = projectOrders(pupil.sx, pupil.sy, cam);
    let power = 0;
    let on = 0;
    pupil.R.forEach((R, i) => {
      if (!view.front[i]) return;
      if (flat.onSensor[i]) {
        on++;
        power += R;
      }
      points.push({
        x: view.x[i],
        y: view.y[i],
        R,
        phase: pupil.phase_deg[i] ?? 0,
        m: pupil.m[i],
        n: pupil.n[i],
        faded: !flat.onSensor[i],
        note: flat.onSensor[i]
          ? `on the sensor at (${fixed(flat.u[i], 2)}, ${fixed(flat.v[i], 2)}) mm`
          : `${fixed(flat.offAxis_deg[i], 1)}° off the camera axis`,
      });
    });
    summary = { onSensor: on, total: pupil.R.length, behind: pupil.R.length - points.length, power };
  }

  const option = orderMapOption({
    points,
    overlays: [
      { name: "mask surface", data: viewHorizon(cam), kind: "outline" },
      { name: "sensor", data: sensor, kind: "aperture" },
    ],
    center,
    half,
    zoomed: settings.zoom === "sensor",
    axisNames: ["camera x (direction cosine)", "camera y"],
    colors,
    grid,
  });
  return { option, summary };
}

export function CameraControls({
  settings,
  aimedAt,
  onChange,
}: {
  settings: CameraSettings;
  /** The axis actually used (from the specular order when aiming at it). */
  aimedAt: CameraGeometry;
  onChange: (patch: Partial<CameraSettings>) => void;
}) {
  const manual = settings.aim === "manual";
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 px-2 pt-1.5 pb-1">
      <ToolbarItem label="Distance">
        <NumberField
          className="w-24"
          value={settings.distance_mm}
          onChange={(distance_mm) => onChange({ distance_mm: Math.max(distance_mm, 0.1) })}
          min={0.1}
          max={10000}
          step={5}
          unit="mm"
          digits={2}
          aria-label="Camera distance"
        />
      </ToolbarItem>
      <ToolbarItem label="Sensor">
        <NumberField
          className="w-20"
          value={settings.width_mm}
          onChange={(width_mm) => onChange({ width_mm: Math.max(width_mm, 0.01) })}
          min={0.01}
          max={1000}
          step={1}
          digits={2}
          aria-label="Sensor width"
        />
        <span className="text-[11px] text-muted-foreground">×</span>
        <NumberField
          className="w-24"
          value={settings.height_mm}
          onChange={(height_mm) => onChange({ height_mm: Math.max(height_mm, 0.01) })}
          min={0.01}
          max={1000}
          step={1}
          unit="mm"
          digits={2}
          aria-label="Sensor height"
        />
      </ToolbarItem>
      <ToolbarItem label="Aim">
        <Segmented
          aria-label="Camera aim"
          value={settings.aim}
          onChange={(aim) =>
            // Switching to manual starts from the current specular aim.
            onChange(aim === "manual" ? { aim, theta_deg: aimedAt.theta_deg, phi_deg: aimedAt.phi_deg } : { aim })
          }
          options={[
            { value: "specular", label: "Specular", hint: "Centre the sensor on the specular order" },
            { value: "manual", label: "Angles", hint: "Point the camera axis by polar angle and azimuth" },
          ]}
        />
      </ToolbarItem>
      <ToolbarItem label="θ">
        <NumberField
          className="w-20"
          value={manual ? settings.theta_deg : aimedAt.theta_deg}
          onChange={(theta_deg) => onChange({ theta_deg })}
          min={0}
          max={90}
          step={0.5}
          unit="°"
          digits={3}
          disabled={!manual}
          aria-label="Camera polar angle"
        />
      </ToolbarItem>
      <ToolbarItem label="φ">
        <NumberField
          className="w-20"
          value={manual ? settings.phi_deg : aimedAt.phi_deg}
          onChange={(phi_deg) => onChange({ phi_deg })}
          min={-180}
          max={180}
          step={1}
          unit="°"
          digits={3}
          disabled={!manual}
          aria-label="Camera azimuth"
        />
      </ToolbarItem>
    </div>
  );
}
