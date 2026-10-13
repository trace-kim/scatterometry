// TanStack Query hooks for every server view. Project-based views are keyed by a hash of
// the project's physics, so editing the stack re-fetches only what changed and the
// previous image stays on screen until the new one arrives (keepPreviousData).
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { hashValue } from "@/lib/hash";
import { type Arrays, api } from "./client";
import type {
  AbsorptionResponse,
  BoxesResponse,
  CheckResult,
  FluxResponse,
  JobInfo,
  ModesResponse,
  OrdersResponse,
  Polarization,
  PresetInfo,
  Project,
  PupilResponse,
  PythonViewInfo,
  PythonViewResult,
  SliceInfo,
  SweepResult,
} from "./model";

export interface SectionParams {
  axis: "x" | "y";
  offset_nm: number;
  periods: number;
  z_min_nm: number;
  z_max_nm: number;
  n_lateral: number;
  n_z: number;
}

/** Hash of everything that changes server responses (not the name or display colors). */
export function physicsKey(project: Project): string {
  return hashValue({ ...project, name: null, materials: project.materials.map(({ color: _, ...m }) => m) });
}

const FOREVER = Number.POSITIVE_INFINITY;

// ---- projects ----------------------------------------------------------------------

export function usePresets() {
  return useQuery({
    queryKey: ["presets"],
    queryFn: ({ signal }) => api.get<PresetInfo[]>("/presets", undefined, signal),
    staleTime: FOREVER,
  });
}

export function fetchPreset(id: string): Promise<Project> {
  return api.get<Project>(`/presets/${id}`);
}

export function normalizeProject(document: unknown): Promise<Project> {
  return api.post<Project>("/project/normalize", document);
}

export function useCheck(project: Project) {
  return useQuery({
    queryKey: ["check", physicsKey(project)],
    queryFn: ({ signal }) => api.post<CheckResult>("/project/check", project, signal),
    placeholderData: keepPreviousData,
    staleTime: FOREVER,
  });
}

function useProjectArrays(name: string, path: string, project: Project, params: object, enabled = true) {
  return useQuery({
    queryKey: [name, physicsKey(project), params],
    queryFn: ({ signal }) => api.postArrays(path, { project, ...params }, signal),
    placeholderData: keepPreviousData,
    staleTime: FOREVER,
    enabled,
  });
}

export function useGeometrySection(project: Project, params: SectionParams, enabled = true) {
  return useProjectArrays("geometry-section", "/geometry/section", project, params, enabled);
}

export function useGeometryPlane(project: Project, slice: number, periods: number, n: number, enabled = true) {
  return useProjectArrays("geometry-plane", "/geometry/plane", project, { slice, periods, n }, enabled);
}

export function useBoxes(project: Project, periods: number, zMaxNm: number | null, n: number, enabled = true) {
  return useQuery({
    queryKey: ["boxes", physicsKey(project), periods, zMaxNm, n],
    queryFn: ({ signal }) =>
      api.post<BoxesResponse>("/geometry/boxes", { project, periods, z_max_nm: zMaxNm, n }, signal),
    placeholderData: keepPreviousData,
    staleTime: FOREVER,
    enabled,
  });
}

export function useDielectricSection(project: Project, params: SectionParams & { fourier: boolean }, enabled = true) {
  return useProjectArrays("dielectric-section", "/dielectric/section", project, params, enabled);
}

export function useDielectricPlane(
  project: Project,
  slice: number,
  periods: number,
  fourier: boolean,
  n: number,
  enabled = true,
) {
  return useProjectArrays("dielectric-plane", "/dielectric/plane", project, { slice, periods, fourier, n }, enabled);
}

export function useConvolution(project: Project, slice: number, enabled = true) {
  return useProjectArrays("convolution", "/dielectric/convolution", project, { slice }, enabled);
}

// ---- jobs ----------------------------------------------------------------------------

export const FINISHED = new Set(["done", "failed", "cancelled"]);

/** Job status; kept current by server events (useServerEvents), polled as a fallback. */
export function useJob(id: string | null) {
  return useQuery({
    queryKey: ["job", id],
    queryFn: ({ signal }) => api.get<JobInfo>(`/jobs/${id}`, undefined, signal),
    enabled: !!id,
    retry: false,
    refetchInterval: (query) => (query.state.data && !FINISHED.has(query.state.data.status) ? 2000 : false),
  });
}

export function useSubmitRun() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: { project: Project; crosscheck: boolean }) => api.post<JobInfo>("/runs", body),
    onSuccess: (job) => client.setQueryData(["job", job.id], job),
  });
}

export function useSubmitSweep() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: { project: Project; parameter: string; start: number; stop: number; points: number }) =>
      api.post<JobInfo>("/sweeps", body),
    onSuccess: (job) => client.setQueryData(["job", job.id], job),
  });
}

export function useCancelJob() {
  return useMutation({
    mutationFn: (job: Pick<JobInfo, "id" | "kind">) =>
      api.del<JobInfo>(`/${job.kind === "run" ? "runs" : "sweeps"}/${job.id}`),
  });
}

// ---- run results (immutable once the run is done) -------------------------------------

function useRunJson<T>(runId: string | null, ready: boolean, path: string, query: Record<string, unknown>) {
  return useQuery({
    queryKey: ["run", runId, path, query],
    queryFn: ({ signal }) => api.get<T>(`/runs/${runId}${path}`, query as never, signal),
    enabled: !!runId && ready,
    staleTime: FOREVER,
    placeholderData: keepPreviousData,
    retry: false,
  });
}

export function useRunSlices(runId: string | null, ready: boolean) {
  return useRunJson<SliceInfo[]>(runId, ready, "/slices", {});
}

export function useOrders(runId: string | null, ready: boolean, pol: Polarization) {
  return useRunJson<OrdersResponse>(runId, ready, "/orders", { pol });
}

export function usePupil(runId: string | null, ready: boolean, pol: Polarization, na: number, reduction: number) {
  return useRunJson<PupilResponse>(runId, ready, "/pupil", { pol, na, reduction });
}

export function useFlux(runId: string | null, ready: boolean, pol: Polarization) {
  return useRunJson<FluxResponse>(runId, ready, "/flux", { pol, n: 800 });
}

export function useAbsorption(runId: string | null, ready: boolean, pol: Polarization) {
  return useRunJson<AbsorptionResponse>(runId, ready, "/absorption", { pol });
}

export function useModes(runId: string | null, ready: boolean, pol: Polarization, slice: number) {
  return useRunJson<ModesResponse>(runId, ready, "/modes", { pol, slice });
}

export function useFieldSection(runId: string | null, ready: boolean, pol: Polarization, params: SectionParams) {
  return useQuery<Arrays>({
    queryKey: ["run", runId, "field-section", pol, params],
    queryFn: ({ signal }) => api.getArrays(`/runs/${runId}/field/section`, { pol, ...params }, signal),
    enabled: !!runId && ready,
    staleTime: FOREVER,
    placeholderData: keepPreviousData,
    retry: false,
  });
}

export function useFieldPlane(
  runId: string | null,
  ready: boolean,
  pol: Polarization,
  depthNm: number,
  periods: number,
  n: number,
) {
  return useQuery<Arrays>({
    queryKey: ["run", runId, "field-plane", pol, depthNm, periods, n],
    queryFn: ({ signal }) =>
      api.getArrays(`/runs/${runId}/field/plane`, { pol, depth_nm: depthNm, periods, n }, signal),
    enabled: !!runId && ready,
    staleTime: FOREVER,
    placeholderData: keepPreviousData,
    retry: false,
  });
}

// ---- sweeps ----------------------------------------------------------------------------------

export function useSweep(sweepId: string | null) {
  return useQuery({
    queryKey: ["sweep", sweepId],
    queryFn: ({ signal }) => api.get<SweepResult>(`/sweeps/${sweepId}`, undefined, signal),
    enabled: !!sweepId,
    retry: false,
    placeholderData: keepPreviousData,
  });
}

// ---- Python-defined views (maskserver/python_views.py) ------------------------------------

export function usePythonViews() {
  return useQuery({
    queryKey: ["python-views"],
    queryFn: ({ signal }) => api.get<PythonViewInfo[]>("/python-views", undefined, signal),
    staleTime: FOREVER,
  });
}

export function usePythonView(
  viewId: string | null,
  project: Project,
  runId: string | null,
  pol: Polarization | null,
  enabled: boolean,
) {
  return useQuery({
    queryKey: ["python-view", viewId, physicsKey(project), runId, pol],
    queryFn: ({ signal }) =>
      api.post<PythonViewResult>(`/python-views/${viewId}`, { project, run_id: runId, pol }, signal),
    enabled: !!viewId && enabled,
    placeholderData: keepPreviousData,
    retry: false,
    staleTime: FOREVER,
  });
}
