import { useCallback, useEffect, useRef, useState } from "react";

export type CameraStatus = "idle" | "starting" | "live" | "error";

function explain(e: unknown): string {
  const name = (e as DOMException)?.name;
  if (name === "NotAllowedError" || name === "SecurityError") return "Camera permission was denied. Allow camera access in your browser's site settings and try again.";
  if (name === "NotFoundError" || name === "OverconstrainedError") return "No usable camera was found.";
  if (name === "NotReadableError") return "The camera is in use by another app.";
  return "The camera could not be started.";
}

export function useLiveCamera() {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const [status, setStatus] = useState<CameraStatus>("idle");
  const [error, setError] = useState<string | null>(null);
  const [devices, setDevices] = useState<MediaDeviceInfo[]>([]);
  const [deviceId, setDeviceId] = useState<string | undefined>();
  const supported = typeof navigator !== "undefined" && !!navigator.mediaDevices?.getUserMedia;

  const stop = useCallback(() => {
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    if (videoRef.current) videoRef.current.srcObject = null;
    setStatus("idle");
  }, []);

  const start = useCallback(async (id?: string) => {
    if (!supported) { setStatus("error"); setError("This browser doesn't support camera access (needs HTTPS or localhost)."); return; }
    streamRef.current?.getTracks().forEach((t) => t.stop());
    setStatus("starting"); setError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: id ? { deviceId: { exact: id } } : { facingMode: { ideal: "environment" } }, audio: false });
      streamRef.current = stream;
      if (videoRef.current) { videoRef.current.srcObject = stream; await videoRef.current.play().catch(() => undefined); }
      const track = stream.getVideoTracks()[0];
      track.addEventListener("ended", () => { setStatus("error"); setError("The camera connection was lost."); });
      setDeviceId(track.getSettings().deviceId ?? id);
      setDevices((await navigator.mediaDevices.enumerateDevices()).filter((d) => d.kind === "videoinput"));
      setStatus("live");
    } catch (e) { setStatus("error"); setError(explain(e)); }
  }, [supported]);

  useEffect(() => {
    return () => {
      stop();
    };
  }, [stop]);
  return { videoRef, status, error, devices, deviceId, supported, start, stop, switchTo: start };
}
