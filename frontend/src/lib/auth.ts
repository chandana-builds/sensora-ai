// Auth without extra dependencies: guest tokens (signed by our backend) or Supabase email/password via its public REST API.
// Only public values are used here. Tokens live in localStorage (see docs/PRD.md).
const API = (
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ??
  (import.meta.env.VITE_API_URL as string | undefined) ??
  (typeof window !== "undefined" && window.location.hostname !== "localhost" && window.location.hostname !== "127.0.0.1"
    ? "https://sensora-ai.onrender.com"
    : "")
).replace(/\/$/, "");
const SUPA = (
  (import.meta.env.VITE_SUPABASE_URL as string | undefined) ??
  "https://vkkwwrkaovkaeqkdojbl.supabase.co"
).replace(/\/$/, "");
const SUPA_KEY =
  (import.meta.env.VITE_SUPABASE_ANON_KEY as string | undefined) ??
  "sb_publishable_ZvsgAd9UDeCK2nEThAmccA_NRbyCdKy";
const KEY = "sensora_auth_v1";

export interface AuthState {
  kind: "guest" | "account";
  token: string;
  refresh?: string;
  email?: string;
  displayName?: string;
  userId?: string;
}

export const accountsEnabled = !!(SUPA && SUPA_KEY);
export const isLocalSupabase = !!(SUPA && (SUPA.includes("127.0.0.1") || SUPA.includes("localhost")));
export const localMailpitUrl = (import.meta.env.VITE_LOCAL_MAILPIT_URL as string | undefined) || "http://127.0.0.1:54324";
const listeners = new Set<() => void>();
const emit = () => listeners.forEach((l) => l());

function parseJwt(token: string): Record<string, unknown> | null {
  try {
    const base64Url = token.split(".")[1];
    if (!base64Url) return null;
    const base64 = base64Url.replace(/-/g, "+").replace(/_/g, "/");
    const jsonPayload = decodeURIComponent(
      atob(base64)
        .split("")
        .map((c) => "%" + ("00" + c.charCodeAt(0).toString(16)).slice(-2))
        .join("")
    );
    return JSON.parse(jsonPayload);
  } catch {
    return null;
  }
}

export function getAuth(): AuthState | null {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return null;
    return JSON.parse(raw) as AuthState;
  } catch {
    return null;
  }
}

function setAuth(a: AuthState | null) {
  if (a) {
    if (!a.userId && a.token) {
      const claims = parseJwt(a.token);
      if (claims?.sub) {
        a.userId = String(claims.sub);
      }
    }
    localStorage.setItem(KEY, JSON.stringify(a));
  } else {
    localStorage.removeItem(KEY);
  }
  emit();
}

export function onAuthChange(cb: () => void) {
  listeners.add(cb);
  return () => {
    listeners.delete(cb);
  };
}

export function authHeaders(): Record<string, string> {
  const a = getAuth();
  return a ? { Authorization: `Bearer ${a.token}` } : {};
}

export function signOut() {
  setAuth(null);
}

export function updateDisplayName(name: string) {
  const cur = getAuth();
  if (cur) {
    setAuth({ ...cur, displayName: name.trim() });
  }
}

export class AuthApiError extends Error {
  readonly status: number;
  readonly errorCode?: string;
  readonly isRateLimit: boolean;
  readonly isEmailRateLimit: boolean;
  readonly retryAfterSeconds: number;

  constructor(
    message: string,
    status: number = 400,
    errorCode?: string,
    retryAfterSeconds: number = 60
  ) {
    super(message);
    this.name = "AuthApiError";
    this.status = status;
    this.errorCode = errorCode;
    this.isEmailRateLimit =
      errorCode === "over_email_send_rate_limit" ||
      /email rate limit/i.test(message);
    this.isRateLimit =
      status === 429 ||
      this.isEmailRateLimit ||
      errorCode === "over_request_rate_limit" ||
      /rate limit|too many requests/i.test(message);
    this.retryAfterSeconds = retryAfterSeconds;
  }
}

async function supa(path: string, body: unknown) {
  if (!SUPA || !SUPA_KEY) {
    throw new AuthApiError(
      "Supabase Auth is not configured. Set VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY in your frontend environment.",
      500,
      "unconfigured"
    );
  }
  let res: Response;
  try {
    res = await fetch(`${SUPA}/auth/v1/${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json", apikey: SUPA_KEY },
      body: JSON.stringify(body),
    });
  } catch {
    throw new AuthApiError(
      "Unable to reach the authentication service. Please check your internet connection.",
      503,
      "network_error"
    );
  }
  const j = await res.json().catch(() => ({}));
  if (!res.ok) {
    const rawMsg: string = j.error_description || j.msg || j.message || "";
    const errorCode: string | undefined = j.error_code || (j.code ? String(j.code) : undefined);

    // Identify Supabase's default email sending rate limit
    if (res.status === 429 || errorCode === "over_email_send_rate_limit" || /email rate limit/i.test(rawMsg)) {
      throw new AuthApiError(
        "Email delivery rate limit reached. Supabase's default email pool limits messages to a few per hour. Please wait before retrying, or configure custom SMTP in Supabase.",
        429,
        "over_email_send_rate_limit",
        60
      );
    }

    if (res.status === 429 || /too many requests|rate limit/i.test(rawMsg)) {
      throw new AuthApiError(
        "Too many requests. Please wait a moment before trying again.",
        429,
        "over_request_rate_limit",
        60
      );
    }

    const msg = rawMsg || "Authentication request failed.";
    throw new AuthApiError(msg, res.status, errorCode);
  }
  return j;
}

export async function continueAsGuest(): Promise<void> {
  let res: Response;
  const baseUrl = API || "http://localhost:8000";
  try {
    res = await fetch(`${baseUrl}/api/auth/guest`, { method: "POST" });
  } catch {
    throw new AuthApiError(
      "Cannot reach the Sensora backend server. Ensure the backend is running at " + baseUrl,
      503,
      "backend_unreachable"
    );
  }
  const j = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new AuthApiError(
      typeof j.detail === "string" ? j.detail : "Guest session access is currently unavailable.",
      res.status
    );
  }
  setAuth({ kind: "guest", token: j.token, displayName: "Guest User" });
}

export async function signIn(email: string, password: string): Promise<void> {
  const cleanEmail = email.trim();
  const baseUrl = API || "http://127.0.0.1:8000";

  // Step 1: Try Supabase standard password sign-in if accounts are configured
  if (accountsEnabled) {
    try {
      const j = await supa("token?grant_type=password", { email: cleanEmail, password });
      setAuth({
        kind: "account",
        token: j.access_token,
        refresh: j.refresh_token,
        email: j.user?.email || cleanEmail,
        userId: j.user?.id,
        displayName: j.user?.user_metadata?.display_name || cleanEmail.split("@")[0],
      });
      return;
    } catch (err) {
      if (err instanceof AuthApiError && err.isRateLimit) {
        throw err;
      }
      // If credentials failed in Supabase, fall through to check local SQLite database
    }
  }

  // Step 2: Try local database login if Supabase is unavailable or user was stored in SQLite
  try {
    const res = await fetch(`${baseUrl}/api/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email: cleanEmail, password }),
    });
    const j = await res.json().catch(() => ({}));
    if (res.ok && j.token) {
      setAuth({
        kind: "account",
        token: j.token,
        email: j.email || cleanEmail,
        userId: j.user_id,
        displayName: j.displayName || cleanEmail.split("@")[0],
      });
      return;
    }
  } catch {
    // ignore
  }

  throw new AuthApiError("Invalid email address or password.", 401);
}

/** Returns true when the account is signed in; false when email confirmation is required. */
export async function signUp(email: string, password: string, displayName?: string): Promise<boolean> {
  const cleanEmail = email.trim();
  const cleanDisplay = displayName?.trim();
  const baseUrl = API || "http://127.0.0.1:8000";

  // Step 1: Use backend registration (bypasses Supabase email rate limits via Admin auto-confirmation or SQLite)
  try {
    const res = await fetch(`${baseUrl}/api/auth/register`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        email: cleanEmail,
        password,
        display_name: cleanDisplay,
      }),
    });
    const j = await res.json().catch(() => ({}));

    if (res.ok) {
      // If user was created in Supabase with auto-confirmation, sign in immediately!
      if (j.provider === "supabase" && accountsEnabled) {
        await signIn(cleanEmail, password);
        return true;
      }
      // If user was created in local SQLite database, use the returned session token!
      if (j.token) {
        setAuth({
          kind: "account",
          token: j.token,
          email: j.email || cleanEmail,
          userId: j.user_id,
          displayName: j.display_name || cleanDisplay || cleanEmail.split("@")[0],
        });
        return true;
      }
    } else {
      if (res.status === 409 || j.detail?.toLowerCase().includes("already exists")) {
        throw new AuthApiError(j.detail || "An account with this email address already exists. Please sign in.", 409);
      }
      if (typeof j.detail === "string" && !j.detail.includes("internal")) {
        throw new AuthApiError(j.detail, res.status);
      }
    }
  } catch (err) {
    if (err instanceof AuthApiError && err.status === 409) {
      throw err;
    }
    // Fall back to direct public Supabase sign up if backend endpoint is unreachable
  }

  // Step 2: Fallback to direct public Supabase signup
  const payload: Record<string, unknown> = { email: cleanEmail, password };
  if (cleanDisplay) {
    payload.data = { display_name: cleanDisplay };
  }
  const j = await supa("signup", payload);
  if (j.access_token) {
    setAuth({
      kind: "account",
      token: j.access_token,
      refresh: j.refresh_token,
      email: j.user?.email || cleanEmail,
      userId: j.user?.id,
      displayName: cleanDisplay || cleanEmail.split("@")[0],
    });
    return true;
  }
  return false;
}

export async function resetPasswordForEmail(email: string): Promise<void> {
  await supa("recover", { email });
}

/** Resend account confirmation email via Supabase Auth */
export async function resendVerificationEmail(email: string): Promise<void> {
  await supa("resend", { type: "signup", email: email.trim() });
}

/** One refresh attempt for expired account tokens. */
export async function refreshSession(): Promise<boolean> {
  const a = getAuth();
  if (!a || a.kind !== "account" || !a.refresh) return false;
  try {
    const j = await supa("token?grant_type=refresh_token", { refresh_token: a.refresh });
    setAuth({
      ...a,
      token: j.access_token,
      refresh: j.refresh_token ?? a.refresh,
      userId: j.user?.id ?? a.userId,
    });
    return true;
  } catch {
    return false;
  }
}
