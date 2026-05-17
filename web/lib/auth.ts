/**
 * I-rdy-004 (#500) — client-side auth: JWT store + login + header injection.
 *
 * Carney demo scope. The JWT is held in sessionStorage: survives a page
 * refresh, cleared when the tab closes, not shared with a fresh tab —
 * the safer browser-storage choice per the Codex I-rdy-004 brief review.
 * 12h JWT expiry (matches the backend); cleared on any 401.
 */

const TOKEN_KEY = "polaris_jwt";
const EXPIRY_KEY = "polaris_jwt_expiry_ms";
const DEFAULT_EXPIRY_SECONDS = 12 * 60 * 60;

export interface LoginResult {
  ok: boolean;
  status: number;
  error?: string;
}

function store(): Storage | null {
  if (typeof window === "undefined") return null;
  return window.sessionStorage;
}

/** Current JWT, or null if absent or past its 12h expiry. */
export function getToken(): string | null {
  const s = store();
  if (!s) return null;
  const token = s.getItem(TOKEN_KEY);
  const expiry = s.getItem(EXPIRY_KEY);
  if (!token || !expiry) return null;
  if (Date.now() >= Number(expiry)) {
    clearToken();
    return null;
  }
  return token;
}

export function setToken(token: string, expiresInSeconds: number): void {
  const s = store();
  if (!s) return;
  const ttl = expiresInSeconds > 0 ? expiresInSeconds : DEFAULT_EXPIRY_SECONDS;
  s.setItem(TOKEN_KEY, token);
  s.setItem(EXPIRY_KEY, String(Date.now() + ttl * 1000));
}

export function clearToken(): void {
  const s = store();
  if (!s) return;
  s.removeItem(TOKEN_KEY);
  s.removeItem(EXPIRY_KEY);
}

export function isAuthenticated(): boolean {
  return getToken() !== null;
}

/**
 * POST credentials to the backend. On 200, store the JWT and report ok.
 * A 401 here is invalid-credentials feedback for the sign-in form — it is
 * NOT routed through the generic 401-redirect (that would loop the page).
 */
export async function login(
  username: string,
  password: string,
): Promise<LoginResult> {
  let response: Response;
  try {
    response = await fetch("/api/v6/auth/login", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ username, password }),
    });
  } catch {
    return {
      ok: false,
      status: 0,
      error: "Could not reach POLARIS. Check the connection.",
    };
  }
  if (response.status === 200) {
    const body = (await response.json()) as {
      access_token: string;
      expires_in?: number;
    };
    setToken(body.access_token, body.expires_in ?? DEFAULT_EXPIRY_SECONDS);
    return { ok: true, status: 200 };
  }
  if (response.status === 401) {
    return { ok: false, status: 401, error: "Invalid username or password." };
  }
  return {
    ok: false,
    status: response.status,
    error: `Sign-in failed (HTTP ${response.status}).`,
  };
}

/** Authorization header for the current token, or {} if unauthenticated. */
export function authHeader(): Record<string, string> {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

/** Clear the token and route to /sign-in. Called on a generic 401. */
export function redirectToSignIn(): void {
  if (typeof window === "undefined") return;
  clearToken();
  if (window.location.pathname !== "/sign-in") {
    window.location.href = "/sign-in";
  }
}
