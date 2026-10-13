// The lateral pattern etched into the patterned layers: its type (picked by pictogram),
// pitch and CD, the material filling the openings, and where the CD is measured.
import { useMemo } from "react";
import { isContactHoles, PATTERN_KINDS, type PatternDoc, type PatternKind } from "@/api/model";
import { Note, type Option, Segmented, SelectField, StackedField } from "@/components/controls";
import { NumberField } from "@/components/number-field";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { fmt } from "@/lib/format";
import { unitCell } from "@/lib/stack";
import { editProject, useProject } from "@/state/project";
import { useMaterialColors } from "../common";
import { PatternGlyph, SetupSection, Swatch } from "./ui";

const KIND_NAMES: Record<PatternKind, string> = {
  none: "Blank",
  ls_v: "Vertical lines",
  ls_h: "Horizontal lines",
  ch_square: "Square array",
  ch_staggered: "Staggered array",
};

export function patternSummary(p: PatternDoc): string {
  if (p.kind === "none") return "Blank, no pattern";
  const name = KIND_NAMES[p.kind];
  if (!isContactHoles(p.kind)) return `${name}, CD ${fmt(p.cd_x_nm)} / pitch ${fmt(p.pitch_x_nm)} nm`;
  const what = p.tone === "holes" ? "holes" : "pillars";
  return `${name} of ${what}, ${fmt(p.cd_x_nm)}×${fmt(p.cd_y_nm)} / ${fmt(p.pitch_x_nm)}×${fmt(p.pitch_y_nm)} nm`;
}

export function PatternSection({ problems }: { problems: number }) {
  const project = useProject();
  const colors = useMaterialColors();
  const p = project.pattern;
  const ch = isContactHoles(p.kind);
  const etched = project.layers.filter((l) => l.patterned);
  const sloped = etched.some((l) => l.swa_deg !== 90);
  const materials = useMemo<Option<string>[]>(
    () => project.materials.map((m, i) => ({ value: m.name, label: m.name, icon: <Swatch color={colors[i]} /> })),
    [project.materials, colors],
  );
  const set = <K extends keyof PatternDoc>(field: K, value: PatternDoc[K]) =>
    editProject((d) => {
      d.pattern[field] = value;
    }, `pattern:${field}`);

  const length = (
    field: "pitch_x_nm" | "pitch_y_nm" | "cd_x_nm" | "cd_y_nm",
    label: string,
    hint?: string,
    min = 1,
  ) => (
    <StackedField label={label} hint={hint}>
      <NumberField
        value={p[field]}
        onChange={(v) => set(field, v)}
        min={min}
        step={min === 0 ? 0.5 : 1}
        unit="nm"
        aria-label={label}
      />
    </StackedField>
  );
  const fillLabel = !ch ? "Spaces filled with" : p.tone === "holes" ? "Holes filled with" : "Pillars surrounded by";
  const [Lx, Ly] = unitCell(p);
  const shape = p.tone === "holes" ? "Hole" : "Pillar";

  return (
    <SetupSection
      id="pattern"
      title="Pattern"
      summary={patternSummary(p)}
      problems={problems}
      warning={p.kind !== "none" && etched.length === 0 ? "no layer patterned" : null}
    >
      <div className="flex items-center gap-2.5">
        <ToggleGroup
          value={[p.kind]}
          onValueChange={(next) => {
            if (next.length) set("kind", next[0] as PatternKind);
          }}
          variant="outline"
          spacing={0}
          aria-label="Pattern type"
        >
          {PATTERN_KINDS.map((k) => (
            <ToggleGroupItem
              key={k.value}
              value={k.value}
              aria-label={k.label}
              title={k.label}
              className="h-8 w-9 px-0 text-muted-foreground aria-pressed:bg-primary aria-pressed:text-primary-foreground hover:aria-pressed:bg-primary/85"
            >
              <PatternGlyph kind={k.value} className="size-[18px]" />
            </ToggleGroupItem>
          ))}
        </ToggleGroup>
        <span className="min-w-0 truncate text-xs font-medium">
          {PATTERN_KINDS.find((k) => k.value === p.kind)?.label}
        </span>
      </div>

      {p.kind === "none" ? (
        <Note>Every layer is a uniform film, so the stack reflects like a thin-film coating.</Note>
      ) : (
        <>
          {ch ? (
            <div className="grid grid-cols-3 gap-x-2 gap-y-2.5">
              {length("pitch_x_nm", "Pitch x")}
              {length(
                "pitch_y_nm",
                p.kind === "ch_staggered" ? "Row pitch y" : "Pitch y",
                p.kind === "ch_staggered"
                  ? "Distance between rows; every other row is shifted by half a pitch"
                  : undefined,
              )}
              <StackedField label="Shape">
                <Segmented
                  aria-label="Shape"
                  value={p.hole_shape}
                  onChange={(v) => set("hole_shape", v)}
                  options={[
                    { value: "rect", label: "Rect" },
                    { value: "ellipse", label: "Ellipse" },
                  ]}
                />
              </StackedField>
              {length("cd_x_nm", `${shape} CD x`, undefined, 0)}
              {length("cd_y_nm", `${shape} CD y`, undefined, 0)}
              <StackedField label="Tone" hint="Holes: the CD is the opening. Pillars: the CD is the island.">
                <Segmented
                  aria-label="Tone"
                  value={p.tone}
                  onChange={(v) => set("tone", v)}
                  options={[
                    { value: "holes", label: "Holes" },
                    { value: "pillars", label: "Pillars" },
                  ]}
                />
              </StackedField>
            </div>
          ) : (
            <div className="grid grid-cols-3 gap-2">
              {length("pitch_x_nm", "Pitch")}
              {length("cd_x_nm", "Line CD", "Width of the patterned layer's material, e.g. the absorber line", 0)}
              <StackedField label="Space" hint="Pitch minus line CD">
                <span className="flex h-7 items-center px-1 text-xs text-muted-foreground tabular-nums">
                  {fmt(p.pitch_x_nm - p.cd_x_nm, 6)} nm
                </span>
              </StackedField>
            </div>
          )}
          <div className="grid grid-cols-2 gap-2">
            <StackedField label={fillLabel}>
              <SelectField value={p.fill} options={materials} onChange={(v) => set("fill", v)} aria-label={fillLabel} />
            </StackedField>
            {sloped && (
              <StackedField
                label="CD measured at"
                hint="Depth where the CD applies; the sidewall angles set the width elsewhere"
              >
                <Segmented
                  aria-label="CD measured at"
                  value={p.cd_reference}
                  onChange={(v) => set("cd_reference", v)}
                  options={[
                    { value: "top", label: "Top" },
                    { value: "middle", label: "Middle" },
                    { value: "bottom", label: "Bottom" },
                  ]}
                />
              </StackedField>
            )}
          </div>
          {etched.length === 0 ? (
            <Note tone="warn">
              No layer is patterned yet, so the pattern has no effect. Switch on{" "}
              <PatternGlyph kind={p.kind} className="inline size-3.5 align-[-2px]" /> next to the layer to etch, such as
              the absorber.
            </Note>
          ) : (
            <Note>
              Etched into {etched.map((l) => l.name).join(", ")}. Unit cell{" "}
              {ch
                ? `${fmt(Lx)} × ${fmt(Ly)} nm, periodic in x and y`
                : `${fmt(Lx)} nm, periodic in ${p.kind === "ls_v" ? "x" : "y"}`}
              .
            </Note>
          )}
        </>
      )}
    </SetupSection>
  );
}
