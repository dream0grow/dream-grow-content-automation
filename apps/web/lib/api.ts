const BASE = "/api/v1";

export type FetchOptions = RequestInit & { token?: string };

export async function apiFetch<T>(path: string, opts: FetchOptions = {}): Promise<T> {
  const headers = new Headers(opts.headers);
  if (!headers.has("Content-Type") && opts.body && typeof opts.body === "string") {
    headers.set("Content-Type", "application/json");
  }
  if (opts.token) headers.set("Authorization", `Bearer ${opts.token}`);
  const res = await fetch(`${BASE}${path}`, {
    ...opts,
    headers,
    credentials: "include",
    cache: "no-store",
  });
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail ?? detail; } catch { /* ignore */ }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  return text ? (JSON.parse(text) as T) : (undefined as T);
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

export const api = {
  get:    <T,>(p: string)            => apiFetch<T>(p),
  post:   <T,>(p: string, body?: unknown) =>
    apiFetch<T>(p, { method: "POST", body: body ? JSON.stringify(body) : undefined }),
  put:    <T,>(p: string, body: unknown) =>
    apiFetch<T>(p, { method: "PUT", body: JSON.stringify(body) }),
  patch:  <T,>(p: string, body: unknown) =>
    apiFetch<T>(p, { method: "PATCH", body: JSON.stringify(body) }),
  delete: <T,>(p: string)            => apiFetch<T>(p, { method: "DELETE" }),
};
