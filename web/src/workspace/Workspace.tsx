// Dockable workspace (dockview): panels can be dragged, split, tabbed, and floated; the
// layout is remembered per browser.
import "dockview-react/dist/styles/dockview.css";
import {
  type DockviewApi,
  DockviewReact,
  type DockviewReadyEvent,
  type IDockviewPanelProps,
  themeDark,
  themeLight,
} from "dockview-react";
import { createContext, type FunctionComponent, lazy, Suspense, useContext, useState } from "react";
import { EmptyState } from "@/components/layout";
import { StackPanel } from "@/panels/StackPanel";
import { useDark } from "@/viz/theme";

// View panels load on first use (each pulls in ECharts, three.js, or AG Grid).
const GeometryPanel = lazy(() => import("@/panels/GeometryPanel").then((m) => ({ default: m.GeometryPanel })));
const DielectricPanel = lazy(() => import("@/panels/DielectricPanel").then((m) => ({ default: m.DielectricPanel })));
const DiffractionPanel = lazy(() => import("@/panels/DiffractionPanel").then((m) => ({ default: m.DiffractionPanel })));
const NearFieldPanel = lazy(() => import("@/panels/NearFieldPanel").then((m) => ({ default: m.NearFieldPanel })));
const SweepPanel = lazy(() => import("@/panels/SweepPanel").then((m) => ({ default: m.SweepPanel })));
const PythonViewsPanel = lazy(() => import("@/panels/PythonViewsPanel").then((m) => ({ default: m.PythonViewsPanel })));
const MeasurementPanel = lazy(() => import("@/panels/MeasurementPanel").then((m) => ({ default: m.MeasurementPanel })));

const LAYOUT_KEY = "masksim.layout.v1";

export const PANELS: { id: string; title: string; component: FunctionComponent }[] = [
  { id: "stack", title: "Setup", component: StackPanel },
  { id: "geometry", title: "Geometry", component: GeometryPanel },
  { id: "dielectric", title: "Dielectric ε", component: DielectricPanel },
  { id: "diffraction", title: "Diffraction", component: DiffractionPanel },
  { id: "nearfield", title: "Near field", component: NearFieldPanel },
  { id: "sweep", title: "Sweep", component: SweepPanel },
  { id: "python", title: "Python views", component: PythonViewsPanel },
  { id: "measurement", title: "Measurement", component: MeasurementPanel },
];

const components = Object.fromEntries(
  PANELS.map(({ id, component: Panel }) => [
    id,
    (() => (
      <Suspense fallback={<EmptyState title="Loading…" />}>
        <Panel />
      </Suspense>
    )) as FunctionComponent<IDockviewPanelProps>,
  ]),
);

function defaultLayout(api: DockviewApi) {
  api.clear();
  api.addPanel({ id: "stack", component: "stack", title: PANELS[0].title });
  let first = true;
  for (const panel of PANELS.slice(1)) {
    api.addPanel({
      id: panel.id,
      component: panel.id,
      title: panel.title,
      position: first
        ? { referencePanel: "stack", direction: "right" }
        : { referencePanel: "geometry", direction: "within" },
    });
    first = false;
  }
  api.getPanel("geometry")?.api.setActive();
  api.getPanel("stack")?.group.api.setSize({ width: 500 });
}

interface WorkspaceApi {
  openPanel: (id: string) => void;
  resetLayout: () => void;
}

const WorkspaceContext = createContext<WorkspaceApi>({ openPanel: () => {}, resetLayout: () => {} });
export const useWorkspace = () => useContext(WorkspaceContext);

export function WorkspaceProvider({
  children,
}: {
  children: (onReady: (e: DockviewReadyEvent) => void) => React.ReactNode;
}) {
  const [api, setApi] = useState<DockviewApi | null>(null);

  const onReady = (event: DockviewReadyEvent) => {
    const dock = event.api;
    setApi(dock);
    let restored = false;
    try {
      const saved = localStorage.getItem(LAYOUT_KEY);
      if (saved) {
        dock.fromJSON(JSON.parse(saved));
        restored = dock.panels.length > 0;
      }
    } catch {
      restored = false;
    }
    if (!restored) defaultLayout(dock);
    // Layouts saved before a panel existed get it as a tab next to the views.
    const anchor = dock.getPanel("geometry") ?? dock.panels.find((p) => p.id !== "stack");
    for (const p of PANELS) {
      if (dock.getPanel(p.id)) continue;
      dock.addPanel({
        id: p.id,
        component: p.id,
        title: p.title,
        inactive: true,
        position: anchor ? { referencePanel: anchor.id, direction: "within" } : undefined,
      });
    }
    // Saved layouts keep the titles they were saved with; show the current ones.
    for (const p of PANELS) dock.getPanel(p.id)?.api.setTitle(p.title);
    dock.onDidLayoutChange(() => {
      try {
        localStorage.setItem(LAYOUT_KEY, JSON.stringify(dock.toJSON()));
      } catch {
        // layout persistence is best-effort
      }
    });
  };

  const value: WorkspaceApi = {
    openPanel: (id) => {
      if (!api) return;
      const existing = api.getPanel(id);
      if (existing) return existing.api.setActive();
      const meta = PANELS.find((p) => p.id === id);
      if (!meta) return;
      const anchor = api.getPanel("geometry") ?? api.panels.find((p) => p.id !== "stack");
      api.addPanel({
        id,
        component: id,
        title: meta.title,
        position: anchor ? { referencePanel: anchor.id, direction: "within" } : undefined,
      });
    },
    resetLayout: () => api && defaultLayout(api),
  };

  return <WorkspaceContext.Provider value={value}>{children(onReady)}</WorkspaceContext.Provider>;
}

export function Workspace({ onReady }: { onReady: (e: DockviewReadyEvent) => void }) {
  const dark = useDark();
  return (
    <div className="masksim-dock h-full w-full">
      <DockviewReact components={components} onReady={onReady} theme={dark ? themeDark : themeLight} />
    </div>
  );
}
