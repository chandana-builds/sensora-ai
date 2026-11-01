import { createContext, ReactNode, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import type { Health, Preferences, PreferencesUpdate } from "../types";

export type Connection = "checking" | "online" | "offline";

const DEFAULT_PREFS: Preferences = {
  experience_level: "beginner", speak_responses: true, speech_rate: 1, larger_text: false,
  high_contrast: false, reduce_motion: false, save_transcripts: true, updated_at: null,
};

interface AppState {
  health: Health | null;
  connection: Connection;
  prefs: Preferences;
  prefsStatus: "loading" | "ready" | "error";
  prefsError: string | null;
  updatePrefs: (patch: PreferencesUpdate) => Promise<void>;
  reloadPrefs: () => void;
  retryConnection: () => Promise<void>;
}

const Ctx = createContext<AppState | null>(null);

export function AppProvider({ children }: { children: ReactNode }) {
  const [health, setHealth] = useState<Health | null>(null);
  const [connection, setConnection] = useState<Connection>("checking");
  const [prefs, setPrefs] = useState<Preferences>(DEFAULT_PREFS);
  const [prefsStatus, setPrefsStatus] = useState<AppState["prefsStatus"]>("loading");
  const [prefsError, setPrefsError] = useState<string | null>(null);
  const [prefsTick, setPrefsTick] = useState(0);

  const performHealthCheck = useCallback(async () => {
    try {
      const h = await api.health();
      setHealth(h);
      setConnection("online");
    } catch {
      setHealth(null);
      setConnection("offline");
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    let timer: number;
    const check = async () => {
      try {
        const h = await api.health();
        if (!cancelled) {
          setHealth(h);
          setConnection("online");
          timer = window.setTimeout(check, 30_000);
        }
      } catch {
        if (!cancelled) {
          setHealth(null);
          setConnection("offline");
          // Re-check every 4 seconds when offline so the UI reconnects immediately
          timer = window.setTimeout(check, 4_000);
        }
      }
    };
    void check();
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    setPrefsStatus("loading");
    api.getPreferences().then(
      (p) => { if (!cancelled) { setPrefs(p); setPrefsStatus("ready"); setPrefsError(null); } },
      (e: unknown) => {
        if (!cancelled) { setPrefsStatus("error"); setPrefsError(e instanceof Error ? e.message : "Could not load preferences."); }
      },
    );
    return () => { cancelled = true; };
  }, [prefsTick]);

  useEffect(() => {
    const root = document.documentElement;
    root.dataset.text = prefs.larger_text ? "large" : "normal";
    root.dataset.contrast = prefs.high_contrast ? "high" : "normal";
    root.dataset.motion = prefs.reduce_motion ? "reduce" : "normal";
  }, [prefs.larger_text, prefs.high_contrast, prefs.reduce_motion]);

  const updatePrefs = useCallback(async (patch: PreferencesUpdate) => {
    const previous = prefs;
    setPrefs({ ...prefs, ...patch });
    try {
      setPrefs(await api.updatePreferences(patch));
      setPrefsStatus("ready");
    } catch (err) {
      setPrefs(previous);
      throw err;
    }
  }, [prefs]);

  const reloadPrefs = useCallback(() => setPrefsTick((t) => t + 1), []);

  const value = useMemo<AppState>(
    () => ({ health, connection, prefs, prefsStatus, prefsError, updatePrefs, reloadPrefs, retryConnection: performHealthCheck }),
    [health, connection, prefs, prefsStatus, prefsError, updatePrefs, reloadPrefs, performHealthCheck],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useApp(): AppState {
  const v = useContext(Ctx);
  if (!v) throw new Error("useApp must be used inside <AppProvider>");
  return v;
}
