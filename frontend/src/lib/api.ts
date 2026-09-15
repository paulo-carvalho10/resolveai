/** HTTP client for the ResolveAI API: token storage, automatic refresh and typed errors. */

const BASE_URL = import.meta.env.VITE_API_URL ?? "/api";
const STORAGE_KEY = "resolveai.tokens";

export type Tokens = { access_token: string; refresh_token: string };

export class ApiError extends Error {
  status: number;
  code: string;
  details?: { field: string; message: string }[];

  constructor(
    status: number,
    code: string,
    message: string,
    details?: { field: string; message: string }[],
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

export const tokenStorage = {
  read(): Tokens | null {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      return raw ? (JSON.parse(raw) as Tokens) : null;
    } catch {
      return null; // private mode or corrupted value: behave as logged out
    }
  },
  write(tokens: Tokens) {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(tokens));
    } catch {
      /* ignore */
    }
  },
  clear() {
    try {
      localStorage.removeItem(STORAGE_KEY);
    } catch {
      /* ignore */
    }
  },
};

/** Fired when the session cannot be renewed, so the app can send the user back to login. */
export const SESSION_EXPIRED_EVENT = "resolveai:session-expired";

type RequestOptions = {
  method?: string;
  body?: unknown;
  params?: Record<string, string | number | boolean | string[] | undefined | null>;
  auth?: boolean;
};

function buildUrl(path: string, params?: RequestOptions["params"]): string {
  const url = new URL(`${BASE_URL}${path}`, window.location.origin);
  for (const [key, value] of Object.entries(params ?? {})) {
    if (value === undefined || value === null || value === "") continue;
    if (Array.isArray(value)) value.forEach((item) => url.searchParams.append(key, item));
    else url.searchParams.set(key, String(value));
  }
  return url.toString();
}

async function toApiError(response: Response): Promise<ApiError> {
  let code = `HTTP_${response.status}`;
  let message = response.statusText;
  let details: { field: string; message: string }[] | undefined;
  try {
    const body = await response.json();
    if (body?.error) {
      code = body.error.code ?? code;
      message = body.error.message ?? message;
      details = body.error.details;
    }
  } catch {
    /* response without a JSON body */
  }
  return new ApiError(response.status, code, message, details);
}

async function refreshTokens(): Promise<boolean> {
  const tokens = tokenStorage.read();
  if (!tokens?.refresh_token) return false;
  const response = await fetch(buildUrl("/auth/refresh"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: tokens.refresh_token }),
  });
  if (!response.ok) return false;
  tokenStorage.write((await response.json()) as Tokens);
  return true;
}

export async function api<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, params, auth = true } = options;

  const send = async (): Promise<Response> => {
    const headers: Record<string, string> = {};
    if (body !== undefined) headers["Content-Type"] = "application/json";
    const tokens = auth ? tokenStorage.read() : null;
    if (tokens) headers.Authorization = `Bearer ${tokens.access_token}`;
    return fetch(buildUrl(path, params), {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  };

  let response = await send();
  // An expired access token is renewed once, transparently.
  if (response.status === 401 && auth && tokenStorage.read()) {
    if (await refreshTokens()) {
      response = await send();
    }
    if (response.status === 401) {
      tokenStorage.clear();
      window.dispatchEvent(new Event(SESSION_EXPIRED_EVENT));
    }
  }

  if (!response.ok) throw await toApiError(response);
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}
