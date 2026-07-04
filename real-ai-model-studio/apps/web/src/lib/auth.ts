// Client-side auth helpers. The token/role live in localStorage. This is a UI
// convenience for the stakeholder trial — the backend is the real gate: every
// protected call carries the Bearer token and the API rejects anything invalid.

const TOKEN_KEY = "rams_token";
const ROLE_KEY = "rams_role";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function getRole(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(ROLE_KEY);
}

export function setAuth(token: string, role: string): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(TOKEN_KEY, token);
  window.localStorage.setItem(ROLE_KEY, role);
}

export function clearAuth(): void {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(TOKEN_KEY);
  window.localStorage.removeItem(ROLE_KEY);
}

// Hard redirect to /login. Used by api.ts on 401 (outside React tree) and by the
// AuthGuard. Avoids importing next/router into non-component modules.
export function redirectToLogin(): void {
  if (typeof window === "undefined") return;
  if (window.location.pathname !== "/login") {
    window.location.href = "/login";
  }
}
