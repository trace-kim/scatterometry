// The layer stack drawn the way it is built: the incident medium on top, the films in
// order (repeat groups bracketed with their count), and the substrate below. Fields edit
// in place; each row's menu inserts, moves, groups, and deletes layers.
import {
  Add01Icon,
  ArrowDown01Icon,
  ArrowUp01Icon,
  Copy01Icon,
  Delete02Icon,
  InsertRowDownIcon,
  InsertRowUpIcon,
  MoreHorizontalIcon,
  RepeatIcon,
  UngroupIcon,
  WavesArrowDownIcon,
} from "@hugeicons/core-free-icons";
import { HugeiconsIcon } from "@hugeicons/react";
import type { ColDef } from "ag-grid-community";
import { type ReactNode, useMemo, useState } from "react";
import type { LayerDoc, Project } from "@/api/model";
import { type Option, SelectField } from "@/components/controls";
import { DataGrid } from "@/components/data-grid";
import { NumberField } from "@/components/number-field";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Toggle } from "@/components/ui/toggle";
import { fixed } from "@/lib/format";
import {
  adjacentGroup,
  blockOf,
  blockThickness,
  canMoveLayer,
  deleteLayer,
  insertLayer,
  joinGroup,
  type LayerBlock,
  layerBlocks,
  leaveGroup,
  moveBlock,
  moveLayer,
  newGroup,
  renameGroup,
  totalThickness,
  ungroup,
} from "@/lib/stack";
import { cn } from "@/lib/utils";
import { editProject, useProject } from "@/state/project";
import { useMaterialColors, useStack } from "../common";
import { CommitInput, PatternGlyph, SetupSection, Swatch } from "./ui";

// Swatch, name, material, thickness, patterned toggle, menu: shared by every row so the
// columns line up across groups and the two media.
const ROW = "grid grid-cols-[0.875rem_minmax(0,1fr)_6.5rem_5.75rem_1.75rem_1.5rem] items-center gap-x-1.5";

function uniqueName(base: string, taken: string[]): string {
  if (!taken.includes(base)) return base;
  const stem = base.replace(/ \d+$/, "");
  let i = 2;
  while (taken.includes(`${stem} ${i}`)) i++;
  return `${stem} ${i}`;
}

function blankLayer(project: Project, material: string): LayerDoc {
  return {
    name: uniqueName(
      "Layer",
      project.layers.map((l) => l.name),
    ),
    material,
    thickness_nm: 10,
    patterned: false,
    swa_deg: 90,
    steps: 1,
    group: "",
  };
}

export function LayersSection({ problems }: { problems: number }) {
  const project = useProject();
  const colors = useMaterialColors();
  const blocks = useMemo(() => layerBlocks(project), [project]);
  const materials = useMemo<Option<string>[]>(
    () => project.materials.map((m, i) => ({ value: m.name, label: m.name, icon: <Swatch color={colors[i]} /> })),
    [project.materials, colors],
  );
  const colorOf = (name: string) => colors[project.materials.findIndex((m) => m.name === name)] ?? "transparent";
  const count = project.layers.length;

  const addLayer = () =>
    editProject((d) => {
      const material =
        d.layers[d.layers.length - 1]?.material ?? d.materials.find((m) => m.n !== 1)?.name ?? d.materials[0]?.name;
      d.layers.push(blankLayer(d, material ?? ""));
    });

  const row = (index: number) => (
    <LayerRow key={index} index={index} materials={materials} color={colorOf(project.layers[index].material)} />
  );

  return (
    <SetupSection
      id="stack"
      title="Layer stack"
      summary={`${count} ${count === 1 ? "layer" : "layers"}, ${fixed(totalThickness(project), 1)} nm`}
      problems={problems}
      actions={
        <Button size="sm" variant="ghost" onClick={addLayer} title="Add a layer at the bottom of the stack">
          <HugeiconsIcon icon={Add01Icon} data-icon="inline-start" />
          Add layer
        </Button>
      }
    >
      <div className="-mx-1">
        <MediumRow
          medium="superstrate"
          materials={materials}
          icon={<HugeiconsIcon icon={WavesArrowDownIcon} className="size-3.5 text-muted-foreground" />}
        />
        {blocks.map((block, bi) =>
          block.group ? (
            <GroupBlock key={`${block.group}@${block.start}`} block={block} index={bi} last={bi === blocks.length - 1}>
              {Array.from({ length: block.end - block.start }, (_, i) => row(block.start + i))}
            </GroupBlock>
          ) : (
            row(block.start)
          ),
        )}
        <MediumRow
          medium="substrate"
          materials={materials}
          icon={<Swatch color={colorOf(project.substrate)} hatched className="size-3" />}
        />
      </div>
      <SolverSlices />
    </SetupSection>
  );
}

/** Incident medium or substrate: semi-infinite, so only the material is set. */
function MediumRow({
  medium,
  materials,
  icon,
}: {
  medium: "superstrate" | "substrate";
  materials: Option<string>[];
  icon: ReactNode;
}) {
  const project = useProject();
  const label = medium === "superstrate" ? "Incident medium" : "Substrate";
  return (
    <div
      className={cn(ROW, "h-8 px-1")}
      title={
        medium === "superstrate"
          ? "Semi-infinite medium the light arrives from"
          : "Semi-infinite medium below the last layer"
      }
    >
      <span className="flex justify-center">{icon}</span>
      <span className="truncate px-1.5 text-xs text-muted-foreground">{label}</span>
      <SelectField
        value={project[medium]}
        options={materials}
        onChange={(v) =>
          editProject((d) => {
            d[medium] = v;
          })
        }
        aria-label={label}
      />
      <span className="text-center text-sm text-muted-foreground" title="Semi-infinite">
        ∞
      </span>
    </div>
  );
}

function LayerRow({ index, materials, color }: { index: number; materials: Option<string>[]; color: string }) {
  const project = useProject();
  const layer = project.layers[index];
  const kind = project.pattern.kind;
  const label = layer.name || `layer ${index + 1}`;
  const set = <K extends keyof LayerDoc>(field: K, value: LayerDoc[K]) =>
    editProject((d) => {
      d.layers[index][field] = value;
    }, `layer:${index}:${field}`);

  return (
    <div className="rounded-md px-1 hover:bg-muted/40 has-[:focus-visible]:bg-muted/40">
      <div className={cn(ROW, "h-8")}>
        <span className="flex justify-center">
          <Swatch color={color} />
        </span>
        <CommitInput
          value={layer.name}
          onCommit={(name) => set("name", name.trim() || layer.name)}
          aria-label={`Name of ${label}`}
          className="font-medium"
        />
        <SelectField
          value={layer.material}
          options={materials}
          onChange={(v) => set("material", v)}
          aria-label={`Material of ${label}`}
        />
        <NumberField
          value={layer.thickness_nm}
          onChange={(v) => set("thickness_nm", v)}
          min={0}
          step={1}
          smallStep={0.1}
          digits={4}
          unit="nm"
          aria-label={`Thickness of ${label}`}
        />
        <Toggle
          pressed={layer.patterned}
          onPressedChange={(patterned) => set("patterned", patterned)}
          disabled={kind === "none"}
          aria-label={`Etch the pattern into ${label}`}
          title={
            kind === "none"
              ? "Choose a pattern type to etch it into layers"
              : layer.patterned
                ? "Patterned: the pattern is etched into this layer"
                : "Not patterned: click to etch the pattern into this layer"
          }
          className="size-7 min-w-0 px-0 text-muted-foreground/60 hover:text-foreground aria-pressed:bg-primary aria-pressed:text-primary-foreground hover:aria-pressed:bg-primary/85 hover:aria-pressed:text-primary-foreground"
        >
          <PatternGlyph kind={kind === "none" ? "ls_v" : kind} />
        </Toggle>
        <LayerMenu index={index} label={label} />
      </div>
      {layer.patterned && kind !== "none" && <Sidewall index={index} label={label} />}
    </div>
  );
}

function Sidewall({ index, label }: { index: number; label: string }) {
  const layer = useProject().layers[index];
  const set = (field: "swa_deg" | "steps", value: number) =>
    editProject((d) => {
      d.layers[index][field] = field === "steps" ? Math.max(1, Math.round(value)) : value;
    }, `layer:${index}:${field}`);
  return (
    <div
      className="flex items-center gap-1.5 pb-1.5 pl-5 text-[11px] text-muted-foreground"
      title="90° is vertical; below 90° the layer widens with depth. A sloped wall is cut into a staircase of slices."
    >
      <span>Sidewall</span>
      <NumberField
        className="w-[4.75rem]"
        value={layer.swa_deg}
        onChange={(v) => set("swa_deg", v)}
        min={1}
        max={179}
        step={0.5}
        digits={3}
        unit="°"
        aria-label={`Sidewall angle of ${label}`}
      />
      {layer.swa_deg === 90 ? (
        <span>vertical</span>
      ) : (
        <>
          <span>in</span>
          <NumberField
            className="w-14"
            value={layer.steps}
            onChange={(v) => set("steps", v)}
            min={1}
            max={50}
            digits={0}
            aria-label={`Slices for the sidewall of ${label}`}
          />
          <span>{layer.steps === 1 ? "slice" : "slices"}</span>
        </>
      )}
    </div>
  );
}

function LayerMenu({ index, label }: { index: number; label: string }) {
  const project = useProject();
  const blocks = layerBlocks(project);
  const block = blocks[blockOf(blocks, index)];
  const above = adjacentGroup(project, index, -1);
  const below = adjacentGroup(project, index, 1);
  const material = project.layers[index].material;
  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        render={
          <Button
            size="icon-sm"
            variant="ghost"
            aria-label={`More actions for ${label}`}
            className="text-muted-foreground"
          />
        }
      >
        <HugeiconsIcon icon={MoreHorizontalIcon} />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-56">
        <DropdownMenuItem onClick={() => editProject((d) => insertLayer(d, index, "above", blankLayer(d, material)))}>
          <HugeiconsIcon icon={InsertRowUpIcon} />
          Insert layer above
        </DropdownMenuItem>
        <DropdownMenuItem onClick={() => editProject((d) => insertLayer(d, index, "below", blankLayer(d, material)))}>
          <HugeiconsIcon icon={InsertRowDownIcon} />
          Insert layer below
        </DropdownMenuItem>
        <DropdownMenuItem
          onClick={() =>
            editProject((d) => {
              const copy = {
                ...d.layers[index],
                name: uniqueName(
                  d.layers[index].name,
                  d.layers.map((l) => l.name),
                ),
              };
              insertLayer(d, index, "below", copy);
            })
          }
        >
          <HugeiconsIcon icon={Copy01Icon} />
          Duplicate
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem
          disabled={!canMoveLayer(project, index, -1)}
          onClick={() => editProject((d) => moveLayer(d, index, -1))}
        >
          <HugeiconsIcon icon={ArrowUp01Icon} />
          Move up
        </DropdownMenuItem>
        <DropdownMenuItem
          disabled={!canMoveLayer(project, index, 1)}
          onClick={() => editProject((d) => moveLayer(d, index, 1))}
        >
          <HugeiconsIcon icon={ArrowDown01Icon} />
          Move down
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        {block?.group ? (
          <DropdownMenuItem onClick={() => editProject((d) => leaveGroup(d, index))}>
            <HugeiconsIcon icon={UngroupIcon} />
            Take out of “{block.group}”
          </DropdownMenuItem>
        ) : (
          <>
            <DropdownMenuItem onClick={() => editProject((d) => void newGroup(d, index))}>
              <HugeiconsIcon icon={RepeatIcon} />
              Repeat this layer
            </DropdownMenuItem>
            {above && (
              <DropdownMenuItem inset onClick={() => editProject((d) => joinGroup(d, index, -1))}>
                Add to “{above}” above
              </DropdownMenuItem>
            )}
            {below && (
              <DropdownMenuItem inset onClick={() => editProject((d) => joinGroup(d, index, 1))}>
                Add to “{below}” below
              </DropdownMenuItem>
            )}
          </>
        )}
        <DropdownMenuSeparator />
        <DropdownMenuItem
          variant="destructive"
          disabled={project.layers.length < 2}
          onClick={() => editProject((d) => deleteLayer(d, index))}
        >
          <HugeiconsIcon icon={Delete02Icon} />
          Delete layer
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

/** Rows of a repeat group inside a bracket, under a header with the group's repeat count. */
function GroupBlock({
  block,
  index,
  last,
  children,
}: {
  block: LayerBlock;
  index: number;
  last: boolean;
  children: ReactNode;
}) {
  const project = useProject();
  const period = blockThickness(project.layers, block);
  return (
    <div className="relative my-1 pl-3">
      <div
        aria-hidden
        className="pointer-events-none absolute top-2 bottom-2 left-1 w-1.5 rounded-l-[3px] border-y-[1.5px] border-l-[1.5px] border-muted-foreground/40"
      />
      <div className="flex h-8 items-center gap-1.5 px-1 text-xs">
        <HugeiconsIcon icon={RepeatIcon} className="size-3.5 shrink-0 text-muted-foreground" />
        <CommitInput
          value={block.group}
          onCommit={(name) => editProject((d) => renameGroup(d, block.start, name))}
          aria-label={`Name of the repeat group ${block.group}`}
          title="Repeat group: its layers repeat together as a block"
          className="field-sizing-content w-auto max-w-36 min-w-10 font-medium"
        />
        <span className="text-muted-foreground">×</span>
        <NumberField
          className="w-16"
          value={block.count}
          onChange={(v) =>
            editProject((d) => {
              d.repeats[block.group] = Math.max(1, Math.round(v));
            }, `repeat:${block.group}`)
          }
          min={1}
          max={1000}
          digits={0}
          aria-label={`Repetitions of ${block.group}`}
        />
        <span
          className="ml-auto text-muted-foreground tabular-nums"
          title={`${block.count} × ${fixed(period, 2)} nm per repetition`}
        >
          {fixed(block.count * period, 1)} nm
        </span>
        <DropdownMenu>
          <DropdownMenuTrigger
            render={
              <Button
                size="icon-sm"
                variant="ghost"
                aria-label={`More actions for the group ${block.group}`}
                className="text-muted-foreground"
              />
            }
          >
            <HugeiconsIcon icon={MoreHorizontalIcon} />
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-56">
            <DropdownMenuItem disabled={index === 0} onClick={() => editProject((d) => moveBlock(d, block.start, -1))}>
              <HugeiconsIcon icon={ArrowUp01Icon} />
              Move group up
            </DropdownMenuItem>
            <DropdownMenuItem disabled={last} onClick={() => editProject((d) => moveBlock(d, block.start, 1))}>
              <HugeiconsIcon icon={ArrowDown01Icon} />
              Move group down
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem onClick={() => editProject((d) => ungroup(d, block.start))}>
              <HugeiconsIcon icon={UngroupIcon} />
              Ungroup (keep one copy)
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
      {children}
    </div>
  );
}

/** How many slices the solver gets, with the slice table on demand. */
function SolverSlices() {
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
  const patterned = summary.patterned_slice_count;
  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2 text-[11px] text-muted-foreground">
        <span>
          The solver sees {summary.slice_count} {summary.slice_count === 1 ? "slice" : "slices"}
          {patterned > 0 && `, ${patterned} of them patterned`}.
        </span>
        <Button variant="link" size="xs" className="h-auto px-0 text-[11px]" onClick={() => setOpen(!open)}>
          {open ? "Hide slices" : "Show slices"}
        </Button>
      </div>
      {open && <DataGrid rowData={slices} columnDefs={columns} className="h-64" />}
    </div>
  );
}
