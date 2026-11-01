import { useCallback, useEffect, useRef, useState } from "react";

function describeMediaError(err: unknown, device: "camera" | "microphone"): string {
  const name = err instanceof DOMException ? err.name : "";
  if (name === "NotAllowedError" || name === "SecurityError")
    return `Permission to use the ${device} was denied. Allow access in your browser's site settings and try again.`;
  if (name === "NotFoundError" || name === "OverconstrainedError")
    return `No ${device} was found on this device.`;
  if (name === "NotReadableError")
    return `The ${device} is being used by another app. Close it and try again.`;
  return `Could not start the ${device}.`;
}

function mediaUnavailable(device: string): string | null {
  if (typeof navigator === "undefined" || !navigator.mediaDevices?.getUserMedia)
    return `The ${device} needs a secure connection (HTTPS or localhost) and a browser that supports it.`;
  return null;
}

export type CameraState = "off" | "starting" | "on" | "error";

/** Local camera preview. Frames never leave the browser in Milestone 1. */
export function useCamera() {
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const [state, setState] = useState<CameraState>("off");
  const [error, setError] = useState<string | null>(null);

  const stop = useCallback(() => {
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    if (videoRef.current) videoRef.current.srcObject = null;
    setState("off");
  }, []);

  const start = useCallback(async () => {
    const unavailable = mediaUnavailable("camera");
    if (unavailable) { setError(unavailable); setState("error"); return; }
    setState("starting");
    setError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: { ideal: "environment" } }, audio: false,
      });
      streamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play().catch(() => undefined);
      }
      setState("on");
    } catch (err) {
      setError(describeMediaError(err, "camera"));
      setState("error");
    }
  }, []);

  useEffect(() => {
    return () => {
      streamRef.current?.getTracks().forEach((t) => t.stop());
    };
  }, []);
  return { videoRef, state, error, start, stop };
}

export type MicState = "off" | "starting" | "live" | "muted" | "error";

/** Microphone access with a live level meter. No speech-to-text yet (Milestone 2). */
export function useMicrophone() {
  const streamRef = useRef<MediaStream | null>(null);
  const ctxRef = useRef<AudioContext | null>(null);
  const rafRef = useRef<number>(0);
  const [state, setState] = useState<MicState>("off");
  const [error, setError] = useState<string | null>(null);
  const [level, setLevel] = useState(0);

  const teardown = useCallback(() => {
    cancelAnimationFrame(rafRef.current);
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    void ctxRef.current?.close().catch(() => undefined);
    ctxRef.current = null;
    setLevel(0);
  }, []);

  const stop = useCallback(() => { teardown(); setState("off"); }, [teardown]);

  const start = useCallback(async () => {
    const unavailable = mediaUnavailable("microphone");
    if (unavailable) { setError(unavailable); setState("error"); return; }
    setState("starting");
    setError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
      streamRef.current = stream;
      const ctx = new AudioContext();
      ctxRef.current = ctx;
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 256;
      ctx.createMediaStreamSource(stream).connect(analyser);
      const data = new Uint8Array(analyser.frequencyBinCount);
      const tick = () => {
        analyser.getByteTimeDomainData(data);
        let peak = 0;
        for (const v of data) peak = Math.max(peak, Math.abs(v - 128));
        setLevel(Math.min(1, peak / 64));
        rafRef.current = requestAnimationFrame(tick);
      };
      tick();
      setState("live");
    } catch (err) {
      teardown();
      setError(describeMediaError(err, "microphone"));
      setState("error");
    }
  }, [teardown]);

  const toggleMute = useCallback(() => {
    const tracks = streamRef.current?.getAudioTracks() ?? [];
    if (tracks.length === 0) return;
    const muting = state === "live";
    tracks.forEach((t) => { t.enabled = !muting; });
    setState(muting ? "muted" : "live");
  }, [state]);

  useEffect(() => {
    return () => {
      teardown();
    };
  }, [teardown]);
  return { state, error, level, start, stop, toggleMute };
}
