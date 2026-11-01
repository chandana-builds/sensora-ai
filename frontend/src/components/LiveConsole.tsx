import { useCallback, useEffect, useRef, useState } from "react";
import {
  Camera,
  Eye,
  Image as ImageIcon,
  Mic,
  MicOff,
  PhoneOff,
  RefreshCw,
  Sparkles,
  Upload,
  Video,
  VideoOff,
  AlertTriangle,
} from "lucide-react";
import { ApiError, getAiStatus, transcribe, type AIStatus } from "../api/live";
import { postAgentTurn, type AgentTurnResult } from "../api/agent";
import StepStatus from "./StepStatus";
import { captureFrame, fileToCapturedFrame, type CapturedFrame } from "../lib/frames";
import { blobToWav16k } from "../lib/wav";
import { useLiveCamera } from "../hooks/useLiveCamera";
import { usePushToTalk } from "../hooks/usePushToTalk";
import { useSpeechOutput } from "../hooks/useSpeechOutput";
import "./LiveConsole.css";

interface Line {
  id: string;
  role: "user" | "assistant";
  text: string;
  simulated?: boolean;
  images?: string[];
}
const MAX_FRAMES = 5;

export default function LiveConsole({
  sessionId,
  userLevel,
  disabled = false,
  deviceName,
  problemDescription,
  initialMessages,
}: {
  sessionId: string;
  userLevel?: "beginner" | "experienced";
  disabled?: boolean;
  deviceName?: string;
  problemDescription?: string;
  initialMessages?: Array<{ id: string; role: string; content: string; metadata?: any }>;
}) {
  const cam = useLiveCamera();
  const ptt = usePushToTalk();
  const tts = useSpeechOutput();
  const [mediaMode, setMediaMode] = useState<"video" | "photos">("video");
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [status, setStatus] = useState<AIStatus | null>(null);
  const [statusErr, setStatusErr] = useState<string | null>(null);
  const [lines, setLines] = useState<Line[]>(() => {
    if (initialMessages && initialMessages.length > 0) {
      return initialMessages.map((m: any) => ({
        id: m.id,
        role: m.role as "user" | "assistant",
        text: m.content,
        images: m.metadata?.images || [],
      }));
    }
    return [];
  });
  const [draft, setDraft] = useState("");
  const [inputMode, setInputMode] = useState<"voice" | "text">("text");
  const [frames, setFrames] = useState<CapturedFrame[]>([]);
  const [last, setLast] = useState<AgentTurnResult | null>(null);
  const [busy, setBusy] = useState<"idle" | "transcribing" | "thinking">("idle");
  const [error, setError] = useState<{ msg: string; retry: boolean } | null>(null);
  const [speakReplies, setSpeakReplies] = useState(true);
  const lastSend = useRef<(() => void) | null>(null);
  const endRef = useRef<HTMLDivElement | null>(null);
  const initialTurnTriggered = useRef(false);
  const cameraAutoStarted = useRef(false);
  const [isListening, setIsListening] = useState(false);
  const recognitionRef = useRef<any>(null);

  // In-call duration timer
  const [callDuration, setCallDuration] = useState(0);
  useEffect(() => {
    let timer: any;
    if (cam.status === "live") {
      timer = setInterval(() => {
        setCallDuration((s) => s + 1);
      }, 1000);
    } else {
      setCallDuration(0);
    }
    return () => clearInterval(timer);
  }, [cam.status]);

  const formatDuration = (secs: number) => {
    const m = Math.floor(secs / 60);
    const s = secs % 60;
    return `${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`;
  };

  // Continuous Auto-Scan vision helper
  const [autoScan, setAutoScan] = useState(false);
  useEffect(() => {
    if (!autoScan || cam.status !== "live" || busy !== "idle") return;
    const interval = setInterval(() => {
      if (cam.status === "live" && busy === "idle" && cam.videoRef.current) {
        try {
          const frame = captureFrame(cam.videoRef.current);
          setFrames((f) => (f.length < MAX_FRAMES ? [...f, frame] : f));
        } catch {}
      }
    }, 10000);
    return () => clearInterval(interval);
  }, [autoScan, cam.status, busy]);

  useEffect(() => {
    let cancelled = false;
    getAiStatus()
      .then((st) => {
        if (!cancelled) setStatus(st);
      })
      .catch((e: Error) => {
        if (!cancelled) setStatusErr(e.message);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Safe scroll effect with explicit void return
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [lines, busy]);

  // Attempt camera start on mount
  useEffect(() => {
    if (!cameraAutoStarted.current && cam.supported && !disabled) {
      cameraAutoStarted.current = true;
      cam.start().catch(() => {});
    }
  }, [cam.supported, disabled, cam]);

  const fail = (e: unknown) =>
    setError({
      msg: e instanceof Error ? e.message : "Something went wrong.",
      retry: e instanceof ApiError ? e.retryable : false,
    });

  function grab() {
    setError(null);
    if (!cam.videoRef.current) return;
    if (frames.length >= MAX_FRAMES) {
      return setError({ msg: `You can attach up to ${MAX_FRAMES} frames per message.`, retry: false });
    }
    try {
      setFrames((f) => [...f, captureFrame(cam.videoRef.current!)]);
    } catch (e) {
      fail(e);
    }
  }

  async function handlePhotoUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const files = e.target.files;
    if (!files || files.length === 0) return;
    setError(null);
    try {
      const remainingSlots = MAX_FRAMES - frames.length;
      if (remainingSlots <= 0) {
        setError({ msg: `You can attach up to ${MAX_FRAMES} pictures per message.`, retry: false });
        return;
      }
      const filesToProcess = Array.from(files).slice(0, remainingSlots);
      const newFrames = await Promise.all(filesToProcess.map((f) => fileToCapturedFrame(f)));
      setFrames((prev) => [...prev, ...newFrames]);
    } catch (err) {
      fail(err);
    } finally {
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  }

  // Live Speech Recognition with PTT fallback
  const toggleListening = useCallback(() => {
    const SpeechRec = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (isListening) {
      if (recognitionRef.current) {
        try {
          recognitionRef.current.stop();
        } catch {}
      }
      setIsListening(false);
      return;
    }

    if (SpeechRec) {
      try {
        if (recognitionRef.current) {
          try {
            recognitionRef.current.abort();
          } catch {}
        }
        const rec = new SpeechRec();
        rec.continuous = false;
        rec.interimResults = true;
        rec.lang = navigator.language || "en-US";
        rec.onstart = () => {
          setIsListening(true);
          tts.stop();
          setError(null);
        };
        rec.onresult = (evt: any) => {
          const text = Array.from(evt.results)
            .map((r: any) => r[0].transcript)
            .join("");
          setDraft(text);
        };
        rec.onerror = (evt: any) => {
          console.warn("Speech recognition notice:", evt.error);
          setIsListening(false);
        };
        rec.onend = () => {
          setIsListening(false);
        };
        recognitionRef.current = rec;
        rec.start();
        return;
      } catch (e) {
        console.warn("SpeechRec start fallback to PTT:", e);
      }
    }

    // Fallback: Push-To-Talk audio recorder
    void toggleMic();
  }, [isListening, tts]);

  async function toggleMic() {
    setError(null);
    if (ptt.state === "idle") {
      tts.stop();
      await ptt.start();
      return;
    }
    const blob = await ptt.stop();
    if (!blob) return setError({ msg: "Nothing was recorded.", retry: false });
    setBusy("transcribing");
    try {
      const r = await transcribe(await blobToWav16k(blob));
      setDraft((d) => (d ? d + " " : "") + r.text);
    } catch (e) {
      setError({
        msg: "Voice transcription is unavailable from AI providers. Please type your message in the text box below.",
        retry: false,
      });
    } finally {
      setBusy("idle");
    }
  }

  async function send(text = draft.trim(), attached = frames, mode = inputMode, done = false) {
    if (!text || busy !== "idle" || disabled) return;
    if (isListening && recognitionRef.current) {
      try {
        recognitionRef.current.stop();
      } catch {}
      setIsListening(false);
    }
    tts.stop();
    setError(null);
    lastSend.current = () => void send(text, attached, mode, done);
    const attachedImages = attached.map((f) => f.dataUrl);
    setLines((l) => [...l, { id: crypto.randomUUID(), role: "user", text, images: attachedImages }]);
    setDraft("");
    setFrames([]);
    setBusy("thinking");
    try {
      const r = await postAgentTurn(sessionId, {
        text,
        input_mode: mode,
        frames: attached.map((f) => f.base64),
        user_level: userLevel,
        reported_step_done: done,
      });
      setLast(r);
      setInputMode("text");
      setLines((l) => [
        ...l,
        {
          id: r.assistant_message_id ?? crypto.randomUUID(),
          role: "assistant",
          text: r.response.assistant_message,
          simulated: r.simulated,
        },
      ]);
      if (speakReplies) tts.speak(r.response.assistant_message);
    } catch (e) {
      fail(e);
    } finally {
      setBusy("idle");
    }
  }

  // Auto-trigger initial diagnostic turn
  useEffect(() => {
    if (initialTurnTriggered.current) return;
    const initialText =
      problemDescription?.trim() || (deviceName ? `I need help troubleshooting my ${deviceName}.` : "");
    if (initialText && lines.length === 0 && busy === "idle" && !disabled) {
      initialTurnTriggered.current = true;
      void send(initialText, [], "text");
    }
  }, [problemDescription, deviceName, lines.length, busy, disabled]);

  const resp = last?.response;
  const stopped = resp?.safety_status === "stop";

  return (
    <div className="lc">
      {status?.simulated && <div className="lc-banner lc-demo" role="status">DEMO MODE — {status.note}</div>}
      {statusErr && <div className="lc-banner lc-warn" role="alert">Can't read AI status: {statusErr}</div>}
      {status && !status.simulated && (
        <div className="lc-banner lc-ok">AI connected with real-time reasoning ({status.reasoning}).</div>
      )}
      {stopped && (
        <div className="lc-banner lc-stop" role="alert">
          <strong>Safety stop.</strong> {resp!.assistant_message}
        </div>
      )}

      {/* Dual Mode Visual Inspection Window */}
      <section className="lc-cam-call card p-0 overflow-hidden relative shadow-lg border border-slate-200">
        <div className="lc-mode-tabs">
          <button
            type="button"
            onClick={() => setMediaMode("video")}
            className={`lc-mode-tab ${mediaMode === "video" ? "active" : ""}`}
            title="Real-time camera video call"
          >
            <Video size={16} />
            <span>Live Video Call</span>
            {cam.status === "live" && <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse ml-1" />}
          </button>
          <button
            type="button"
            onClick={() => setMediaMode("photos")}
            className={`lc-mode-tab ${mediaMode === "photos" ? "active" : ""}`}
            title="Capture or upload picture snapshots of the device"
          >
            <ImageIcon size={16} />
            <span>Capture & Upload Pictures {frames.length > 0 && `(${frames.length})`}</span>
          </button>
        </div>

        {/* Hidden file input for uploading pictures */}
        <input
          ref={fileInputRef}
          type="file"
          accept="image/*"
          multiple
          className="hidden"
          onChange={handlePhotoUpload}
          style={{ display: "none" }}
        />

        {/* Video Call Container (kept in DOM to prevent re-creation and play drops) */}
        <div className="relative" style={{ display: mediaMode === "video" ? "block" : "none" }}>
          {/* Top Status & Telemetry Bar */}
          <div className="absolute top-3 left-3 right-3 z-10 flex items-center justify-between pointer-events-none">
            <div className="flex items-center gap-2 bg-slate-900/85 backdrop-blur text-white px-3 py-1.5 rounded-full text-xs font-semibold shadow pointer-events-auto">
              {cam.status === "live" ? (
                <>
                  <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 animate-pulse" />
                  <span className="tracking-wide">LIVE CALL</span>
                  <span className="text-slate-500">·</span>
                  <span className="text-emerald-400 font-mono">{formatDuration(callDuration)}</span>
                </>
              ) : (
                <>
                  <span className="w-2.5 h-2.5 rounded-full bg-amber-500" />
                  <span>STANDBY</span>
                </>
              )}
              <span className="text-slate-500">·</span>
              <span className="text-slate-300 font-normal truncate max-w-[130px] sm:max-w-[200px]">
                {deviceName || "Device Inspection"}
              </span>
            </div>

            {cam.status === "live" && (
              <div className="flex items-center gap-1.5 bg-slate-900/80 backdrop-blur px-2.5 py-1 rounded-full text-xs font-medium text-slate-300 shadow pointer-events-auto">
                <span className="text-emerald-400 font-mono text-[11px]">
                  {cam.streamSource === "demo" ? "DEMO FEED" : "720p HD"}
                </span>
                {autoScan && (
                  <span className="flex items-center gap-1 text-cyan-400 text-[10px] bg-cyan-950/70 border border-cyan-800/60 px-2 py-0.5 rounded-full">
                    <Eye size={10} className="animate-pulse" /> AUTO-SCAN
                  </span>
                )}
              </div>
            )}
          </div>

          <video
            ref={cam.videoRef}
            autoPlay
            playsInline
            muted
            className="w-full bg-slate-950 object-cover min-h-[340px] max-h-[480px]"
            aria-label="Live camera video stream"
            onClick={cam.playVideo}
          />

          {/* Standby & Error Overlay Screen */}
          {cam.status !== "live" && (
            <div className="absolute inset-0 flex flex-col items-center justify-center bg-slate-900/95 text-slate-200 p-6 text-center z-10 backdrop-blur-sm">
              {cam.status === "error" ? (
                <div className="max-w-md mx-auto">
                  <div className="w-14 h-14 rounded-full bg-rose-500/15 border border-rose-500/30 flex items-center justify-center mx-auto mb-3 text-rose-400">
                    <AlertTriangle size={30} />
                  </div>
                  <h4 className="font-semibold text-lg text-white mb-1.5">Camera Connection Notice</h4>
                  <p className="text-xs text-rose-300 bg-rose-950/40 border border-rose-900/60 rounded-lg p-2.5 mb-4">
                    {cam.error || "Unable to start webcam stream."}
                  </p>
                  <p className="text-xs text-slate-400 mb-5 leading-relaxed">
                    You can grant browser camera access, or click <strong>Start Demo Video Call</strong> to test Sensora's
                    real-time video diagnostics right now.
                  </p>
                  <div className="flex items-center justify-center gap-3 flex-wrap">
                    <button
                      type="button"
                      onClick={() => cam.start()}
                      className="btn btn-secondary btn-sm flex items-center gap-1.5 bg-slate-800 text-white border-slate-600 hover:bg-slate-700"
                    >
                      <RefreshCw size={15} />
                      <span>Retry Webcam</span>
                    </button>
                    <button
                      type="button"
                      onClick={cam.startDemoFeed}
                      className="btn btn-primary btn-sm flex items-center gap-1.5 px-4 py-2 bg-teal-600 hover:bg-teal-500 text-white shadow-lg shadow-teal-900/40"
                    >
                      <Sparkles size={15} />
                      <span>Start Demo Video Call</span>
                    </button>
                  </div>
                </div>
              ) : (
                <div className="max-w-md mx-auto">
                  <div className="w-14 h-14 rounded-full bg-teal-500/15 border border-teal-500/30 flex items-center justify-center mx-auto mb-3 text-teal-400">
                    <Camera size={30} className={cam.status === "starting" ? "animate-spin" : ""} />
                  </div>
                  <h4 className="font-semibold text-lg text-white mb-1.5">
                    {cam.status === "starting" ? "Connecting video feed…" : "Interactive Video Call"}
                  </h4>
                  <p className="text-xs text-slate-400 mb-5 leading-relaxed">
                    Stream your device live or launch the interactive simulated video feed with active hardware telemetry.
                  </p>
                  <div className="flex items-center justify-center gap-3 flex-wrap">
                    <button
                      type="button"
                      onClick={() => cam.start()}
                      disabled={cam.status === "starting" || disabled}
                      className="btn btn-primary btn-sm flex items-center gap-2 px-4 py-2"
                    >
                      <Video size={16} />
                      <span>Turn On Webcam</span>
                    </button>
                    <button
                      type="button"
                      onClick={cam.startDemoFeed}
                      disabled={cam.status === "starting" || disabled}
                      className="btn btn-secondary btn-sm flex items-center gap-2 bg-slate-800 text-slate-200 border-slate-700 hover:bg-slate-700 px-4 py-2"
                    >
                      <Sparkles size={16} className="text-teal-400" />
                      <span>Launch Demo Video</span>
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Full Floating In-Call Controls Bar */}
          <div className="lc-call-bar">
            {cam.status === "live" ? (
              <>
                {/* 1. Snap Evidence Frame for Analysis */}
                <button
                  type="button"
                  onClick={grab}
                  className="lc-call-btn lc-btn-snap"
                  title="Capture current camera view for AI inspection"
                >
                  <Camera size={16} />
                  <span>Snap Evidence</span>
                  <span className="lc-snap-badge">{frames.length}/{MAX_FRAMES}</span>
                </button>

                {/* 2. Video Track Mute / Pause Toggle */}
                <button
                  type="button"
                  onClick={cam.toggleMuteVideo}
                  className={`lc-call-btn ${cam.isVideoMuted ? "lc-btn-muted" : "lc-btn-media"}`}
                  title={cam.isVideoMuted ? "Resume video stream" : "Turn off video stream"}
                >
                  {cam.isVideoMuted ? <VideoOff size={16} /> : <Video size={16} />}
                  <span className="lc-call-label">{cam.isVideoMuted ? "Video Off" : "Video On"}</span>
                </button>

                {/* 3. Audio Mic Toggle (Speech-to-Text / PTT) */}
                <button
                  type="button"
                  onClick={toggleListening}
                  className={`lc-call-btn ${
                    isListening || ptt.state === "recording"
                      ? "lc-btn-listening"
                      : "lc-btn-media"
                  }`}
                  title={isListening ? "Listening... click to stop" : "Speak to AI"}
                >
                  {isListening || ptt.state === "recording" ? <MicOff size={16} /> : <Mic size={16} />}
                  <span className="lc-call-label">
                    {isListening || ptt.state === "recording" ? "Listening…" : "Mute Mic"}
                  </span>
                </button>

                {/* 4. Auto-Scan Toggle */}
                <button
                  type="button"
                  onClick={() => setAutoScan((v) => !v)}
                  className={`lc-call-btn lc-btn-autoscan ${autoScan ? "active" : ""}`}
                  title={autoScan ? "Disable auto vision scanning" : "Enable continuous AI vision scanning"}
                >
                  <Eye size={16} className={autoScan ? "text-cyan-300 animate-pulse" : ""} />
                  <span className="lc-call-label">Auto-Scan</span>
                </button>

                {/* 5. Switch Source (Webcam <-> Demo Feed) */}
                <button
                  type="button"
                  onClick={() => {
                    if (cam.streamSource === "demo") {
                      cam.start();
                    } else {
                      cam.startDemoFeed();
                    }
                  }}
                  className="lc-call-btn lc-btn-switch"
                  title="Switch between Webcam and Demo Feed"
                >
                  <RefreshCw size={15} />
                  <span className="lc-call-label">{cam.streamSource === "demo" ? "Use Webcam" : "Use Demo"}</span>
                </button>

                {/* Visual Divider */}
                <div className="lc-call-divider" />

                {/* 6. End Call Button (Distinct Red Hang-Up Pill) */}
                <button
                  type="button"
                  onClick={cam.stop}
                  className="lc-call-btn lc-btn-end"
                  title="End video call"
                >
                  <PhoneOff size={16} />
                  <span>End Call</span>
                </button>
              </>
            ) : (
              <>
                <button
                  type="button"
                  onClick={() => cam.start()}
                  disabled={cam.status === "starting" || disabled}
                  className="lc-call-btn lc-btn-snap"
                >
                  <Video size={16} />
                  <span>Turn On Webcam</span>
                </button>
                <button
                  type="button"
                  onClick={cam.startDemoFeed}
                  disabled={cam.status === "starting" || disabled}
                  className="lc-call-btn lc-btn-media"
                >
                  <Sparkles size={15} className="text-teal-400" />
                  <span>Start Demo Call</span>
                </button>
              </>
            )}
          </div>
        </div>

        {/* Photo Studio Window (kept in DOM with toggle display) */}
        <div
          className="lc-photo-studio"
          style={{ display: mediaMode === "photos" ? "flex" : "none" }}
        >
          <div
            className="lc-photo-dropzone"
            onClick={() => fileInputRef.current?.click()}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => e.key === "Enter" && fileInputRef.current?.click()}
          >
            <Upload size={38} className="mx-auto mb-3 text-teal-400" />
            <p className="font-semibold text-base text-white mb-1">Share Pictures of Your Device</p>
            <p className="text-xs text-slate-400 mb-4 max-w-sm mx-auto">
              Upload clear photos or screenshots from your phone or PC. Sensora uses either live video or photos for
              diagnosis.
            </p>
            <div className="flex items-center justify-center gap-2.5 flex-wrap">
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  fileInputRef.current?.click();
                }}
                className="btn btn-primary btn-sm flex items-center gap-1.5 px-4 py-2"
              >
                <Upload size={15} />
                <span>Choose / Take Photos</span>
              </button>
              {cam.status === "live" && (
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    grab();
                  }}
                  className="btn btn-secondary btn-sm flex items-center gap-1.5 bg-slate-800 text-white border-slate-600"
                >
                  <Camera size={15} />
                  <span>Snap from Video Call</span>
                </button>
              )}
            </div>
          </div>
        </div>

        {/* Attached Pictures Thumbnail Tray */}
        {frames.length > 0 && (
          <div className="lc-thumbs p-2.5 bg-slate-900/90 border-t border-slate-800 flex items-center gap-2.5 flex-wrap">
            <span className="text-xs text-slate-300 font-medium mr-1">
              Attached ({frames.length}/{MAX_FRAMES}):
            </span>
            {frames.map((f) => (
              <figure key={f.id} className="relative m-0">
                <img
                  src={f.dataUrl}
                  alt="Attached frame"
                  className="h-14 w-auto rounded border border-slate-600 object-cover cursor-pointer hover:opacity-90"
                  onClick={() => window.open(f.dataUrl, "_blank")}
                  title="Click to view full image"
                />
                <button
                  type="button"
                  aria-label="Remove frame"
                  onClick={() => setFrames((fs) => fs.filter((x) => x.id !== f.id))}
                  className="absolute -top-1.5 -right-1.5 bg-rose-600 text-white rounded-full w-5 h-5 flex items-center justify-center text-xs font-bold shadow hover:bg-rose-700"
                >
                  ×
                </button>
              </figure>
            ))}
          </div>
        )}
      </section>

      <section className="lc-chat">
        <div className="lc-log" aria-live="polite">
          {lines.length === 0 && (
            <p className="lc-empty">Describe the problem by voice or text. Show or share pictures of the device when I ask.</p>
          )}
          {lines.map((l) => (
            <div key={l.id} className={`lc-line ${l.role}`}>
              {l.simulated && <span className="lc-tag">simulated</span>}
              <p className="m-0 leading-relaxed">{l.text}</p>
              {l.images && l.images.length > 0 && (
                <div className="lc-line-photos">
                  {l.images.map((imgSrc, idx) => (
                    <img
                      key={idx}
                      src={imgSrc}
                      alt={`Attached photo ${idx + 1}`}
                      className="lc-history-photo"
                      onClick={() => window.open(imgSrc, "_blank")}
                      title="Click to view full photo"
                    />
                  ))}
                </div>
              )}
            </div>
          ))}
          {busy !== "idle" && (
            <p className="lc-line assistant lc-busy">{busy === "transcribing" ? "Transcribing…" : "Thinking…"}</p>
          )}
          <div ref={endRef} />
        </div>

        {error && (
          <div className="lc-err" role="alert">
            {error.msg}
            {error.retry && lastSend.current && (
              <>
                {" "}
                <button onClick={() => lastSend.current?.()}>Retry</button>
              </>
            )}
          </div>
        )}
        {ptt.error && <p className="lc-err" role="alert">{ptt.error}</p>}
        {last?.warnings.map((w) => (
          <p key={w} className="lc-warn-text">
            {w}
          </p>
        ))}

        <div className="lc-row">
          <button
            className={ptt.state === "recording" ? "rec" : ""}
            onClick={toggleMic}
            disabled={!ptt.supported || busy !== "idle" || disabled}
            aria-pressed={ptt.state === "recording"}
          >
            {ptt.state === "recording" ? "Stop & transcribe" : "Speak"}
          </button>
          <input
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="Type or speak, then Send"
            onKeyDown={(e) => e.key === "Enter" && send()}
            aria-label="Your message"
            disabled={disabled}
          />
          <button onClick={() => send()} disabled={!draft.trim() || busy !== "idle" || disabled}>
            Send
          </button>
        </div>
        <div className="lc-row lc-sub">
          {tts.supported ? (
            <>
              <label>
                <input
                  type="checkbox"
                  checked={speakReplies}
                  onChange={(e) => {
                    setSpeakReplies(e.target.checked);
                    if (!e.target.checked) tts.stop();
                  }}
                />{" "}
                Speak replies
              </label>
              {tts.speaking && (
                <button className="secondary" onClick={tts.stop}>
                  Stop speaking
                </button>
              )}
            </>
          ) : (
            <span className="lc-note">Spoken replies aren't supported in this browser; replies are shown as text.</span>
          )}
          <span className="lc-note">Voice is record-then-transcribe, not live two-way speech.</span>
        </div>
      </section>

      <section className="lc-ai" aria-label="Sensora's analysis">
        {!resp ? (
          <p className="lc-empty">No analysis yet.</p>
        ) : (
          <>
            <StepStatus
              result={last}
              busy={busy !== "idle"}
              onDone={() => void send("I've done this step.", frames, "text", true)}
            />
            <h3>Current step</h3>
            {resp.current_step ? (
              <div className="lc-step">
                <strong>{resp.current_step.title}</strong>
                <p>{resp.current_step.instruction}</p>
                {resp.current_step.expected_result && (
                  <p className="lc-note">Expected: {resp.current_step.expected_result}</p>
                )}
              </div>
            ) : (
              <p className="lc-empty">
                {stopped
                  ? "No steps — safety stop."
                  : resp.escalation_recommended
                  ? "Safe checks finished."
                  : "No instruction yet."}
              </p>
            )}
            {resp.requires_new_image && (
              <p className="lc-hint">I need a (clearer/closer) camera view — capture a frame and send it.</p>
            )}
            {resp.verification_required && !resp.requires_new_image && (
              <p className="lc-hint">When done, show me the result so I can check it.</p>
            )}
            {resp.observations.length > 0 && (
              <>
                <h4>What I can see{last?.simulated ? " (simulated)" : ""}</h4>
                <ul>
                  {resp.observations.map((o) => (
                    <li key={o}>{o}</li>
                  ))}
                </ul>
              </>
            )}
            {resp.likely_causes.length > 0 && (
              <>
                <h4>Likely causes</h4>
                <ul>
                  {resp.likely_causes.map((c) => (
                    <li key={c.cause}>
                      {c.cause} <em>({c.likelihood})</em>
                    </li>
                  ))}
                </ul>
              </>
            )}
            <p className="lc-note">
              Confidence: {resp.confidence.level}
              {resp.confidence.note ? ` — ${resp.confidence.note}` : ""}
            </p>
            {resp.escalation_recommended && !stopped && (
              <p className="lc-hint">
                I recommend contacting a professional or the provider. Your session summary can be shared.
              </p>
            )}
          </>
        )}
      </section>
    </div>
  );
}
