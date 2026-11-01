import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  User,
  SlidersHorizontal,
  Volume2,
  Eye,
  Shield,
  Download,
  Trash2,
  LogOut,
  Check,
  Lock,
  AlertTriangle,
  KeyRound,
} from "lucide-react";
import { useAuth } from "../context/AuthContext";
import { useApp } from "../context/AppContext";
import { exportMyData, deleteMyData, updatePreferences } from "../api/sessions";
import type { PreferencesUpdate } from "../types";

export default function Settings() {
  const { user, signOut, updateDisplayName, accountsEnabled } = useAuth();
  const { prefs, updatePrefs } = useApp();
  const navigate = useNavigate();

  const [displayNameInput, setDisplayNameInput] = useState(user?.displayName || "");
  const [profileSaving, setProfileSaving] = useState(false);
  const [profileSaved, setProfileSaved] = useState(false);

  const [rate, setRate] = useState(prefs.speech_rate);
  const [confirmPurge, setConfirmPurge] = useState(false);
  const [isPurging, setIsPurging] = useState(false);
  const [purgeSuccess, setPurgeSuccess] = useState<string | null>(null);
  const timer = useRef<number>();

  useEffect(() => {
    setDisplayNameInput(user?.displayName || "");
  }, [user]);

  useEffect(() => {
    setRate(prefs.speech_rate);
  }, [prefs.speech_rate]);

  const handleSaveProfile = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!displayNameInput.trim()) return;
    setProfileSaving(true);
    try {
      updateDisplayName(displayNameInput.trim());
      await updatePreferences({ display_name: displayNameInput.trim() });
      setProfileSaved(true);
      setTimeout(() => setProfileSaved(false), 2500);
    } catch {
      // Local fallback updated
    } finally {
      setProfileSaving(false);
    }
  };

  const handleToggle = async (key: keyof PreferencesUpdate, value: boolean) => {
    await updatePrefs({ [key]: value });
  };

  const handleLevelChange = async (level: "beginner" | "experienced") => {
    await updatePrefs({ experience_level: level });
  };

  const handleRateChange = (newRate: number) => {
    setRate(newRate);
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(async () => {
      await updatePrefs({ speech_rate: newRate });
    }, 400);
  };

  const testVoiceSynthesis = () => {
    if (typeof window !== "undefined" && "speechSynthesis" in window) {
      window.speechSynthesis.cancel();
      const u = new SpeechSynthesisUtterance("Sensora speech synthesis test. Ready for hands-free troubleshooting.");
      u.rate = rate;
      window.speechSynthesis.speak(u);
    }
  };

  const handleDownloadExport = async () => {
    try {
      const data = await exportMyData();
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `sensora-data-export-${new Date().toISOString().slice(0, 10)}.json`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (err) {
      alert("Unable to generate export. " + (err instanceof Error ? err.message : ""));
    }
  };

  const handlePurgeAllData = async () => {
    setIsPurging(true);
    try {
      const res = await deleteMyData();
      setConfirmPurge(false);
      setPurgeSuccess(`Successfully removed ${res.deleted_sessions} sessions from the database.`);
      setTimeout(() => setPurgeSuccess(null), 4000);
    } catch (err) {
      alert("Failed to delete session records: " + (err instanceof Error ? err.message : ""));
    } finally {
      setIsPurging(false);
    }
  };

  const handleSignOut = () => {
    signOut();
    navigate("/");
  };

  return (
    <div className="container page narrow">
      <div className="mb-6">
        <p className="eyebrow">Account & System Configuration</p>
        <h1 className="text-2xl font-bold">Settings</h1>
        <p className="text-slate-600 text-sm m-0">
          Customize your diagnostic assistant preferences, accessibility options, and privacy controls.
        </p>
      </div>

      {purgeSuccess && (
        <div className="card p-4 mb-6 bg-emerald-50 border-emerald-200 text-emerald-800 flex items-center gap-2">
          <Check size={18} />
          <span>{purgeSuccess}</span>
        </div>
      )}

      {/* 1. Profile Section */}
      <section className="card block-card mb-6">
        <div className="flex items-center gap-2 mb-4">
          <User size={18} className="text-blue-600" />
          <h2 className="text-base font-bold m-0">Profile Information</h2>
        </div>

        <form onSubmit={handleSaveProfile} className="space-y-4">
          <div className="form-group">
            <label htmlFor="settings-name">Display Name</label>
            <div className="flex gap-2">
              <input
                id="settings-name"
                type="text"
                value={displayNameInput}
                onChange={(e) => setDisplayNameInput(e.target.value)}
                placeholder="Your name"
                className="max-w-md"
              />
              <button
                type="submit"
                className="btn btn-secondary flex-shrink-0"
                disabled={profileSaving || displayNameInput.trim() === user?.displayName}
              >
                {profileSaving ? "Saving..." : profileSaved ? "Saved!" : "Save Name"}
              </button>
            </div>
          </div>

          <div className="form-group">
            <label>Registered Email Address</label>
            <div className="text-sm font-medium text-slate-800 py-2">
              {user?.email || (
                <span className="text-slate-500 italic">
                  Isolated Guest Workspace (No email attached)
                </span>
              )}
            </div>
            {user?.kind === "guest" && (
              <p className="text-xs text-slate-500 m-0">
                To link your history to an email account and sign in from other devices, create an account.
              </p>
            )}
          </div>
        </form>
      </section>

      {/* 2. Troubleshooting Guidance Mode */}
      <section className="card block-card mb-6">
        <div className="flex items-center gap-2 mb-4">
          <SlidersHorizontal size={18} className="text-blue-600" />
          <h2 className="text-base font-bold m-0">Diagnostic Guidance Level</h2>
        </div>

        <div className="radio-cards">
          <label
            className={`radio-card ${prefs.experience_level === "beginner" ? "selected" : ""}`}
            onClick={() => handleLevelChange("beginner")}
          >
            <input
              type="radio"
              name="exp_level"
              checked={prefs.experience_level === "beginner"}
              onChange={() => handleLevelChange("beginner")}
            />
            <span className="font-bold text-slate-900 text-sm">Beginner Mode</span>
            <span className="text-xs text-slate-500">
              Clear, step-by-step descriptions with component locations and plain language explanations.
            </span>
          </label>

          <label
            className={`radio-card ${prefs.experience_level === "experienced" ? "selected" : ""}`}
            onClick={() => handleLevelChange("experienced")}
          >
            <input
              type="radio"
              name="exp_level"
              checked={prefs.experience_level === "experienced"}
              onChange={() => handleLevelChange("experienced")}
            />
            <span className="font-bold text-slate-900 text-sm">Experienced Mode</span>
            <span className="text-xs text-slate-500">
              Direct, technical instructions focusing on hardware specs, pinouts, and concise commands.
            </span>
          </label>
        </div>
      </section>

      {/* 3. Voice & Audio Preferences */}
      <section className="card block-card mb-6">
        <div className="flex items-center gap-2 mb-4">
          <Volume2 size={18} className="text-blue-600" />
          <h2 className="text-base font-bold m-0">Voice & Speech Responses</h2>
        </div>

        <div className="space-y-3">
          <label className="toggle">
            <div>
              <span className="font-semibold text-slate-900 text-sm">Read responses aloud</span>
              <span className="text-xs text-slate-500 block">
                Automatically speak assistant instructions via browser speech synthesis.
              </span>
            </div>
            <input
              type="checkbox"
              checked={prefs.speak_responses}
              onChange={(e) => handleToggle("speak_responses", e.target.checked)}
            />
          </label>

          {prefs.speak_responses && (
            <div className="py-2">
              <div className="flex justify-between items-center mb-1">
                <span className="text-sm font-semibold text-slate-900">Speech Rate</span>
                <span className="text-xs font-mono text-slate-500">{rate.toFixed(1)}x</span>
              </div>
              <div className="flex items-center gap-3">
                <input
                  type="range"
                  min="0.7"
                  max="1.5"
                  step="0.1"
                  value={rate}
                  onChange={(e) => handleRateChange(parseFloat(e.target.value))}
                  className="flex-1"
                />
                <button
                  type="button"
                  onClick={testVoiceSynthesis}
                  className="btn btn-secondary btn-small flex-shrink-0"
                >
                  Test Audio
                </button>
              </div>
            </div>
          )}
        </div>
      </section>

      {/* 4. Accessibility Preferences */}
      <section className="card block-card mb-6">
        <div className="flex items-center gap-2 mb-4">
          <Eye size={18} className="text-blue-600" />
          <h2 className="text-base font-bold m-0">Accessibility Controls</h2>
        </div>

        <div className="space-y-3">
          <label className="toggle">
            <div>
              <span className="font-semibold text-slate-900 text-sm">Larger Text</span>
              <span className="text-xs text-slate-500 block">Increase base font size across the application.</span>
            </div>
            <input
              type="checkbox"
              checked={prefs.larger_text}
              onChange={(e) => handleToggle("larger_text", e.target.checked)}
            />
          </label>

          <label className="toggle">
            <div>
              <span className="font-semibold text-slate-900 text-sm">High Contrast Mode</span>
              <span className="text-xs text-slate-500 block">Enhance border lines and text contrast for low-vision use.</span>
            </div>
            <input
              type="checkbox"
              checked={prefs.high_contrast}
              onChange={(e) => handleToggle("high_contrast", e.target.checked)}
            />
          </label>

          <label className="toggle">
            <div>
              <span className="font-semibold text-slate-900 text-sm">Reduce Motion</span>
              <span className="text-xs text-slate-500 block">Disable animations and transitions.</span>
            </div>
            <input
              type="checkbox"
              checked={prefs.reduce_motion}
              onChange={(e) => handleToggle("reduce_motion", e.target.checked)}
            />
          </label>
        </div>
      </section>

      {/* 5. Privacy & Data Controls */}
      <section className="card block-card mb-6">
        <div className="flex items-center gap-2 mb-4">
          <Shield size={18} className="text-blue-600" />
          <h2 className="text-base font-bold m-0">Privacy & Data Governance</h2>
        </div>

        <div className="notice mb-4">
          <p className="font-semibold text-slate-900 text-xs uppercase tracking-wide m-0">
            What Sensora AI Stores
          </p>
          <p className="text-xs text-slate-600 mt-1 m-0">
            We store session transcripts, diagnostic steps, and visual observation text tags in the database. Live camera video is processed frame-by-frame and never stored as raw recordings unless you explicitly give evidence retention consent during a session.
          </p>
        </div>

        <div className="space-y-3 pt-2">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-3 bg-slate-50 rounded-lg">
            <div>
              <div className="font-semibold text-slate-900 text-sm">Download Full Data Archive</div>
              <div className="text-xs text-slate-500">
                Export all your session transcripts, verified steps, and saved preferences as a JSON file.
              </div>
            </div>
            <button
              type="button"
              onClick={handleDownloadExport}
              className="btn btn-secondary btn-small flex-shrink-0"
            >
              <Download size={14} />
              <span>Export JSON</span>
            </button>
          </div>

          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-3 bg-red-50/50 rounded-lg border border-red-100">
            <div>
              <div className="font-semibold text-red-900 text-sm">Delete All Diagnostic Sessions</div>
              <div className="text-xs text-red-700/80">
                Permanently purge all session transcripts, verification outcomes, and history records.
              </div>
            </div>
            <button
              type="button"
              onClick={() => setConfirmPurge(true)}
              className="btn btn-danger-outline btn-small flex-shrink-0"
            >
              <Trash2 size={14} />
              <span>Purge All Data</span>
            </button>
          </div>
        </div>
      </section>

      {/* 6. Account Actions */}
      <section className="card block-card mb-6">
        <div className="flex items-center gap-2 mb-4">
          <Lock size={18} className="text-blue-600" />
          <h2 className="text-base font-bold m-0">Account & Authentication</h2>
        </div>

        <div className="space-y-3">
          {accountsEnabled && user?.kind === "account" && (
            <div className="flex items-center justify-between py-2 border-b border-slate-100">
              <div>
                <span className="font-semibold text-slate-900 text-sm">Password Security</span>
                <span className="text-xs text-slate-500 block">Send a password reset email to your registered inbox.</span>
              </div>
              <Link to="/forgot-password" className="btn btn-secondary btn-small">
                <KeyRound size={14} />
                <span>Reset Password</span>
              </Link>
            </div>
          )}

          <div className="flex items-center justify-between py-2">
            <div>
              <span className="font-semibold text-slate-900 text-sm">Sign Out</span>
              <span className="text-xs text-slate-500 block">End your current session on this device.</span>
            </div>
            <button type="button" onClick={handleSignOut} className="btn btn-secondary btn-small text-danger">
              <LogOut size={14} />
              <span>Sign out</span>
            </button>
          </div>
        </div>
      </section>

      {/* Purge Confirmation Modal */}
      {confirmPurge && (
        <div className="overlay" role="dialog" aria-modal="true">
          <div className="modal">
            <div className="flex items-start gap-3 mb-3">
              <div className="p-2 rounded-full bg-red-100 text-red-600">
                <AlertTriangle size={20} />
              </div>
              <div>
                <h2 className="text-lg font-bold text-slate-900 m-0">Purge all diagnostic data?</h2>
                <p className="text-sm text-slate-600 mt-1 m-0">
                  This destructive action will permanently erase all session records, transcripts, steps, and observation logs associated with your account. This cannot be undone.
                </p>
              </div>
            </div>

            <div className="modal-actions">
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => setConfirmPurge(false)}
                disabled={isPurging}
              >
                Cancel
              </button>
              <button
                type="button"
                className="btn btn-danger"
                onClick={handlePurgeAllData}
                disabled={isPurging}
              >
                {isPurging ? "Purging..." : "Yes, Purge Everything"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
