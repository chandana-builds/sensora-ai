import { useCallback, useEffect, useRef, useState } from "react";
import { Camera, Image as ImageIcon, Mic, MicOff, Upload, Video, VideoOff } from "lucide-react";
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

  // Safe scroll effect with explicit void return (prevents Promise return error)
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [lines, busy]);

  // Automatically start camera on mount when entering Live Workspace
  useEffect(() => {
    if (!cameraAutoStarted.current && cam.supported && !disabled) {
      cameraAutoStarted.current = true;
      cam.start().catch(() => {});
    }
  }, [cam.supported, disabled]);

  const fail = (e: unknown) => setError({ msg: e instanceof Error ? e.message : "Something went wrong.",
    retry: e instanceof ApiError ? e.retryable : false });

  function grab() {
    setError(null);
    if (!cam.videoRef.current) return;
    if (frames.length >= MAX_FRAMES) return setError({ msg: `You can attach up to ${MAX_FRAMES} frames per message.`, retry: false });
    try { setFrames((f) => [...f, captureFrame(cam.videoRef.current!)]); } catch (e) { fail(e); }
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
        try { recognitionRef.current.stop(); } catch {}
      }
      setIsListening(false);
      return;
    }

    if (SpeechRec) {
      try {
        if (recognitionRef.current) {
          try { recognitionRef.current.abort(); } catch {}
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
    if (ptt.state === "idle") { tts.stop(); await ptt.start(); return; } // speaking is interrupted when the user talks
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
    } finally { setBusy("idle"); }
  }

  async function send(text = draft.trim(), attached = frames, mode = inputMode, done = false) {
    if (!text || busy !== "idle" || disabled) return;
    if (isListening && recognitionRef.current) {
      try { recognitionRef.current.stop(); } catch {}
      setIsListening(false);
    }
    tts.stop(); setError(null);
    lastSend.current = () => void send(text, attached, mode, done);
    const attachedImages = attached.map((f) => f.dataUrl);
    setLines((l) => [...l, { id: crypto.randomUUID(), role: "user", text, images: attachedImages }]);
    setDraft(""); setFrames([]); setBusy("thinking");
    try {
      const r = await postAgentTurn(sessionId, { text, input_mode: mode, frames: attached.map((f) => f.base64), user_level: userLevel, reported_step_done: done });
      setLast(r); setInputMode("text");
      setLines((l) => [...l, { id: r.assistant_message_id ?? crypto.randomUUID(), role: "assistant", text: r.response.assistant_message, simulated: r.simulated }]);
      if (speakReplies) tts.speak(r.response.assistant_message);
    } catch (e) { fail(e); } finally { setBusy("idle"); }
  }

  // Auto-trigger initial diagnostic turn with spoken voice if problem was reported
  useEffect(() => {
    if (initialTurnTriggered.current) return;
    const initialText = problemDescription?.trim() || (deviceName ? `I need help troubleshooting my ${deviceName}.` : "");
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
      {status && !status.simulated && <div className="lc-banner lc-ok">AI connected with real-time reasoning ({status.reasoning}).</div>}
      {stopped && <div className="lc-banner lc-stop" role="alert"><strong>Safety stop.</strong> {resp!.assistant_message}</div>}

      {/* Dual Mode Visual Inspection Window */}
      <section className="lc-cam-call card p-0 overflow-hidden relative shadow-lg border border-slate-200">
        <div className="lc-mode-tabs">
          <button
            type="button"
            onClick={() => setMediaMode("video")}
            className={`lc-mode-tab ${mediaMode === "video" ? "active" : ""}`}
            title="Real-time camera video stream"
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

        {mediaMode === "video" ? (
          <div className="relative">
            <div className="absolute top-3 left-3 z-10 flex items-center gap-2 bg-slate-900/80 backdrop-blur text-white px-3 py-1 rounded-full text-xs font-semibold">
              <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 animate-pulse" />
              <span>LIVE VIDEO CALL</span>
              <span className="text-slate-400">·</span>
              <span>{deviceName || "Device Inspection"}</span>
            </div>

            <video
              ref={cam.videoRef}
              autoPlay
              playsInline
              muted
              className="w-full bg-slate-950 object-cover min-h-[320px] max-h-[460px]"
              aria-label="Live camera video stream"
            />

            {cam.status !== "live" && (
              <div className="absolute inset-0 flex flex-col items-center justify-center bg-slate-900 text-slate-300 p-6 text-center">
                <Camera size={44} className="mb-3 text-slate-400 animate-pulse" />
                <p className="font-semibold text-lg text-white mb-1">
                  {cam.status === "starting" ? "Connecting camera feed…" : "Camera is currently inactive"}
                </p>
                <p className="text-sm text-slate-400 mb-4 max-w-sm">
                  Allow camera access in your browser so Sensora can inspect your device visual state.
                </p>
                <button
                  type="button"
                  onClick={() => cam.start()}
                  disabled={cam.status === "starting" || disabled}
                  className="btn btn-primary flex items-center gap-2 px-5 py-2.5"
                >
                  <Video size={18} />
                  <span>Turn On Video</span>
                </button>
              </div>
            )}

            {/* Video Call Floating Controls Bar */}
            <div className="absolute bottom-3 left-1/2 -translate-x-1/2 z-10 flex items-center gap-2 bg-slate-900/90 backdrop-blur-md px-4 py-2 rounded-2xl shadow-2xl border border-slate-700/50">
              {cam.status === "live" ? (
                <>
                  <button
                    type="button"
                    onClick={grab}
                    className="btn btn-primary btn-sm flex items-center gap-1.5 px-3 py-1.5 shadow"
                    title="Capture current camera view for AI inspection"
                  >
                    <Camera size={16} />
                    <span>Snap Frame ({frames.length}/{MAX_FRAMES})</span>
                  </button>
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm flex items-center gap-1.5 bg-slate-800 text-white border-slate-600 hover:bg-slate-700"
                    onClick={cam.stop}
                    title="Turn off camera"
                  >
                    <VideoOff size={15} />
                    <span>Stop</span>
                  </button>
                  {cam.devices.length > 1 && (
                    <select
                      aria-label="Choose camera"
                      value={cam.deviceId}
                      onChange={(e) => cam.switchTo(e.target.value)}
                      className="bg-slate-800 text-xs text-white border border-slate-600 rounded px-2 py-1"
                    >
                      {cam.devices.map((d, i) => (
                        <option key={d.deviceId} value={d.deviceId}>
                          {d.label || `Camera ${i + 1}`}
                        </option>
                      ))}
                    </select>
                  )}
                </>
              ) : (
                <button
                  type="button"
                  onClick={() => cam.start()}
                  disabled={cam.status === "starting" || disabled}
                  className="btn btn-primary btn-sm flex items-center gap-1.5 px-3 py-1.5"
                >
                  <Video size={16} />
                  <span>Enable Camera</span>
                </button>
              )}

              <div className="h-5 w-px bg-slate-700 mx-1" />

              {/* Live Voice Mic Toggle Button */}
              <button
                type="button"
                onClick={toggleListening}
                className={`btn btn-sm flex items-center gap-1.5 px-3 py-1.5 transition ${
                  isListening || ptt.state === "recording"
                    ? "bg-rose-600 hover:bg-rose-700 text-white animate-pulse"
                    : "bg-emerald-600 hover:bg-emerald-700 text-white"
                }`}
                title={isListening ? "Listening... click to stop" : "Speak to AI (voice recognition)"}
              >
                {isListening || ptt.state === "recording" ? <MicOff size={15} /> : <Mic size={15} />}
                <span>{isListening || ptt.state === "recording" ? "Listening…" : "Speak"}</span>
              </button>
            </div>
          </div>
        ) : (
          /* Photo Studio Window */
          <div className="lc-photo-studio">
            <div
              className="lc-photo-dropzone"
              onClick={() => fileInputRef.current?.click()}
              role="button"
              tabIndex={0}
              onKeyDown={(e) => e.key === "Enter" && fileInputRef.current?.click()}
            >
              <Upload size={38} className="mx-auto mb-3 text-teal-400" />
              <p className="font-semibold text-base text-white mb-1">
                Share Pictures of Your Device
              </p>
              <p className="text-xs text-slate-400 mb-4 max-w-sm mx-auto">
                Upload clear photos or screenshots from your phone or PC. Sensora uses either live video or photos for diagnosis.
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
                    <span>Snap from Camera</span>
                  </button>
                )}
              </div>
            </div>
          </div>
        )}

        {cam.error && <p className="lc-err p-3 bg-rose-50 border-t border-rose-200 text-rose-700 text-xs m-0" role="alert">{cam.error}</p>}

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
          {lines.length === 0 && <p className="lc-empty">Describe the problem by voice or text. Show or share pictures of the device when I ask.</p>}
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
          {busy !== "idle" && <p className="lc-line assistant lc-busy">{busy === "transcribing" ? "Transcribing…" : "Thinking…"}</p>}
          <div ref={endRef} />
        </div>

        {error && <div className="lc-err" role="alert">{error.msg}{error.retry && lastSend.current && <> <button onClick={() => lastSend.current?.()}>Retry</button></>}</div>}
        {ptt.error && <p className="lc-err" role="alert">{ptt.error}</p>}
        {last?.warnings.map((w) => <p key={w} className="lc-warn-text">{w}</p>)}

        <div className="lc-row">
          <button className={ptt.state === "recording" ? "rec" : ""} onClick={toggleMic} disabled={!ptt.supported || busy !== "idle" || disabled}
            aria-pressed={ptt.state === "recording"}>{ptt.state === "recording" ? "Stop & transcribe" : "Speak"}</button>
          <input value={draft} onChange={(e) => setDraft(e.target.value)} placeholder="Type or speak, then Send"
            onKeyDown={(e) => e.key === "Enter" && send()} aria-label="Your message" disabled={disabled} />
          <button onClick={() => send()} disabled={!draft.trim() || busy !== "idle" || disabled}>Send</button>
        </div>
        <div className="lc-row lc-sub">
          {tts.supported
            ? <><label><input type="checkbox" checked={speakReplies} onChange={(e) => { setSpeakReplies(e.target.checked); if (!e.target.checked) tts.stop(); }} /> Speak replies</label>
                {tts.speaking && <button className="secondary" onClick={tts.stop}>Stop speaking</button>}</>
            : <span className="lc-note">Spoken replies aren't supported in this browser; replies are shown as text.</span>}
          <span className="lc-note">Voice is record-then-transcribe, not live two-way speech.</span>
        </div>
      </section>

      <section className="lc-ai" aria-label="Sensora's analysis">
        {!resp ? <p className="lc-empty">No analysis yet.</p> : <>
          <StepStatus result={last} busy={busy !== "idle"} onDone={() => void send("I've done this step.", frames, "text", true)} />
          <h3>Current step</h3>
          {resp.current_step ? <div className="lc-step"><strong>{resp.current_step.title}</strong><p>{resp.current_step.instruction}</p>
            {resp.current_step.expected_result && <p className="lc-note">Expected: {resp.current_step.expected_result}</p>}</div>
            : <p className="lc-empty">{stopped ? "No steps — safety stop." : resp.escalation_recommended ? "Safe checks finished." : "No instruction yet."}</p>}
          {resp.requires_new_image && <p className="lc-hint">I need a (clearer/closer) camera view — capture a frame and send it.</p>}
          {resp.verification_required && !resp.requires_new_image && <p className="lc-hint">When done, show me the result so I can check it.</p>}
          {resp.observations.length > 0 && <><h4>What I can see{last?.simulated ? " (simulated)" : ""}</h4><ul>{resp.observations.map((o) => <li key={o}>{o}</li>)}</ul></>}
          {resp.likely_causes.length > 0 && <><h4>Likely causes</h4><ul>{resp.likely_causes.map((c) => <li key={c.cause}>{c.cause} <em>({c.likelihood})</em></li>)}</ul></>}
          <p className="lc-note">Confidence: {resp.confidence.level}{resp.confidence.note ? ` — ${resp.confidence.note}` : ""}</p>
          {resp.escalation_recommended && !stopped && <p className="lc-hint">I recommend contacting a professional or the provider. Your session summary can be shared.</p>}
        </>}
      </section>
    </div>
  );
}
