import { useCallback, useEffect, useRef, useState } from "react";

export type CameraStatus = "idle" | "starting" | "live" | "error";
export type StreamSource = "webcam" | "demo" | null;

function explain(e: unknown): string {
  const name = (e as DOMException)?.name;
  if (name === "NotAllowedError" || name === "SecurityError") {
    return "Camera permission was denied. Please allow camera access in your browser or switch to Demo Video Call.";
  }
  if (name === "NotFoundError" || name === "OverconstrainedError") {
    return "No physical webcam was found. You can use our interactive Demo Video Call to test Sensora AI.";
  }
  if (name === "NotReadableError") {
    return "The camera is currently in use by another application.";
  }
  return "Could not connect to camera. You can try again or use Demo Video Call.";
}

export function useLiveCamera() {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const demoCleanupRef = useRef<(() => void) | null>(null);
  const [status, setStatus] = useState<CameraStatus>("idle");
  const [streamSource, setStreamSource] = useState<StreamSource>(null);
  const [error, setError] = useState<string | null>(null);
  const [isVideoMuted, setIsVideoMuted] = useState(false);
  const [devices, setDevices] = useState<MediaDeviceInfo[]>([]);
  const [deviceId, setDeviceId] = useState<string | undefined>();
  const supported = typeof navigator !== "undefined" && !!navigator.mediaDevices?.getUserMedia;

  // Cleanly stop any active streams and demo animations
  const stop = useCallback(() => {
    if (demoCleanupRef.current) {
      demoCleanupRef.current();
      demoCleanupRef.current = null;
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }
    if (videoRef.current) {
      videoRef.current.srcObject = null;
    }
    setStatus("idle");
    setStreamSource(null);
    setIsVideoMuted(false);
  }, []);

  // Helper to attach stream to the video element and ensure playback
  const attachStreamToVideo = useCallback((stream: MediaStream) => {
    const video = videoRef.current;
    if (!video) return;
    video.srcObject = stream;
    video.muted = true;
    video.playsInline = true;
    video.setAttribute("playsinline", "true");
    video.setAttribute("webkit-playsinline", "true");

    const playPromise = () => {
      video.play().catch((err) => {
        console.warn("Camera auto-play pending user gesture or metadata:", err);
      });
    };

    video.onloadedmetadata = () => {
      playPromise();
    };

    // Also call directly in case metadata is already loaded
    playPromise();
  }, []);

  // Start real webcam stream with robust fallback
  const start = useCallback(async (id?: string) => {
    if (!supported) {
      setStatus("error");
      setError("This browser doesn't support camera access (requires HTTPS or localhost). Try Demo Video Call.");
      return;
    }

    // Stop previous streams
    stop();
    setStatus("starting");
    setError(null);

    let stream: MediaStream | null = null;
    try {
      // First try standard HD constraints with preferred camera
      stream = await navigator.mediaDevices.getUserMedia({
        video: id
          ? { deviceId: { exact: id } }
          : { facingMode: { ideal: "environment" }, width: { ideal: 1280 }, height: { ideal: 720 } },
        audio: false,
      });
    } catch {
      // Fallback: simple { video: true } in case facingMode or resolution was rejected
      try {
        stream = await navigator.mediaDevices.getUserMedia({
          video: id ? { deviceId: { exact: id } } : true,
          audio: false,
        });
      } catch (err) {
        setStatus("error");
        setError(explain(err));
        return;
      }
    }

    if (!stream) {
      setStatus("error");
      setError("Could not initialize video stream.");
      return;
    }

    streamRef.current = stream;
    setStreamSource("webcam");
    attachStreamToVideo(stream);

    const track = stream.getVideoTracks()[0];
    if (track) {
      track.addEventListener("ended", () => {
        setStatus("error");
        setError("The camera connection was disconnected.");
      });
      setDeviceId(track.getSettings().deviceId ?? id);
    }

    try {
      const allDevices = await navigator.mediaDevices.enumerateDevices();
      setDevices(allDevices.filter((d) => d.kind === "videoinput"));
    } catch {}

    setStatus("live");
    setIsVideoMuted(false);
  }, [supported, stop, attachStreamToVideo]);

  // Start a simulated 30fps animated video call stream (ideal for testing & devices without webcam)
  const startDemoFeed = useCallback(() => {
    stop();
    setStatus("starting");
    setError(null);

    const canvas = document.createElement("canvas");
    canvas.width = 1280;
    canvas.height = 720;
    const ctx = canvas.getContext("2d");
    if (!ctx) {
      setStatus("error");
      setError("Canvas rendering unavailable.");
      return;
    }

    let animId = 0;
    let t = 0;

    const render = () => {
      t += 0.04;
      // Background gradient
      ctx.fillStyle = "#090d16";
      ctx.fillRect(0, 0, 1280, 720);

      // Grid lines
      ctx.strokeStyle = "rgba(35, 196, 166, 0.12)";
      ctx.lineWidth = 1;
      for (let x = 0; x < 1280; x += 48) {
        ctx.beginPath();
        ctx.moveTo(x, 0);
        ctx.lineTo(x, 720);
        ctx.stroke();
      }
      for (let y = 0; y < 720; y += 48) {
        ctx.beginPath();
        ctx.moveTo(0, y);
        ctx.lineTo(1280, y);
        ctx.stroke();
      }

      // Simulated Hardware Device Chassis (e.g. Wi-Fi Router / Smart Audio Unit)
      ctx.fillStyle = "#1e293b";
      ctx.beginPath();
      if ((ctx as any).roundRect) {
        (ctx as any).roundRect(320, 240, 640, 260, 20);
      } else {
        ctx.rect(320, 240, 640, 260);
      }
      ctx.fill();
      ctx.strokeStyle = "#334155";
      ctx.lineWidth = 3;
      ctx.stroke();

      // Dual Antennas
      ctx.fillStyle = "#0f172a";
      ctx.fillRect(400, 110, 22, 130);
      ctx.fillRect(858, 110, 22, 130);

      // Indicator LED panel
      const leds = [
        { label: "PWR", color: "#10b981", active: true },
        { label: "WAN", color: Math.sin(t * 3) > 0 ? "#10b981" : "#f59e0b", active: true },
        { label: "WIFI", color: "#10b981", active: true },
        { label: "ETH 1", color: "#64748b", active: false },
        { label: "ETH 2", color: "#10b981", active: true },
        { label: "AUDIO", color: Math.sin(t * 2) > 0 ? "#38bdf8" : "#10b981", active: true },
      ];

      leds.forEach((led, idx) => {
        const lx = 375 + idx * 95;
        const ly = 370;
        ctx.fillStyle = led.active ? led.color : "#334155";
        ctx.beginPath();
        ctx.arc(lx, ly, 9, 0, Math.PI * 2);
        ctx.fill();
        if (led.active) {
          ctx.strokeStyle = led.color;
          ctx.lineWidth = 2;
          ctx.beginPath();
          ctx.arc(lx, ly, 15, 0, Math.PI * 2);
          ctx.stroke();
        }
        ctx.fillStyle = "#94a3b8";
        ctx.font = "bold 13px system-ui, sans-serif";
        ctx.textAlign = "center";
        ctx.fillText(led.label, lx, ly + 34);
      });

      // Animated Vision Scanning Line
      const scanY = 180 + ((Math.sin(t) + 1) / 2) * 360;
      const grad = ctx.createLinearGradient(0, scanY - 25, 0, scanY + 25);
      grad.addColorStop(0, "rgba(35, 196, 166, 0)");
      grad.addColorStop(0.5, "rgba(35, 196, 166, 0.45)");
      grad.addColorStop(1, "rgba(35, 196, 166, 0)");
      ctx.fillStyle = grad;
      ctx.fillRect(300, scanY - 25, 680, 50);

      ctx.strokeStyle = "#23c4a6";
      ctx.lineWidth = 2.5;
      ctx.beginPath();
      ctx.moveTo(300, scanY);
      ctx.lineTo(980, scanY);
      ctx.stroke();

      // Bounding box overlay for AI visual detection
      ctx.strokeStyle = "#38bdf8";
      ctx.lineWidth = 2;
      ctx.setLineDash([6, 6]);
      ctx.strokeRect(345, 330, 590, 100);
      ctx.setLineDash([]);
      ctx.fillStyle = "#38bdf8";
      ctx.font = "bold 13px monospace";
      ctx.textAlign = "left";
      ctx.fillText("[SENSORA VISION: DETECTED HARDWARE INTERFACE & LED STATUS]", 350, 320);

      // Top Diagnostics Header
      ctx.fillStyle = "rgba(15, 23, 42, 0.85)";
      ctx.fillRect(0, 0, 1280, 52);
      ctx.fillStyle = "#23c4a6";
      ctx.font = "bold 15px monospace";
      ctx.fillText("● SENSORA AI VIDEO CALL · REAL-TIME CAMERA STREAM", 30, 33);

      ctx.fillStyle = "#94a3b8";
      ctx.font = "14px monospace";
      ctx.textAlign = "right";
      const nowStr = new Date().toISOString().replace("T", " ").substring(0, 19);
      ctx.fillText(`30 FPS · 720p HD · ${nowStr}`, 1250, 33);

      animId = requestAnimationFrame(render);
    };

    render();

    // Capture 30fps stream from canvas
    const captureStream = (canvas as any).captureStream ? (canvas as any).captureStream(30) : null;
    if (!captureStream) {
      cancelAnimationFrame(animId);
      setStatus("error");
      setError("Video stream creation is unsupported in this environment.");
      return;
    }

    demoCleanupRef.current = () => {
      cancelAnimationFrame(animId);
      captureStream.getTracks().forEach((trk: MediaStreamTrack) => trk.stop());
    };

    streamRef.current = captureStream;
    setStreamSource("demo");
    attachStreamToVideo(captureStream);
    setStatus("live");
    setIsVideoMuted(false);
  }, [stop, attachStreamToVideo]);

  // Toggle video track mute/pause
  const toggleMuteVideo = useCallback(() => {
    if (!streamRef.current) return;
    const tracks = streamRef.current.getVideoTracks();
    if (tracks.length > 0) {
      const nextMuted = !isVideoMuted;
      tracks.forEach((t) => {
        t.enabled = !nextMuted;
      });
      setIsVideoMuted(nextMuted);
    }
  }, [isVideoMuted]);

  // Explicit play trigger in case browser paused video element
  const playVideo = useCallback(async () => {
    if (videoRef.current) {
      try {
        await videoRef.current.play();
      } catch (err) {
        console.warn("Manual video play trigger failed:", err);
      }
    }
  }, []);

  // Keep video element synced when component remounts or status is live
  useEffect(() => {
    if (status === "live" && streamRef.current && videoRef.current) {
      if (videoRef.current.srcObject !== streamRef.current) {
        attachStreamToVideo(streamRef.current);
      }
    }
  }, [status, attachStreamToVideo]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      stop();
    };
  }, [stop]);

  return {
    videoRef,
    status,
    streamSource,
    error,
    isVideoMuted,
    devices,
    deviceId,
    supported,
    start,
    startDemoFeed,
    toggleMuteVideo,
    playVideo,
    stop,
    switchTo: start,
  };
}
