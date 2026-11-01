import { useCallback, useEffect, useRef, useState } from "react";

export type PttState = "idle" | "recording";

/** Click-to-start / click-to-stop recording. Returns the raw recording; convert with blobToWav16k. */
export function usePushToTalk(maxMs = 60_000) {
  const [state, setState] = useState<PttState>("idle");
  const [error, setError] = useState<string | null>(null);
  const rec = useRef<MediaRecorder | null>(null);
  const chunks = useRef<Blob[]>([]);
  const timer = useRef<number | undefined>();
  const supported = typeof MediaRecorder !== "undefined" && !!navigator.mediaDevices?.getUserMedia;

  const release = () => { window.clearTimeout(timer.current); rec.current?.stream.getTracks().forEach((t) => t.stop()); };

  const start = useCallback(async () => {
    setError(null);
    if (!supported) { setError("Voice input isn't supported in this browser. Type your message instead."); return false; }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
      chunks.current = [];
      const r = new MediaRecorder(stream);
      r.ondataavailable = (e) => e.data.size && chunks.current.push(e.data);
      r.start();
      rec.current = r;
      timer.current = window.setTimeout(() => r.state === "recording" && r.stop(), maxMs);
      setState("recording");
      return true;
    } catch (e) {
      const n = (e as DOMException)?.name;
      setError(n === "NotAllowedError" ? "Microphone permission was denied. Allow it in your browser's site settings, or type instead."
        : n === "NotFoundError" ? "No microphone found. Type your message instead." : "The microphone could not be started.");
      return false;
    }
  }, [supported, maxMs]);

  const stop = useCallback((): Promise<Blob | null> => new Promise((resolve) => {
    const r = rec.current;
    if (!r) return resolve(null);
    const finish = () => { release(); setState("idle"); rec.current = null;
      resolve(chunks.current.length ? new Blob(chunks.current, { type: r.mimeType || "audio/webm" }) : null); };
    if (r.state === "inactive") return finish();
    r.onstop = finish; r.stop();
  }), []);

  const cancel = useCallback(() => { const r = rec.current; if (r && r.state !== "inactive") { r.onstop = null; r.stop(); } release(); rec.current = null; setState("idle"); }, []);
  useEffect(() => {
    return () => {
      cancel();
    };
  }, [cancel]);
  return { state, error, supported, start, stop, cancel };
}
