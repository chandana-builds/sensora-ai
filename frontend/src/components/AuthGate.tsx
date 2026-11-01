import { useEffect, useState, type ReactNode } from "react";
import { accountsEnabled, continueAsGuest, getAuth, onAuthChange, signIn, signOut, signUp } from "../lib/auth";

export function useAuth() {
  const [auth, setAuth] = useState(getAuth());
  useEffect(() => onAuthChange(() => setAuth(getAuth())), []);
  return auth;
}

export default function AuthGate({ children }: { children: ReactNode }) {
  const auth = useAuth();
  const [email, setEmail] = useState(""); const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false); const [msg, setMsg] = useState<string | null>(null); const [err, setErr] = useState<string | null>(null);
  if (auth) return <>{children}</>;

  const run = async (fn: () => Promise<void>) => { setBusy(true); setErr(null); setMsg(null); try { await fn(); } catch (e) { setErr((e as Error).message); } finally { setBusy(false); } };
  return (
    <main className="auth" aria-labelledby="auth-h">
      <h1 id="auth-h">Sensora AI</h1>
      <p>Sign in so your troubleshooting sessions stay private to you.</p>
      {accountsEnabled && (
        <div>
          <input type="email" placeholder="Email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} aria-label="Email" />
          <input type="password" placeholder="Password (8+ characters)" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} aria-label="Password" />
          <button disabled={busy || !email || password.length < 8} onClick={() => void run(() => signIn(email, password))}>Sign in</button>{" "}
          <button className="secondary" disabled={busy || !email || password.length < 8}
            onClick={() => void run(async () => { setMsg((await signUp(email, password)) ? null : "Account created. Check your email to confirm it, then sign in."); })}>Create account</button>
        </div>
      )}
      <p><button className="secondary" disabled={busy} onClick={() => void run(continueAsGuest)}>Continue as guest (demo)</button></p>
      <p className="note">Guest sessions are private to this browser's token only. Clearing browser data loses access to them. Camera frames are never stored unless you consent.</p>
      {busy && <p role="status">Connecting… (the free server can take up to a minute to wake up)</p>}
      {msg && <p role="status">{msg}</p>}{err && <p role="alert" className="err">{err}</p>}
    </main>
  );
}
export { signOut };
