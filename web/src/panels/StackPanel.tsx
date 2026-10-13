// Stack editor: materials, layers (with repeat groups), pattern, illumination, numerics.
// Every edit goes through the project store, so it is undoable and the geometry and
// dielectric views follow immediately.
import {
  Add01Icon,
  Alert02Icon,
  ArrowDown01Icon,
  ArrowUp01Icon,
  Copy01Icon,
  Delete02Icon,
} from "@hugeicons/core-free-icons";
import { HugeiconsIcon } from "@hugeicons/react";
import type { CellEditRequestEvent, ColDef, ICellRendererParams, RowDragEndEvent } from "ag-grid-community";
import { type ReactNode, useMemo, useState } from "react";
import { isContactHoles, type LayerDoc, type MaterialDoc, PATTERN_KINDS, type Project } from "@/api/model";
import { FieldRow, Segmented, SelectField } from "@/components/controls";
import { DataGrid } from "@/components/data-grid";
import { Stat } from "@/components/layout";
import { NumberField } from "@/components/number-field";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Input } from "@/components/ui/input";
import { fixed, fmt } from "@/lib/format";
import { editProject, useProject } from "@/state/project";
import { useMaterialColors, useStack } from "./common";

export function StackPanel() {
  const { errors, requestError } = useStack();
  return (
    <div className="h-full overflow-auto bg-background">
      <div className="space-y-5 p-3">
        {(errors.length > 0 || requestError) && (
          <Alert variant="destructive">
            <HugeiconsIcon icon={Alert02Icon} />
            <AlertTitle>The stack can't be solved yet</AlertTitle>
            <AlertDescription>
              <ul className="list-inside list-disc">
                {(errors.length ? errors : [String(requestError)]).map((e) => (
                  <li key={e}>{e}</li>
                ))}
              </ul>
            </AlertDescription>
          </Alert>
        )}
        <ProjectName />
        <MaterialsSection />
        <LayersSection />
        <PatternSection />
        <IlluminationSection />
        <NumericsSection />
        <SummarySection />
      </div>
    </div>
  );
}

function Section({ title, actions, children }: { title: ReactNode; actions?: ReactNode; children: ReactNode }) {
  return (
    <section className="space-y-2">
      <div className="flex h-6 items-center gap-2">
        <h2 className="text-[11px] font-semibold tracking-wide text-muted-foreground uppercase">{title}</h2>
        <div className="ml-auto flex items-center gap-0.5">{actions}</div>
      </div>
      {children}
    </section>
  );
}

function IconButton({
  icon,
  label,
  onClick,
  disabled,
}: {
  icon: typeof Add01Icon;
  label: string;
  onClick: () => void;
  disabled?: boolean;
}) {
  return (
    <Button size="icon-sm" variant="ghost" onClick={onClick} disabled={disabled} title={label} aria-label={label}>
      <HugeiconsIcon icon={icon} />
    </Button>
  );
}

function ProjectName() {
  const project = useProject();
  return (
    <FieldRow label="Project">
      <Input
        value={project.name}
        onChange={(e) =>
          editProject((d) => {
            d.name = e.target.value;
          }, "name")
        }
        aria-label="Project name"
      />
    </FieldRow>
  );
}

// ---- materials ------------------------------------------------------------------------

interface MaterialRow extends MaterialDoc {
  index: number;
  display: string;
}

function renameMaterial(d: Project, index: number, name: string) {
  const old = d.materials[index].name;
  d.materials[index].name = name;
  for (const layer of d.layers) if (layer.material === old) layer.material = name;
  if (d.superstrate === old) d.superstrate = name;
  if (d.substrate === old) d.substrate = name;
  if (d.pattern.fill === old) d.pattern.fill = name;
}

function ColorCell(params: ICellRendererParams<MaterialRow>) {
  const row = params.data;
  if (!row) return null;
  return (
    <label className="flex h-full items-center" title="Display color">
      <input
        type="color"
        value={row.display.length === 7 ? row.display : "#888888"}
        onChange={(e) =>
          editProject((d) => {
            d.materials[row.index].color = e.target.value;
          }, `color:${row.index}`)
        }
        className="size-4 cursor-pointer rounded-sm border-0 bg-transparent p-0"
      />
    </label>
  );
}

function MaterialsSection() {
  const project = useProject();
  const colors = useMaterialColors();
  const [selected, setSelected] = useState<number | null>(null);
  const rows = useMemo<MaterialRow[]>(
    () => project.materials.map((m, index) => ({ ...m, index, display: colors[index] })),
    [project.materials, colors],
  );
  const columns = useMemo<ColDef<MaterialRow>[]>(
    () => [
      { headerName: "", field: "display", width: 34, cellRenderer: ColorCell, sortable: false, resizable: false },
      { headerName: "Material", field: "name", editable: true, flex: 1.3, minWidth: 80 },
      {
        headerName: "n",
        field: "n",
        editable: true,
        flex: 1,
        cellEditor: "agNumberCellEditor",
        cellEditorParams: { precision: 8 },
        valueFormatter: (p) => fmt(p.value, 7),
      },
      {
        headerName: "k",
        field: "k",
        editable: true,
        flex: 1,
        cellEditor: "agNumberCellEditor",
        cellEditorParams: { min: 0, precision: 8 },
        valueFormatter: (p) => fmt(p.value, 7),
      },
    ],
    [],
  );

  const onEdit = (event: CellEditRequestEvent<MaterialRow>) => {
    const index = event.data.index;
    const field = event.colDef.field as keyof MaterialDoc;
    const value = event.newValue;
    editProject((d) => {
      if (field === "name") renameMaterial(d, index, String(value ?? "").trim() || d.materials[index].name);
      else if (field === "n" || field === "k") {
        const number = Number(value);
        if (Number.isFinite(number)) d.materials[index][field] = number;
      }
    }, `material:${index}:${field}`);
  };

  const add = () =>
    editProject((d) => {
      let i = d.materials.length + 1;
      while (d.materials.some((m) => m.name === `Material ${i}`)) i++;
      d.materials.push({ name: `Material ${i}`, n: 1, k: 0, color: null });
    });
  const remove = () => {
    if (selected === null) return;
    editProject((d) => void d.materials.splice(selected, 1));
    setSelected(null);
  };

  return (
    <Section
      title="Materials (n − ik at the wavelength)"
      actions={
        <>
          <IconButton icon={Add01Icon} label="Add material" onClick={add} />
          <IconButton
            icon={Delete02Icon}
            label="Delete selected material"
            onClick={remove}
            disabled={selected === null}
          />
        </>
      }
    >
      <DataGrid<MaterialRow>
        rowData={rows}
        columnDefs={columns}
        domLayout="autoHeight"
        readOnlyEdit
        onCellEditRequest={onEdit}
        getRowId={(p) => String(p.data.index)}
        rowSelection={{ mode: "singleRow", checkboxes: false, enableClickSelection: true }}
        onSelectionChanged={(e) => setSelected(e.api.getSelectedRows()[0]?.index ?? null)}
      />
      <div className="grid grid-cols-2 gap-2">
        <FieldRow label="Incident" hint="Medium the light arrives from">
          <SelectField
            value={project.superstrate}
            onChange={(v) =>
              editProject((d) => {
                d.superstrate = v;
              })
            }
            options={project.materials.map((m) => ({ value: m.name, label: m.name }))}
          />
        </FieldRow>
        <FieldRow label="Substrate">
          <SelectField
            value={project.substrate}
            onChange={(v) =>
              editProject((d) => {
                d.substrate = v;
              })
            }
            options={project.materials.map((m) => ({ value: m.name, label: m.name }))}
          />
        </FieldRow>
      </div>
    </Section>
  );
}

// ---- layers --------------------------------------------------------------------------------

interface LayerRow extends LayerDoc {
  index: number;
}

const NEW_LAYER: LayerDoc = {
  name: "Layer",
  material: "",
  thickness_nm: 10,
  patterned: false,
  swa_deg: 90,
  steps: 1,
  group: "",
};

function LayersSection() {
  const project = useProject();
  const [selected, setSelected] = useState<number | null>(null);
  const rows = useMemo<LayerRow[]>(() => project.layers.map((l, index) => ({ ...l, index })), [project.layers]);
  const materialNames = useMemo(() => project.materials.map((m) => m.name), [project.materials]);
  const columns = useMemo<ColDef<LayerRow>[]>(
    () => [
      { headerName: "", rowDrag: true, width: 26, sortable: false, resizable: false },
      { headerName: "Layer", field: "name", editable: true, flex: 1.2, minWidth: 64 },
      {
        headerName: "Material",
        field: "material",
        editable: true,
        flex: 1.1,
        minWidth: 64,
        cellEditor: "agSelectCellEditor",
        cellEditorParams: { values: materialNames },
      },
      {
        headerName: "t (nm)",
        field: "thickness_nm",
        editable: true,
        width: 62,
        cellEditor: "agNumberCellEditor",
        cellEditorParams: { min: 0, precision: 4 },
        valueFormatter: (p) => fmt(p.value, 6),
      },
      {
        headerName: "Pat.",
        field: "patterned",
        editable: true,
        width: 50,
        cellRenderer: "agCheckboxCellRenderer",
        cellEditor: "agCheckboxCellEditor",
        headerTooltip: "Apply the lateral pattern to this layer",
      },
      {
        headerName: "SWA°",
        field: "swa_deg",
        editable: (p) => !!p.data?.patterned,
        width: 56,
        cellEditor: "agNumberCellEditor",
        cellEditorParams: { min: 1, max: 179, precision: 3 },
        headerTooltip: "Sidewall angle of the layer material; < 90° widens it with depth",
        cellClass: (p) => (p.data?.patterned ? "" : "text-muted-foreground"),
      },
      {
        headerName: "Steps",
        field: "steps",
        editable: (p) => !!p.data?.patterned && p.data.swa_deg !== 90,
        width: 52,
        cellEditor: "agNumberCellEditor",
        cellEditorParams: { min: 1, max: 50, precision: 0 },
        headerTooltip: "Staircase slices for a non-vertical sidewall",
        cellClass: (p) => (p.data?.patterned && p.data.swa_deg !== 90 ? "" : "text-muted-foreground"),
      },
      {
        headerName: "Group",
        field: "group",
        editable: true,
        flex: 1,
        minWidth: 52,
        headerTooltip: "Contiguous rows with the same group repeat together (e.g. a Mo/Si pair)",
      },
    ],
    [materialNames],
  );

  const onEdit = (event: CellEditRequestEvent<LayerRow>) => {
    const index = event.data.index;
    const field = event.colDef.field as keyof LayerDoc;
    const value = event.newValue;
    editProject((d) => {
      const layer = d.layers[index];
      if (field === "name" || field === "material" || field === "group") layer[field] = String(value ?? "").trim();
      else if (field === "patterned") layer.patterned = !!value;
      else {
        const number = Number(value);
        if (!Number.isFinite(number)) return;
        if (field === "steps") layer.steps = Math.max(1, Math.round(number));
        else layer[field] = number;
      }
    }, `layer:${index}:${field}`);
  };

  const onDragEnd = (event: RowDragEndEvent<LayerRow>) => {
    const order: number[] = [];
    event.api.forEachNode((node) => node.data && order.push(node.data.index));
    if (order.every((v, i) => v === i)) return;
    editProject((d) => {
      d.layers = order.map((i) => d.layers[i]);
    });
    setSelected(null);
  };

  const insert = (layer: LayerDoc) =>
    editProject((d) => {
      const at = selected === null ? d.layers.length : selected + 1;
      d.layers.splice(at, 0, layer);
    });
  const move = (delta: number) => {
    if (selected === null) return;
    const target = selected + delta;
    if (target < 0 || target >= project.layers.length) return;
    editProject((d) => {
      const [layer] = d.layers.splice(selected, 1);
      d.layers.splice(target, 0, layer);
    });
    setSelected(target);
  };

  const groups = useMemo(
    () => [...new Set(project.layers.map((l) => l.group.trim()).filter(Boolean))],
    [project.layers],
  );

  return (
    <Section
      title="Layers (incident side first)"
      actions={
        <>
          <IconButton
            icon={Add01Icon}
            label="Add layer below the selection"
            onClick={() =>
              insert({ ...NEW_LAYER, material: project.materials[1]?.name ?? project.materials[0]?.name ?? "" })
            }
          />
          <IconButton
            icon={Copy01Icon}
            label="Duplicate selected layer"
            onClick={() => selected !== null && insert({ ...project.layers[selected] })}
            disabled={selected === null}
          />
          <IconButton
            icon={ArrowUp01Icon}
            label="Move up"
            onClick={() => move(-1)}
            disabled={selected === null || selected === 0}
          />
          <IconButton
            icon={ArrowDown01Icon}
            label="Move down"
            onClick={() => move(1)}
            disabled={selected === null || selected === project.layers.length - 1}
          />
          <IconButton
            icon={Delete02Icon}
            label="Delete selected layer"
            onClick={() => {
              if (selected === null) return;
              editProject((d) => void d.layers.splice(selected, 1));
              setSelected(null);
            }}
            disabled={selected === null}
          />
        </>
      }
    >
      <DataGrid<LayerRow>
        rowData={rows}
        columnDefs={columns}
        domLayout="autoHeight"
        readOnlyEdit
        onCellEditRequest={onEdit}
        rowDragManaged
        onRowDragEnd={onDragEnd}
        getRowId={(p) => String(p.data.index)}
        rowSelection={{ mode: "singleRow", checkboxes: false, enableClickSelection: true }}
        onSelectionChanged={(e) => setSelected(e.api.getSelectedRows()[0]?.index ?? null)}
      />
      {groups.length > 0 && (
        <div className="grid grid-cols-2 gap-2">
          {groups.map((group) => (
            <FieldRow key={group} label={`Repeat “${group}”`} hint="How many times the group's rows repeat as a block">
              <NumberField
                value={project.repeats[group] ?? 1}
                onChange={(v) =>
                  editProject((d) => {
                    d.repeats[group] = Math.max(1, Math.round(v));
                  }, `repeat:${group}`)
                }
                min={1}
                max={1000}
                unit="×"
                digits={0}
              />
            </FieldRow>
          ))}
        </div>
      )}
    </Section>
  );
}

// ---- pattern, illumination, numerics ---------------------------------------------------

function PatternSection() {
  const project = useProject();
  const p = project.pattern;
  const ch = isContactHoles(p.kind);
  const set = <K extends keyof Project["pattern"]>(field: K, value: Project["pattern"][K]) =>
    editProject((d) => {
      d.pattern[field] = value;
    }, `pattern:${field}`);
  return (
    <Section title="Pattern (applied to every patterned layer)">
      <div className="space-y-2">
        <FieldRow label="Type">
          <SelectField value={p.kind} onChange={(v) => set("kind", v)} options={PATTERN_KINDS} />
        </FieldRow>
        {p.kind !== "none" && (
          <>
            {ch ? (
              <div className="grid grid-cols-2 gap-2">
                <FieldRow label="Pitch x">
                  <NumberField value={p.pitch_x_nm} onChange={(v) => set("pitch_x_nm", v)} min={1} unit="nm" />
                </FieldRow>
                <FieldRow label={p.kind === "ch_staggered" ? "Row spacing" : "Pitch y"}>
                  <NumberField value={p.pitch_y_nm} onChange={(v) => set("pitch_y_nm", v)} min={1} unit="nm" />
                </FieldRow>
                <FieldRow label="CD x">
                  <NumberField value={p.cd_x_nm} onChange={(v) => set("cd_x_nm", v)} min={0} step={0.5} unit="nm" />
                </FieldRow>
                <FieldRow label="CD y">
                  <NumberField value={p.cd_y_nm} onChange={(v) => set("cd_y_nm", v)} min={0} step={0.5} unit="nm" />
                </FieldRow>
                <FieldRow label="Shape">
                  <Segmented
                    value={p.hole_shape}
                    onChange={(v) => set("hole_shape", v)}
                    options={[
                      { value: "rect", label: "Rect" },
                      { value: "ellipse", label: "Ellipse" },
                    ]}
                  />
                </FieldRow>
                <FieldRow label="Tone" hint="holes: CD is the opening; pillars: CD is the island">
                  <Segmented
                    value={p.tone}
                    onChange={(v) => set("tone", v)}
                    options={[
                      { value: "holes", label: "Holes" },
                      { value: "pillars", label: "Pillars" },
                    ]}
                  />
                </FieldRow>
              </div>
            ) : (
              <div className="grid grid-cols-2 gap-2">
                <FieldRow label="Pitch">
                  <NumberField value={p.pitch_x_nm} onChange={(v) => set("pitch_x_nm", v)} min={1} unit="nm" />
                </FieldRow>
                <FieldRow label="Line CD" hint="Width of the layer material (e.g. the absorber line)">
                  <NumberField value={p.cd_x_nm} onChange={(v) => set("cd_x_nm", v)} min={0} step={0.5} unit="nm" />
                </FieldRow>
              </div>
            )}
            <div className="grid grid-cols-2 gap-2">
              <FieldRow label="Space material">
                <SelectField
                  value={p.fill}
                  onChange={(v) => set("fill", v)}
                  options={project.materials.map((m) => ({ value: m.name, label: m.name }))}
                />
              </FieldRow>
              <FieldRow label="CD defined at" hint="Depth where the CD applies; sidewall angles set it elsewhere">
                <SelectField
                  value={p.cd_reference}
                  onChange={(v) => set("cd_reference", v)}
                  options={[
                    { value: "top", label: "Top" },
                    { value: "middle", label: "Middle" },
                    { value: "bottom", label: "Bottom" },
                  ]}
                />
              </FieldRow>
            </div>
          </>
        )}
      </div>
    </Section>
  );
}

function IlluminationSection() {
  const { illumination: ill } = useProject();
  const set = <K extends keyof Project["illumination"]>(field: K, value: Project["illumination"][K]) =>
    editProject((d) => {
      d.illumination[field] = value;
    }, `illumination:${field}`);
  return (
    <Section title="Illumination">
      <div className="grid grid-cols-2 gap-2">
        <FieldRow label="Wavelength λ">
          <NumberField
            value={ill.wavelength_nm}
            onChange={(v) => set("wavelength_nm", v)}
            min={0.01}
            step={0.1}
            unit="nm"
          />
        </FieldRow>
        <FieldRow label="Polarization" hint="TE: E perpendicular to the plane of incidence">
          <Segmented
            value={ill.polarization}
            onChange={(v) => set("polarization", v)}
            options={[
              { value: "TE", label: "TE" },
              { value: "TM", label: "TM" },
              { value: "TE+TM", label: "Both" },
            ]}
          />
        </FieldRow>
        <FieldRow label="Incidence θ">
          <NumberField
            value={ill.theta_deg}
            onChange={(v) => set("theta_deg", v)}
            min={0}
            max={89}
            step={0.5}
            unit="°"
          />
        </FieldRow>
        <FieldRow label="Azimuth φ" hint="0 puts the plane of incidence in x–z (across vertical lines)">
          <NumberField value={ill.phi_deg} onChange={(v) => set("phi_deg", v)} min={-180} max={180} step={1} unit="°" />
        </FieldRow>
      </div>
    </Section>
  );
}

function NumericsSection() {
  const { numerics: num, pattern } = useProject();
  const set = <K extends keyof Project["numerics"]>(field: K, value: number) =>
    editProject((d) => {
      d.numerics[field] = Math.max(0, Math.round(value));
    }, `numerics:${field}`);
  const ch = isContactHoles(pattern.kind);
  return (
    <Section title="Numerics">
      <div className="grid grid-cols-2 gap-2">
        <FieldRow label={ch ? "Harmonics Nx" : "Harmonics N"} hint="Orders −N…N along the periodic axis">
          <NumberField value={num.nx} onChange={(v) => set("nx", v)} min={0} max={80} digits={0} />
        </FieldRow>
        {ch && (
          <FieldRow label="Harmonics Ny">
            <NumberField value={num.ny} onChange={(v) => set("ny", v)} min={0} max={40} digits={0} />
          </FieldRow>
        )}
        <FieldRow label="Grid samples" hint="Real-space samples per period for the Fourier transform; 0 = automatic">
          <NumberField value={num.grid} onChange={(v) => set("grid", v)} min={0} max={8192} step={64} digits={0} />
        </FieldRow>
      </div>
    </Section>
  );
}

// ---- summary and slices ----------------------------------------------------------------------

function SummarySection() {
  const { summary, slices } = useStack();
  const [open, setOpen] = useState(false);
  const columns = useMemo<ColDef[]>(
    () => [
      { headerName: "Slice", field: "label", flex: 1.4, minWidth: 90 },
      { headerName: "Material", field: "material", flex: 1 },
      { headerName: "Space", field: "fill", flex: 1, valueFormatter: (p) => (p.data.patterned ? p.value : "") },
      { headerName: "z top", field: "z_top_nm", width: 70, valueFormatter: (p) => fixed(p.value, 2) },
      { headerName: "t", field: "thickness_nm", width: 62, valueFormatter: (p) => fixed(p.value, 3) },
      { headerName: "CD x", field: "cd_x_nm", width: 64, valueFormatter: (p) => fixed(p.value, 2) },
      { headerName: "CD y", field: "cd_y_nm", width: 64, valueFormatter: (p) => fixed(p.value, 2) },
    ],
    [],
  );
  if (!summary) return null;
  const [Lx, Ly] = summary.unit_cell_nm;
  return (
    <Section title="What the solver receives">
      <div className="grid grid-cols-3 gap-2">
        <Stat label="Total thickness" value={`${fixed(summary.total_thickness_nm, 1)} nm`} />
        <Stat label="RCWA slices" value={summary.slice_count} hint={`${summary.patterned_slice_count} patterned`} />
        <Stat
          label="Unit cell"
          value={summary.periodic_axes === "xy" ? `${fixed(Lx, 0)} × ${fixed(Ly, 0)} nm` : `${fixed(Lx, 0)} nm`}
          hint={summary.periodic_axes === "none" ? "unpatterned" : `periodic in ${summary.periodic_axes}`}
        />
        <Stat label="Harmonics" value={summary.harmonics} hint={`matrices ${summary.matrix_size}²`} />
        <Stat label="Grid" value={`${summary.grid[0]} × ${summary.grid[1]}`} />
        <Stat label="Polarizations" value={summary.polarizations.join(" + ")} />
      </div>
      <Collapsible open={open} onOpenChange={setOpen}>
        <CollapsibleTrigger render={<Button variant="ghost" size="sm" className="-ml-2" />}>
          {open ? "Hide" : "Show"} slice table ({slices.length})
        </CollapsibleTrigger>
        <CollapsibleContent>
          <DataGrid rowData={slices} columnDefs={columns} className="h-64" />
        </CollapsibleContent>
      </Collapsible>
    </Section>
  );
}
