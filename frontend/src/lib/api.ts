import type { ApiErrorBody, TokenResponse } from "@/lib/types";

const BASE = "/api/v1";
const CSRF_COOKIE = "careeros_csrf";

let accessToken: string | null = null;
let refreshPromise: Promise<boolean> | null = null;
let unauthorizedHandler: (() => void) | null = null;

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: unknown;
  readonly requestId: string | undefined;

  constructor(status: number, code: string, message: string, details?: unknown, requestId?: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
    this.requestId = requestId;
  }

  static async fromResponse(response: Response): Promise<ApiError> {
    let body: ApiErrorBody | null = null;
    try {
      body = (await response.json()) as ApiErrorBody;
    } catch {
      body = null;
    }
    const error = body?.error;
    return new ApiError(
      response.status,
      error?.code ?? `http_${response.status}`,
      error?.message ?? defaultMessage(response.status),
      error?.details,
      error?.request_id,
    );
  }
}

function defaultMessage(status: number): string {
  if (status === 401) return "Your session has expired. Please sign in again.";
  if (status === 403) return "You are not allowed to do that.";
  if (status === 404) return "That item could not be found.";
  if (status === 413) return "That file is too large.";
  if (status === 429) return "Too many attempts. Please wait a moment.";
  if (status >= 500) return "Something went wrong on the server.";
  return "The request could not be completed.";
}

export function setAccessToken(token: string | null): void {
  accessToken = token;
}

export function getAccessToken(): string | null {
  return accessToken;
}

export function setUnauthorizedHandler(handler: (() => void) | null): void {
  unauthorizedHandler = handler;
}

export function readCookie(name: string): string | null {
  const escaped = name.replace(/[.$?*|{}()[\]\\/+^]/g, "\\$&");
  const match = document.cookie.match(new RegExp(`(?:^|; )${escaped}=([^;]*)`));
  return match ? decodeURIComponent(match[1]) : null;
}

export function csrfHeaders(): Record<string, string> {
  const token = readCookie(CSRF_COOKIE);
  return token ? { "X-CSRF-Token": token } : {};
}

async function performRefresh(): Promise<boolean> {
  const csrf = readCookie(CSRF_COOKIE);
  if (!csrf) return false;
  try {
    const response = await fetch(`${BASE}/auth/refresh`, {
      method: "POST",
      credentials: "include",
      headers: { "X-CSRF-Token": csrf },
    });
    if (!response.ok) return false;
    const data = (await response.json()) as TokenResponse;
    accessToken = data.access_token;
    return true;
  } catch {
    return false;
  }
}

/** Rotates the refresh token. Concurrent callers share one in-flight request. */
export function refreshSession(): Promise<boolean> {
  if (!refreshPromise) {
    refreshPromise = performRefresh().finally(() => {
      refreshPromise = null;
    });
  }
  return refreshPromise;
}

interface RequestOptions extends Omit<RequestInit, "body"> {
  body?: unknown;
  /** Set to false for endpoints that manage their own 401 handling. */
  retryOn401?: boolean;
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { body, retryOn401 = true, headers: rawHeaders, ...rest } = options;
  const headers = new Headers(rawHeaders);
  let payload: BodyInit | undefined;

  if (body instanceof FormData) {
    payload = body;
  } else if (body !== undefined) {
    headers.set("Content-Type", "application/json");
    payload = JSON.stringify(body);
  }

  if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);

  let response: Response;
  try {
    response = await fetch(`${BASE}${path}`, { ...rest, body: payload, headers, credentials: "include" });
  } catch {
    throw new ApiError(0, "network_error", "Cannot reach the CareerOS server. Is it running?");
  }

  const isAuthPath = path.startsWith("/auth/");
  if (response.status === 401 && retryOn401 && !isAuthPath) {
    const refreshed = await refreshSession();
    if (refreshed) {
      return request<T>(path, { ...options, retryOn401: false });
    }
    unauthorizedHandler?.();
  }

  if (!response.ok) throw await ApiError.fromResponse(response);
  if (response.status === 204 || response.headers.get("content-length") === "0") {
    return undefined as T;
  }
  const contentType = response.headers.get("content-type") ?? "";
  if (!contentType.includes("application/json")) return (await response.text()) as T;
  return (await response.json()) as T;
}

export const api = {
  get: <T>(path: string, options?: RequestOptions) => request<T>(path, { ...options, method: "GET" }),
  post: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    request<T>(path, { ...options, method: "POST", body }),
  patch: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    request<T>(path, { ...options, method: "PATCH", body }),
  delete: <T>(path: string, options?: RequestOptions) =>
    request<T>(path, { ...options, method: "DELETE" }),
};

export function toQuery(params: Record<string, string | number | boolean | null | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") continue;
    if (typeof value === "boolean" && !value) continue;
    search.set(key, String(value));
  }
  const query = search.toString();
  return query ? `?${query}` : "";
}

/** Authenticated binary download; the access token travels in a header, not the URL. */
export async function downloadFile(path: string, fallbackName: string): Promise<void> {
  const headers = new Headers();
  if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);
  const response = await fetch(`${BASE}${path}`, { headers, credentials: "include" });
  if (response.status === 401 && (await refreshSession())) {
    return downloadFile(path, fallbackName);
  }
  if (!response.ok) throw await ApiError.fromResponse(response);

  const disposition = response.headers.get("content-disposition") ?? "";
  const encoded = /filename\*=UTF-8''([^;]+)/i.exec(disposition)?.[1];
  const plain = /filename="?([^";]+)"?/i.exec(disposition)?.[1];
  const name = encoded ? decodeURIComponent(encoded) : plain || fallbackName;

  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = name;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  return "Something went wrong.";
}

/** Validation details from a 422 come back as [{field, msg}]. */
export function fieldErrors(error: unknown): Record<string, string> {
  if (!(error instanceof ApiError) || !Array.isArray(error.details)) return {};
  const output: Record<string, string> = {};
  for (const item of error.details as { field?: string; msg?: string }[]) {
    if (item.field) output[item.field] = item.msg ?? "Invalid value";
  }
  return output;
}
