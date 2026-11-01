// Self-contained app shell for the demo: auth -> dashboard/history -> live session -> session detail + handoff.
// Use it as-is (render <SensoraApp/> from main.tsx) or lift the pieces into your own router.
import { useState } from "react";
import { createSession, deleteMyData, exportMyData } from "./api/sessions";
import AuthGate, { signOut, useAuth } from "./components/AuthGate";
import ExperienceSetting from "./components/ExperienceSetting";
import LiveConsole from "./components/LiveConsole";
import ModeBadge from "./components/ModeBadge";
import PrivacyControls from "./components/PrivacyControls";
import SessionHistory from "./components/SessionHistory";
import SessionView from "./components/SessionView";

type View = { name: "home" } | { name: "live"; id: string } | { name: "detail"; id: string };

function Shell() {
  const auth = useAuth();
  const [view, setView] = useState<View>({ name: "home" });
  const [level, setLevel] = useState<"beginner" | "experienced" | null>(null);
  const [err, setErr] = useState<string | null>(null); const [busy, setBusy] = useState(false); const [bump, setBump] = useState(0);

  async function start() {
    setBusy(true); setErr(null);
    try { const s = await createSession({ user_level: level }); setView({ name: "live", id: s.id }); } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  }
  async function download() {
    try { const url = URL.createObjectURL(new Blob([JSON.stringify(await exportMyData(), null, 2)], { type: "application/json" })); Object.assign(document.createElement("a"), { href: url, download: "sensora-my-data.json" }).click(); URL.revokeObjectURL(url); } catch (e) { setErr((e as Error).message); }
  }
  async function wipe() {
    if (!window.confirm("Delete ALL your sessions, saved frames and preferences? This can't be undone.")) return;
    try { await deleteMyData(); setBump((b) => b + 1); setView({ name: "home" }); } catch (e) { setErr((e as Error).message); }
  }
  return (
    <div className="app">
      <header className="top">
        <button className="linkish" onClick={() => setView({ name: "home" })}><strong>Sensora AI</strong></button>
        <ModeBadge />
        <span className="note">{auth?.kind === "guest" ? "Guest" : auth?.email}</span>
        <button className="secondary" onClick={signOut}>Sign out</button>
      </header>
      {err && <p role="alert" className="err">{err}</p>}
      {view.name === "home" && <main>
        <h1>Troubleshoot a device</h1>
        <p>Describe the problem, show the device, and follow one step at a time.</p>
        <button onClick={() => void start()} disabled={busy}>{busy ? "Starting…" : "Start a new session"}</button>
        <ExperienceSetting onChange={setLevel} />
        <h2>Recent sessions</h2>
        <SessionHistory refreshKey={bump} onOpen={(id) => setView({ name: "detail", id })} />
        <h2>Your data</h2>
        <button className="secondary" onClick={() => void download()}>Download all my data</button>{" "}
        <button className="secondary" onClick={() => void wipe()}>Delete all my data</button>
      </main>}
      {view.name === "live" && <main>
        <button className="secondary" onClick={() => setView({ name: "detail", id: view.id })}>End & review session</button>
        <LiveConsole sessionId={view.id} userLevel={level ?? undefined} />
        <PrivacyControls sessionId={view.id} />
      </main>}
      {view.name === "detail" && <main>
        <button className="secondary" onClick={() => setView({ name: "home" })}>← All sessions</button>
        <SessionView sessionId={view.id} onResume={() => setView({ name: "live", id: view.id })} />
      </main>}
    </div>
  );
}
export default function SensoraApp() { return <AuthGate><Shell /></AuthGate>; }
