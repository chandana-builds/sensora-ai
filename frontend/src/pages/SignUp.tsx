import React, { useState, useRef, useEffect } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import {
  Eye,
  EyeOff,
  Lock,
  Mail,
  User,
  ArrowRight,
  ShieldCheck,
  AlertCircle,
  CheckCircle,
  Clock,
  RefreshCw,
} from "lucide-react";
import { useAuth } from "../context/AuthContext";
import { AuthApiError } from "../lib/auth";
import { useAuthCooldown } from "../hooks/useAuthCooldown";

export default function SignUp() {
  const {
    signUp,
    continueAsGuest,
    accountsEnabled,
    isAuthenticated,
    resendVerification,
    isLocalSupabase,
    localMailpitUrl,
  } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  // Form field states - preserved during errors and rate-limits
  const [displayName, setDisplayName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);

  // Status and feedback states
  const [error, setError] = useState<string | null>(null);
  const [rateLimitNotice, setRateLimitNotice] = useState<string | null>(null);
  const [confirmationNeeded, setConfirmationNeeded] = useState(false);
  const [resendSuccess, setResendSuccess] = useState(false);
  const [resendError, setResendError] = useState<string | null>(null);

  // Loading states
  const [isLoading, setIsLoading] = useState(false);
  const [isResending, setIsResending] = useState(false);
  const [isGuestLoading, setIsGuestLoading] = useState(false);

  // Persistent cooldowns (stored in sessionStorage to survive refresh or remount)
  const cooldown = useAuthCooldown("signup_attempt", 60);
  const resendCooldown = useAuthCooldown("resend_attempt", 60);

  // Synchronous submission lock refs to block double-clicks/rapid enters before React re-renders
  const isSubmittingRef = useRef(false);
  const isResendingRef = useRef(false);
  const isGuestRef = useRef(false);

  const searchParams = new URLSearchParams(location.search);
  const redirectPath = searchParams.get("redirect") || "/dashboard";

  useEffect(() => {
    if (isAuthenticated) {
      navigate(redirectPath, { replace: true });
    }
  }, [isAuthenticated, navigate, redirectPath]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    // Prevent duplicate requests from repeated clicks, effects, or active cooldown
    if (isSubmittingRef.current || isLoading || cooldown.isActive) {
      return;
    }

    const cleanEmail = email.trim();
    if (!cleanEmail || !password) {
      setError("Please provide both an email address and a password.");
      return;
    }
    if (password.length < 8) {
      setError("Password must be at least 8 characters long.");
      return;
    }

    isSubmittingRef.current = true;
    setError(null);
    setRateLimitNotice(null);
    setIsLoading(true);

    try {
      const autoSignedIn = await signUp(cleanEmail, password, displayName.trim() || undefined);
      if (autoSignedIn) {
        navigate(redirectPath, { replace: true });
      } else {
        setConfirmationNeeded(true);
        // Start resend cooldown right after confirmation email is triggered
        resendCooldown.startCooldown(60);
      }
    } catch (err: unknown) {
      if (err instanceof AuthApiError && (err.isEmailRateLimit || err.isRateLimit)) {
        cooldown.startCooldown(err.retryAfterSeconds || 60);
        setRateLimitNotice(err.message);
      } else if (err instanceof Error && /rate limit/i.test(err.message)) {
        cooldown.startCooldown(60);
        setRateLimitNotice(err.message);
      } else {
        setError(err instanceof Error ? err.message : "Unable to register account. Please try again.");
      }
    } finally {
      setIsLoading(false);
      isSubmittingRef.current = false;
    }
  };

  const handleResend = async () => {
    if (isResendingRef.current || isResending || resendCooldown.isActive || !email.trim()) {
      return;
    }

    isResendingRef.current = true;
    setResendError(null);
    setResendSuccess(false);
    setIsResending(true);

    try {
      await resendVerification(email.trim());
      setResendSuccess(true);
      resendCooldown.startCooldown(60);
    } catch (err: unknown) {
      if (err instanceof AuthApiError && (err.isEmailRateLimit || err.isRateLimit)) {
        resendCooldown.startCooldown(err.retryAfterSeconds || 60);
        setResendError(err.message);
      } else if (err instanceof Error && /rate limit/i.test(err.message)) {
        resendCooldown.startCooldown(60);
        setResendError(err.message);
      } else {
        setResendError(err instanceof Error ? err.message : "Failed to resend confirmation email.");
      }
    } finally {
      setIsResending(false);
      isResendingRef.current = false;
    }
  };

  const handleGuest = async () => {
    if (isGuestRef.current || isGuestLoading) return;
    isGuestRef.current = true;
    setError(null);
    setRateLimitNotice(null);
    setIsGuestLoading(true);

    try {
      await continueAsGuest();
      navigate(redirectPath, { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Guest access failed. Please try again.");
    } finally {
      setIsGuestLoading(false);
      isGuestRef.current = false;
    }
  };

  return (
    <div className="auth-page">
      <div className="auth-container">
        <div className="auth-card">
          <div className="auth-header">
            <div className="auth-brand-badge">
              <ShieldCheck size={20} className="text-accent" />
              <span>Sensora Secure Registration</span>
              {isLocalSupabase && (
                <span className="badge badge-guest" style={{ marginLeft: "auto", textTransform: "none", fontSize: "0.72rem" }}>
                  Local Mailpit Dev
                </span>
              )}
            </div>
            <h1 className="auth-title">Create your account</h1>
            <p className="auth-subtitle">
              Save your device models, custom preferences, and full troubleshooting histories.
            </p>
          </div>

          {error && (
            <div className="auth-error-alert" role="alert">
              <AlertCircle size={18} className="flex-shrink-0" />
              <span>{error}</span>
            </div>
          )}

          {rateLimitNotice && (
            <div className="auth-rate-limit-alert" role="alert">
              <h4>
                <Clock size={18} />
                <span>Email Delivery Rate Limit Reached</span>
              </h4>
              <p>{rateLimitNotice}</p>
              {cooldown.isActive && (
                <p>
                  Submission temporarily locked. You can retry in <strong>{cooldown.secondsLeft}s</strong>.
                </p>
              )}
              <div className="dev-hint">
                <strong>Developer Note:</strong> Supabase's default shared SMTP allows ~3-4 emails/hr on free tier. To test locally without limits, run local Supabase with Mailpit or configure Custom SMTP in <em>Supabase Dashboard → Authentication → SMTP Settings</em>.
              </div>
            </div>
          )}

          {confirmationNeeded ? (
            <div className="auth-success-card">
              <CheckCircle size={36} className="text-emerald-600 mb-2" />
              <h2 className="text-lg font-bold text-slate-900">Confirmation email sent</h2>
              <p className="text-sm text-slate-600 mb-4 leading-relaxed">
                We've sent a verification link to <strong>{email}</strong>. Please click the link to activate your account, then sign in.
              </p>

              {isLocalSupabase && (
                <div className="notice mb-4" style={{ background: "#ecfdf5", borderColor: "#10b981", textAlign: "left" }}>
                  <p className="text-xs font-bold text-emerald-900 m-0">
                    Local Email Testing (Mailpit / Inbucket)
                  </p>
                  <p className="text-xs text-emerald-800 m-0 mt-1 leading-relaxed">
                    Email captured locally. Open your Mailpit inbox to view the email and click the confirmation link:
                  </p>
                  <div className="mt-2">
                    <a
                      href={localMailpitUrl}
                      target="_blank"
                      rel="noreferrer"
                      className="btn btn-primary btn-small inline-flex items-center gap-1"
                    >
                      <span>Open Mailpit Inbox (Port 54324)</span>
                      <ArrowRight size={14} />
                    </a>
                  </div>
                </div>
              )}

              {resendSuccess && (
                <div className="notice mb-4" style={{ background: "var(--accent-soft)", borderColor: "var(--accent)" }}>
                  <p className="text-xs font-semibold text-accent m-0">
                    A fresh confirmation email has been dispatched. Please check your inbox and spam folder.
                  </p>
                </div>
              )}

              {resendError && (
                <div className="auth-rate-limit-alert mb-4" role="alert">
                  <h4>
                    <Clock size={16} />
                    <span>Resend Delayed</span>
                  </h4>
                  <p>{resendError}</p>
                </div>
              )}

              <div className="flex flex-col gap-2 mb-4">
                <button
                  type="button"
                  className="btn btn-secondary btn-block"
                  onClick={handleResend}
                  disabled={isResending || resendCooldown.isActive}
                >
                  {isResending ? (
                    <>
                      <span className="spinner spinner-sm" />
                      <span>Sending verification email...</span>
                    </>
                  ) : resendCooldown.isActive ? (
                    <>
                      <Clock size={16} />
                      <span>Resend available in {resendCooldown.secondsLeft}s</span>
                    </>
                  ) : (
                    <>
                      <RefreshCw size={16} />
                      <span>Resend verification email</span>
                    </>
                  )}
                </button>

                <Link to={`/signin${location.search}`} className="btn btn-primary btn-block">
                  Return to Sign In
                </Link>
              </div>

              <div className="text-xs text-slate-500 text-center">
                Need immediate access while waiting?{" "}
                <button
                  type="button"
                  onClick={handleGuest}
                  disabled={isGuestLoading}
                  className="text-accent underline font-medium hover:text-accent-strong cursor-pointer"
                >
                  Continue as Guest
                </button>
              </div>
            </div>
          ) : (
            <>
              {!accountsEnabled && (
                <div className="notice mb-4">
                  <p className="font-medium text-slate-800 m-0">Development Demo Mode</p>
                  <p className="text-xs text-slate-600 m-0 mt-1">
                    Supabase accounts are not configured. Click below to continue with an isolated guest session.
                  </p>
                </div>
              )}

              {accountsEnabled && (
                <form onSubmit={handleSubmit} className="auth-form">
                  <div className="form-group">
                    <label htmlFor="signup-name">Display Name (Optional)</label>
                    <div className="input-wrap">
                      <User size={18} className="input-icon" />
                      <input
                        id="signup-name"
                        type="text"
                        autoComplete="name"
                        placeholder="e.g. Alex"
                        value={displayName}
                        onChange={(e) => setDisplayName(e.target.value)}
                        disabled={isLoading || cooldown.isActive}
                      />
                    </div>
                  </div>

                  <div className="form-group">
                    <label htmlFor="signup-email">Email address</label>
                    <div className="input-wrap">
                      <Mail size={18} className="input-icon" />
                      <input
                        id="signup-email"
                        type="email"
                        autoComplete="email"
                        required
                        placeholder="name@example.com"
                        value={email}
                        onChange={(e) => setEmail(e.target.value)}
                        disabled={isLoading || cooldown.isActive}
                      />
                    </div>
                  </div>

                  <div className="form-group">
                    <label htmlFor="signup-password">Password (minimum 8 characters)</label>
                    <div className="input-wrap">
                      <Lock size={18} className="input-icon" />
                      <input
                        id="signup-password"
                        type={showPassword ? "text" : "password"}
                        autoComplete="new-password"
                        required
                        minLength={8}
                        placeholder="Create a strong password"
                        value={password}
                        onChange={(e) => setPassword(e.target.value)}
                        disabled={isLoading || cooldown.isActive}
                      />
                      <button
                        type="button"
                        className="password-toggle-btn"
                        onClick={() => setShowPassword(!showPassword)}
                        aria-label={showPassword ? "Hide password" : "Show password"}
                      >
                        {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                      </button>
                    </div>
                  </div>

                  <button
                    type="submit"
                    className="btn btn-primary btn-block"
                    disabled={isLoading || isGuestLoading || cooldown.isActive}
                  >
                    {isLoading ? (
                      <>
                        <span className="spinner spinner-sm" />
                        <span>Creating account...</span>
                      </>
                    ) : cooldown.isActive ? (
                      <>
                        <Clock size={16} />
                        <span>Wait {cooldown.secondsLeft}s before retrying</span>
                      </>
                    ) : rateLimitNotice ? (
                      <>
                        <span>Retry Create Account</span>
                        <ArrowRight size={16} />
                      </>
                    ) : (
                      <>
                        <span>Create Account</span>
                        <ArrowRight size={16} />
                      </>
                    )}
                  </button>
                </form>
              )}

              <div className="auth-divider">
                <span>or</span>
              </div>

              <button
                type="button"
                className="btn btn-secondary btn-block guest-btn"
                onClick={handleGuest}
                disabled={isGuestLoading || isLoading}
              >
                {isGuestLoading ? (
                  <>
                    <span className="spinner spinner-sm" />
                    <span>Preparing workspace...</span>
                  </>
                ) : (
                  <span>Continue as Guest</span>
                )}
              </button>

              <div className="auth-footer">
                <span>Already have an account? </span>
                <Link to={`/signin${location.search}`} className="font-semibold text-accent hover:underline">
                  Sign in
                </Link>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
