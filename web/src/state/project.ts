// The project document being edited, with undo/redo built on Immer patches.
// Edits that share a `key` within COALESCE_MS (typing in one field, dragging a slider)
// collapse into a single undo step.
import { applyPatches, enablePatches, type Patch, produceWithPatches } from "immer";
import { create } from "zustand";
import type { Project } from "@/api/model";
import { hashValue } from "@/lib/hash";

enablePatches();

const COALESCE_MS = 1200;
const HISTORY_LIMIT = 300;
const AUTOSAVE_KEY = "masksim.project.v1";

interface Entry {
  redo: Patch[];
  undo: Patch[];
  key?: string;
  at: number;
}

interface ProjectState {
  project: Project | null;
  past: Entry[];
  future: Entry[];
  revision: number;
  /** Hash of the document as last loaded or saved; `isDirty` compares against it. */
  savedHash: string;
  fileName: string | null;
  load: (project: Project, fileName?: string | null) => void;
  edit: (recipe: (draft: Project) => void, key?: string) => void;
  undo: () => void;
  redo: () => void;
  markSaved: (fileName?: string) => void;
}

export const useProjectStore = create<ProjectState>()((set, get) => ({
  project: null,
  past: [],
  future: [],
  revision: 0,
  savedHash: "",
  fileName: null,

  load: (project, fileName = null) =>
    set((s) => ({ project, past: [], future: [], fileName, revision: s.revision + 1, savedHash: hashValue(project) })),

  edit: (recipe, key) => {
    const { project, past, revision } = get();
    if (!project) return;
    const [next, redo, undo] = produceWithPatches(project, recipe);
    if (!redo.length) return;
    const now = Date.now();
    const last = past[past.length - 1];
    const history =
      key && last?.key === key && now - last.at < COALESCE_MS
        ? [...past.slice(0, -1), { redo: [...last.redo, ...redo], undo: [...undo, ...last.undo], key, at: now }]
        : [...past, { redo, undo, key, at: now }].slice(-HISTORY_LIMIT);
    set({ project: next, past: history, future: [], revision: revision + 1 });
  },

  undo: () => {
    const { project, past, future, revision } = get();
    const entry = past[past.length - 1];
    if (!project || !entry) return;
    set({
      project: applyPatches(project, entry.undo),
      past: past.slice(0, -1),
      future: [...future, { ...entry, key: undefined }],
      revision: revision + 1,
    });
  },

  redo: () => {
    const { project, past, future, revision } = get();
    const entry = future[future.length - 1];
    if (!project || !entry) return;
    set({
      project: applyPatches(project, entry.redo),
      past: [...past, entry],
      future: future.slice(0, -1),
      revision: revision + 1,
    });
  },

  markSaved: (fileName) =>
    set((s) => ({ savedHash: s.project ? hashValue(s.project) : "", fileName: fileName ?? s.fileName })),
}));

/** True when the document differs from its last loaded or saved state. */
export function isDirty(state: Pick<ProjectState, "project" | "savedHash">): boolean {
  return !!state.project && hashValue(state.project) !== state.savedHash;
}

/** The loaded project (the workspace only renders once one is loaded). */
export function useProject(): Project {
  const project = useProjectStore((s) => s.project);
  if (!project) throw new Error("no project loaded");
  return project;
}

export const editProject = (recipe: (draft: Project) => void, key?: string) =>
  useProjectStore.getState().edit(recipe, key);

// ---- browser autosave (survives reloads; files are saved explicitly) -------------------

export function restoreAutosave(): Project | null {
  try {
    const text = localStorage.getItem(AUTOSAVE_KEY);
    return text ? (JSON.parse(text) as Project) : null;
  } catch {
    return null;
  }
}

let autosaveTimer: ReturnType<typeof setTimeout> | undefined;
useProjectStore.subscribe((state, previous) => {
  if (!state.project || state.project === previous.project) return;
  clearTimeout(autosaveTimer);
  autosaveTimer = setTimeout(() => {
    try {
      localStorage.setItem(AUTOSAVE_KEY, JSON.stringify(state.project));
    } catch {
      // storage full or blocked: autosave is a convenience only
    }
  }, 400);
});
