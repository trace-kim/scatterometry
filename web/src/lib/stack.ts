// Pure helpers behind the setup panel: repeat-group blocks and the edits that keep them
// intact, the stack's total thickness, which diffraction orders propagate, and which
// setup section a validation message belongs to. Edits take an Immer draft.
import { isContactHoles, type LayerDoc, type PatternDoc, type Project } from "@/api/model";

export type SetupSectionId = "stack" | "pattern" | "illumination" | "accuracy" | "materials";

export interface LayerBlock {
  /** Repeat group of the run, or "" for a single ungrouped layer. */
  group: string;
  /** Index of the run's first layer in `project.layers`. */
  start: number;
  /** One past the run's last layer. */
  end: number;
  /** Repetitions of the run (1 when ungrouped). */
  count: number;
}

type Stack = Pick<Project, "layers" | "repeats">;

/** Runs of contiguous layers sharing a repeat group (mirrors masksim.stack._layer_blocks). */
export function layerBlocks({ layers, repeats }: Stack): LayerBlock[] {
  const blocks: LayerBlock[] = [];
  let i = 0;
  while (i < layers.length) {
    const group = layers[i].group.trim();
    let j = i + 1;
    while (group && j < layers.length && layers[j].group.trim() === group) j++;
    blocks.push({ group, start: i, end: j, count: group ? Math.max(1, Math.trunc(repeats[group] ?? 1)) : 1 });
    i = j;
  }
  return blocks;
}

/** Thickness of one repetition of a block (nm). */
export function blockThickness(layers: LayerDoc[], block: LayerBlock): number {
  let sum = 0;
  for (let i = block.start; i < block.end; i++) sum += layers[i].thickness_nm;
  return sum;
}

/** Thickness of the expanded stack (nm). */
export function totalThickness(stack: Stack): number {
  return layerBlocks(stack).reduce((sum, b) => sum + b.count * blockThickness(stack.layers, b), 0);
}

export function blockOf(blocks: LayerBlock[], index: number): number {
  return blocks.findIndex((b) => index >= b.start && index < b.end);
}

/** Drops repeat counts of groups no layer uses any more. */
function pruneRepeats(d: Project) {
  const used = new Set(d.layers.map((l) => l.group.trim()));
  for (const group of Object.keys(d.repeats)) if (!used.has(group)) delete d.repeats[group];
}

/**
 * Whether `moveLayer(index, delta)` can move the layer: a grouped layer moves only inside
 * its group, an ungrouped one steps over a whole neighbouring block.
 */
export function canMoveLayer(stack: Stack, index: number, delta: -1 | 1): boolean {
  const blocks = layerBlocks(stack);
  const b = blocks[blockOf(blocks, index)];
  if (!b) return false;
  if (b.group) return index + delta >= b.start && index + delta < b.end;
  return !!blocks[blockOf(blocks, index) + delta];
}

export function moveLayer(d: Project, index: number, delta: -1 | 1) {
  if (!canMoveLayer(d, index, delta)) return;
  const blocks = layerBlocks(d);
  const bi = blockOf(blocks, index);
  if (blocks[bi].group) {
    const [layer] = d.layers.splice(index, 1);
    d.layers.splice(index + delta, 0, layer);
    return;
  }
  const neighbor = blocks[bi + delta];
  const [layer] = d.layers.splice(index, 1);
  d.layers.splice(delta < 0 ? neighbor.start : neighbor.end - 1, 0, layer);
}

/** Moves a whole block over its neighbouring block. */
export function moveBlock(d: Project, start: number, delta: -1 | 1) {
  const blocks = layerBlocks(d);
  const bi = blockOf(blocks, start);
  const block = blocks[bi];
  const neighbor = blocks[bi + delta];
  if (!block || !neighbor) return;
  const [first, second] = delta < 0 ? [neighbor, block] : [block, neighbor];
  const firstLayers = d.layers.slice(first.start, first.end);
  const secondLayers = d.layers.slice(second.start, second.end);
  d.layers.splice(first.start, second.end - first.start, ...secondLayers, ...firstLayers);
}

/** Inserts `layer` next to `index` as a sibling: inside a group it joins that group. */
export function insertLayer(d: Project, index: number, where: "above" | "below", layer: LayerDoc) {
  const reference = d.layers[index];
  d.layers.splice(where === "above" ? index : index + 1, 0, { ...layer, group: reference?.group ?? "" });
}

export function deleteLayer(d: Project, index: number) {
  d.layers.splice(index, 1);
  pruneRepeats(d);
}

/** The group an ungrouped layer could join by direction, if the neighbouring block is a group. */
export function adjacentGroup(stack: Stack, index: number, delta: -1 | 1): string | null {
  const blocks = layerBlocks(stack);
  const bi = blockOf(blocks, index);
  if (bi < 0 || blocks[bi].group) return null;
  return blocks[bi + delta]?.group || null;
}

export function joinGroup(d: Project, index: number, delta: -1 | 1) {
  const group = adjacentGroup(d, index, delta);
  if (group) d.layers[index].group = group;
}

/** Makes an ungrouped layer a new group of its own, repeated twice. Returns the group name. */
export function newGroup(d: Project, index: number): string {
  const taken = new Set([...d.layers.map((l) => l.group.trim()), ...Object.keys(d.repeats)]);
  let i = 1;
  while (taken.has(`Group ${i}`)) i++;
  const name = `Group ${i}`;
  d.layers[index].group = name;
  d.repeats[name] = 2;
  return name;
}

/** Takes a layer out of its group; a layer from the middle of the group moves just below it. */
export function leaveGroup(d: Project, index: number) {
  const blocks = layerBlocks(d);
  const block = blocks[blockOf(blocks, index)];
  if (!block?.group) return;
  const [layer] = d.layers.splice(index, 1);
  layer.group = "";
  const at = index === block.start ? block.start : block.end - 1;
  d.layers.splice(at, 0, layer);
  pruneRepeats(d);
}

export function ungroup(d: Project, start: number) {
  const blocks = layerBlocks(d);
  const block = blocks[blockOf(blocks, start)];
  if (!block?.group) return;
  for (let i = block.start; i < block.end; i++) d.layers[i].group = "";
  pruneRepeats(d);
}

/** Renames a group's run, keeping its repeat count. Empty names are ignored. */
export function renameGroup(d: Project, start: number, name: string) {
  const next = name.trim();
  const blocks = layerBlocks(d);
  const block = blocks[blockOf(blocks, start)];
  if (!block?.group || !next || next === block.group) return;
  for (let i = block.start; i < block.end; i++) d.layers[i].group = next;
  d.repeats[next] = d.repeats[next] ?? block.count;
  pruneRepeats(d);
}

// ---- materials ------------------------------------------------------------------------

/** Where each material is used, keyed by name: layer names and the media and fill roles. */
export function materialUsage(project: Project): Map<string, string[]> {
  const usage = new Map<string, string[]>();
  const add = (material: string, where: string) => usage.set(material, [...(usage.get(material) ?? []), where]);
  add(project.superstrate, "incident medium");
  for (const layer of project.layers) add(layer.material, layer.name || "unnamed layer");
  add(project.substrate, "substrate");
  if (project.pattern.kind !== "none") add(project.pattern.fill, "pattern fill");
  return usage;
}

// ---- pattern and diffraction orders ------------------------------------------------------

/** Unit cell (Lx, Ly) in nm, as masksim.stack.unit_cell. */
export function unitCell(p: PatternDoc): [number, number] {
  if (isContactHoles(p.kind)) return [p.pitch_x_nm, p.pitch_y_nm * (p.kind === "ch_staggered" ? 2 : 1)];
  return [p.pitch_x_nm, p.pitch_x_nm];
}

export function isPatterned(project: Project): boolean {
  return project.pattern.kind !== "none" && project.layers.some((l) => l.patterned);
}

export interface PropagatingOrders {
  /** Order range along x (m) and y (n); [0, 0] along an axis that is not periodic. */
  m: [number, number];
  n: [number, number];
  /** Number of (m, n) orders that propagate back into the incident medium. */
  count: number;
}

/**
 * Reflected orders that propagate: |k_t| < n_inc with k_t = k_inc,t − (m λ/Lx, n λ/Ly),
 * the solver's convention. Null for an unpatterned stack (only the specular order exists).
 */
export function propagatingOrders(project: Project): PropagatingOrders | null {
  if (!isPatterned(project)) return null;
  const { pattern: p, illumination: ill } = project;
  const nInc = project.materials.find((m) => m.name === project.superstrate)?.n ?? Number.NaN;
  const [Lx, Ly] = unitCell(p);
  if (!(ill.wavelength_nm > 0 && nInc > 0 && Lx > 0 && Ly > 0)) return null;
  const sin = nInc * Math.sin((ill.theta_deg * Math.PI) / 180);
  const kx0 = sin * Math.cos((ill.phi_deg * Math.PI) / 180);
  const ky0 = sin * Math.sin((ill.phi_deg * Math.PI) / 180);
  const gx = p.kind === "ls_h" ? 0 : ill.wavelength_nm / Lx;
  const gy = p.kind === "ls_v" ? 0 : ill.wavelength_nm / Ly;
  const range = (k0: number, g: number): [number, number] =>
    g === 0 ? [0, 0] : [Math.ceil((k0 - nInc) / g), Math.floor((k0 + nInc) / g)];
  const [m0, m1] = range(kx0, gx);
  const [n0, n1] = range(ky0, gy);
  const limit = nInc * nInc * (1 - 1e-12);
  let count = 0;
  const m: [number, number] = [Number.POSITIVE_INFINITY, Number.NEGATIVE_INFINITY];
  const n: [number, number] = [Number.POSITIVE_INFINITY, Number.NEGATIVE_INFINITY];
  for (let i = m0; i <= m1; i++) {
    for (let j = n0; j <= n1; j++) {
      const kx = kx0 - i * gx;
      const ky = ky0 - j * gy;
      if (kx * kx + ky * ky >= limit) continue;
      count++;
      m[0] = Math.min(m[0], i);
      m[1] = Math.max(m[1], i);
      n[0] = Math.min(n[0], j);
      n[1] = Math.max(n[1], j);
    }
  }
  return count ? { m, n, count } : null;
}

/**
 * Smallest numerics.nx / numerics.ny that keep every propagating order (the solver uses nx
 * along y for horizontal lines). Null for an unpatterned stack.
 */
export function minimumOrders(project: Project): { nx: number; ny: number } | null {
  const orders = propagatingOrders(project);
  if (!orders) return null;
  const reach = ([lo, hi]: [number, number]) => Math.max(Math.abs(lo), Math.abs(hi));
  const kind = project.pattern.kind;
  if (kind === "ls_v") return { nx: reach(orders.m), ny: 0 };
  if (kind === "ls_h") return { nx: reach(orders.n), ny: 0 };
  return { nx: reach(orders.m), ny: reach(orders.n) };
}

// ---- validation messages ---------------------------------------------------------------

/** Setup section a message from masksim.validate() belongs to (see stack.py). */
export function problemSection(message: string, project: Project): SetupSectionId {
  const unknown = /^Unknown material '(.*)'\.$/.exec(message);
  if (unknown) {
    const name = unknown[1];
    const inStack =
      project.superstrate === name || project.substrate === name || project.layers.some((l) => l.material === name);
    return inStack ? "stack" : "pattern";
  }
  if (/^Layer '/.test(message)) return "stack";
  if (/material/i.test(message)) return "materials";
  if (/^(Pitches|CD) /.test(message)) return "pattern";
  if (/^(Wavelength|Angle of incidence) /.test(message)) return "illumination";
  if (/harmonic|grid/i.test(message)) return "accuracy";
  return "stack";
}
