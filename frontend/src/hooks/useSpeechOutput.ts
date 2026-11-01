import { useCallback, useEffect, useState } from "react";

/** Browser speech synthesis (one-way spoken replies; not full-duplex). */
export function useSpeechOutput() {
  const supported = typeof window !== "undefined" && "speechSynthesis" in window;
  const [speaking, setSpeaking] = useState(false);

  const stop = useCallback(() => { if (supported) window.speechSynthesis.cancel(); setSpeaking(false); }, [supported]);
  const speak = useCallback((text: string) => {
    if (!supported) return;
    window.speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(text.replace(/^\[Simulated demo\]\s*/, ""));
    u.lang = navigator.language || "en-US";
    u.onstart = () => setSpeaking(true);
    u.onend = u.onerror = () => setSpeaking(false);
    window.speechSynthesis.speak(u);
  }, [supported]);
  useEffect(() => {
    return () => {
      stop();
    };
  }, [stop]);
  return { supported, speaking, speak, stop };
}
