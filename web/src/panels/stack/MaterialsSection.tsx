// Material library: optical constants (n − ik at the wavelength) and display colors of
// the materials the stack and pattern refer to, with where each one is used.
import { Add01Icon, Delete02Icon } from "@hugeicons/core-free-icons";
import { HugeiconsIcon } from "@hugeicons/react";
import type { CellEditRequestEvent, ColDef, ICellRendererParams } from "ag-grid-community";
import { useMemo, useState } from "react";
import type { MaterialDoc, Project } from "@/api/model";
import { Note } from "@/components/controls";
import { DataGrid } from "@/components/data-grid";
import { Button } from "@/components/ui/button";
import { fmt } from "@/lib/format";
import { materialUsage } from "@/lib/stack";
import { editProject, useProject } from "@/state/project";
import { useMaterialColors } from "../common";
import { SetupSection } from "./ui";

interface MaterialRow extends MaterialDoc {
  index: number;
  display: string;
  usedBy: string[];
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
        aria-label={`Display color of ${row.name}`}
        className="size-4 cursor-pointer rounded-sm border-0 bg-transparent p-0"
      />
    </label>
  );
}

export function MaterialsSection({ problems }: { problems: number }) {
  const project = useProject();
  const colors = useMaterialColors();
  const [selected, setSelected] = useState<number | null>(null);
  const usage = useMemo(() => materialUsage(project), [project]);
  const rows = useMemo<MaterialRow[]>(
    () =>
      project.materials.map((m, index) => ({ ...m, index, display: colors[index], usedBy: usage.get(m.name) ?? [] })),
    [project.materials, colors, usage],
  );
  const columns = useMemo<ColDef<MaterialRow>[]>(
    () => [
      { headerName: "", field: "display", width: 34, cellRenderer: ColorCell, sortable: false, resizable: false },
      { headerName: "Material", field: "name", editable: true, flex: 1.2, minWidth: 76 },
      {
        headerName: "n",
        field: "n",
        editable: true,
        flex: 1,
        minWidth: 64,
        cellEditor: "agNumberCellEditor",
        cellEditorParams: { precision: 8 },
        valueFormatter: (p) => fmt(p.value, 7),
      },
      {
        headerName: "k",
        field: "k",
        editable: true,
        flex: 1,
        minWidth: 64,
        cellEditor: "agNumberCellEditor",
        cellEditorParams: { min: 0, precision: 8 },
        valueFormatter: (p) => fmt(p.value, 7),
      },
      {
        headerName: "Used by",
        field: "usedBy",
        flex: 1.3,
        minWidth: 80,
        sortable: false,
        valueFormatter: (p) => (p.value as string[]).join(", "),
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
  const selectedRow = selected === null ? null : rows[selected];
  const remove = () => {
    if (!selectedRow || selectedRow.usedBy.length) return;
    editProject((d) => void d.materials.splice(selectedRow.index, 1));
    setSelected(null);
  };
  const inUse = rows.filter((r) => r.usedBy.length).length;

  return (
    <SetupSection
      id="materials"
      title="Materials"
      summary={`${rows.length} defined, ${inUse} in use`}
      problems={problems}
      actions={
        <>
          <Button size="sm" variant="ghost" onClick={add}>
            <HugeiconsIcon icon={Add01Icon} data-icon="inline-start" />
            Add
          </Button>
          <Button
            size="icon-sm"
            variant="ghost"
            onClick={remove}
            disabled={!selectedRow || selectedRow.usedBy.length > 0}
            title={
              !selectedRow
                ? "Select a material to delete it"
                : selectedRow.usedBy.length
                  ? `In use by ${selectedRow.usedBy.join(", ")}`
                  : `Delete ${selectedRow.name}`
            }
            aria-label="Delete the selected material"
          >
            <HugeiconsIcon icon={Delete02Icon} />
          </Button>
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
      <Note>
        Complex refractive index n − ik at λ = {fmt(project.illumination.wavelength_nm)} nm. The values don't follow the
        wavelength: update them when you change it. Double-click a cell to edit it.
      </Note>
    </SetupSection>
  );
}
