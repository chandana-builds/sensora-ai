import { useState, useEffect, useCallback, useRef } from "react";

/**
 * Custom hook to manage persistent cooldowns for authentication requests (resend email, retry rate-limited signup, etc.).
 * Stores expiry in sessionStorage so remounting or page reloading preserves the remaining cooldown duration.
 */
export function useAuthCooldown(key: string, defaultSeconds: number = 60) {
  const storageKey = `sensora_cooldown_${key}`;

  const getRemainingSeconds = useCallback(() => {
    try {
      const stored = sessionStorage.getItem(storageKey);
      if (!stored) return 0;
      const expiry = parseInt(stored, 10);
      if (isNaN(expiry)) return 0;
      const diff = Math.ceil((expiry - Date.now()) / 1000);
      return diff > 0 ? diff : 0;
    } catch {
      return 0;
    }
  }, [storageKey]);

  const [secondsLeft, setSecondsLeft] = useState<number>(getRemainingSeconds);
  const timerRef = useRef<number | null>(null);

  const clearCooldown = useCallback(() => {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
    try {
      sessionStorage.removeItem(storageKey);
    } catch {
      // ignore storage access errors
    }
    setSecondsLeft(0);
  }, [storageKey]);

  const startCooldown = useCallback(
    (durationSeconds: number = defaultSeconds) => {
      const expiry = Date.now() + Math.max(1, durationSeconds) * 1000;
      try {
        sessionStorage.setItem(storageKey, expiry.toString());
      } catch {
        // ignore
      }
      setSecondsLeft(Math.max(1, durationSeconds));

      if (timerRef.current) {
        clearInterval(timerRef.current);
      }

      timerRef.current = window.setInterval(() => {
        const remaining = Math.ceil((expiry - Date.now()) / 1000);
        if (remaining <= 0) {
          if (timerRef.current) {
            clearInterval(timerRef.current);
            timerRef.current = null;
          }
          try {
            sessionStorage.removeItem(storageKey);
          } catch {
            // ignore
          }
          setSecondsLeft(0);
        } else {
          setSecondsLeft(remaining);
        }
      }, 1000);
    },
    [defaultSeconds, storageKey]
  );

  useEffect(() => {
    const initial = getRemainingSeconds();
    setSecondsLeft(initial);
    if (initial <= 0) return;

    timerRef.current = window.setInterval(() => {
      const remaining = getRemainingSeconds();
      setSecondsLeft(remaining);
      if (remaining <= 0) {
        if (timerRef.current) {
          clearInterval(timerRef.current);
          timerRef.current = null;
        }
        try {
          sessionStorage.removeItem(storageKey);
        } catch {
          // ignore
        }
      }
    }, 1000);

    return () => {
      if (timerRef.current) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
    };
  }, [getRemainingSeconds, storageKey]);

  return {
    secondsLeft,
    isActive: secondsLeft > 0,
    startCooldown,
    clearCooldown,
  };
}
