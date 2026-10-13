// Thin fetch layer over the maskserver API (/api). JSON in and out, except array
// endpoints, which return .npz archives decoded by lib/npz.
import { type NpyArray, parseNpz } from "@/lib/npz";

export class ApiError extends Error {
  readonly status: number;
  readonly errors: string[];

  constructor(status: number, errors: string[]) {
    super(errors.join("; ") || `HTTP ${status}`);
    this.status = status;
    this.errors = errors;
  }
}

export type Query = Record<string, string | number | boolean | null | undefined>;
export type Arrays = Record<string, NpyArray>;

function url(path: string, query?: Query): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value !== undefined && value !== null) params.set(key, String(value));
  }
  const qs = params.toString();
  return `/api${path}${qs ? `?${qs}` : ""}`;
}

async function toError(response: Response): Promise<ApiError> {
  let errors: string[] = [];
  try {
    const detail = (await response.json())?.detail;
    if (Array.isArray(detail?.errors)) errors = detail.errors;
    else if (typeof detail === "string") errors = [detail];
    else if (Array.isArray(detail))
      errors = detail.map((e: { loc?: unknown[]; msg?: string }) => `${(e.loc ?? []).slice(1).join(".")}: ${e.msg}`);
  } catch {
    // not a JSON error body
  }
  return new ApiError(response.status, errors.length ? errors : [`${response.status} ${response.statusText}`]);
}

async function send(
  method: string,
  path: string,
  options: { body?: unknown; query?: Query; signal?: AbortSignal } = {},
): Promise<Response> {
  const hasBody = options.body !== undefined;
  const response = await fetch(url(path, options.query), {
    method,
    signal: options.signal,
    headers: hasBody ? { "content-type": "application/json" } : undefined,
    body: hasBody ? JSON.stringify(options.body) : undefined,
  });
  if (!response.ok) throw await toError(response);
  return response;
}

export const api = {
  async get<T>(path: string, query?: Query, signal?: AbortSignal): Promise<T> {
    return (await send("GET", path, { query, signal })).json();
  },
  async post<T>(path: string, body: unknown, signal?: AbortSignal): Promise<T> {
    return (await send("POST", path, { body, signal })).json();
  },
  async del<T>(path: string): Promise<T> {
    return (await send("DELETE", path)).json();
  },
  async getArrays(path: string, query?: Query, signal?: AbortSignal): Promise<Arrays> {
    return parseNpz(await (await send("GET", path, { query, signal })).arrayBuffer());
  },
  async postArrays(path: string, body: unknown, signal?: AbortSignal): Promise<Arrays> {
    return parseNpz(await (await send("POST", path, { body, signal })).arrayBuffer());
  },
};

export function errorMessages(error: unknown): string[] {
  if (error instanceof ApiError) return error.errors;
  if (error instanceof Error) return [error.message];
  return error ? [String(error)] : [];
}
