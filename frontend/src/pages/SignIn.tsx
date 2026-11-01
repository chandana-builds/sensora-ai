import React, { useState, useRef, useEffect } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { Eye, EyeOff, Lock, Mail, ArrowRight, ShieldCheck, AlertCircle, Clock } from "lucide-react";
import { useAuth } from "../context/AuthContext";
import { AuthApiError } from "../lib/auth";
import { useAuthCooldown } from "../hooks/useAuthCooldown";

export default function SignIn() {
  const { signIn, continueAsGuest, accountsEnabled, isAuthenticated, isLocalSupabase } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [rateLimitNotice, setRateLimitNotice] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isGuestLoading, setIsGuestLoading] = useState(false);

  const cooldown = useAuthCooldown("signin_attempt", 60);
  const isSubmittingRef = useRef(false);
  const isGuestRef = useRef(false);

  // Preserve destination
  const searchParams = new URLSearchParams(location.search);
  const redirectPath = searchParams.get("redirect") || "/dashboard";

  // Redirect if already authenticated
  useEffect(() => {
    if (isAuthenticated) {
      navigate(redirectPath, { replace: true });
    }
  }, [isAuthenticated, navigate, redirectPath]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (isSubmittingRef.current || isLoading || cooldown.isActive) {
      return;
    }

    const cleanEmail = email.trim();
    if (!cleanEmail || !password) {
      setError("Please enter both email address and password.");
      return;
    }

    isSubmittingRef.current = true;
    setError(null);
    setRateLimitNotice(null);
    setIsLoading(true);

    try {
      await signIn(cleanEmail, password);
      navigate(redirectPath, { replace: true });
    } catch (err: unknown) {
      if (err instanceof AuthApiError && (err.isEmailRateLimit || err.isRateLimit)) {
        cooldown.startCooldown(err.retryAfterSeconds || 60);
        setRateLimitNotice(err.message);
      } else if (err instanceof Error && /rate limit/i.test(err.message)) {
        cooldown.startCooldown(60);
        setRateLimitNotice(err.message);
      } else {
        setError(err instanceof Error ? err.message : "Unable to sign in. Please verify your credentials.");
      }
    } finally {
      setIsLoading(false);
      isSubmittingRef.current = false;
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
              <span>Sensora Secure Access</span>
              {isLocalSupabase && (
                <span className="badge badge-guest" style={{ marginLeft: "auto", textTransform: "none", fontSize: "0.72rem" }}>
                  Local Mailpit Dev
                </span>
              )}
            </div>
            <h1 className="auth-title">Sign in to your account</h1>
            <p className="auth-subtitle">
              Access your personalized troubleshooting dashboard and history.
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
                <span>Sign-In Rate Limit Active</span>
              </h4>
              <p>{rateLimitNotice}</p>
              {cooldown.isActive && (
                <p>
                  Sign in temporarily locked. You can try again in <strong>{cooldown.secondsLeft}s</strong>.
                </p>
              )}
            </div>
          )}

          {!accountsEnabled && (
            <div className="notice mb-4">
              <p className="font-medium text-slate-800 m-0">Development Demo Mode</p>
              <p className="text-xs text-slate-600 m-0 mt-1">
                Supabase credentials are not configured in this environment. You can enter directly using a private, isolated guest session.
              </p>
            </div>
          )}

          {accountsEnabled && (
            <form onSubmit={handleSubmit} className="auth-form">
              <div className="form-group">
                <label htmlFor="signin-email">Email address</label>
                <div className="input-wrap">
                  <Mail size={18} className="input-icon" />
                  <input
                    id="signin-email"
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
                <div className="label-row">
                  <label htmlFor="signin-password">Password</label>
                  <Link to="/forgot-password" className="text-xs text-accent hover:underline">
                    Forgot password?
                  </Link>
                </div>
                <div className="input-wrap">
                  <Lock size={18} className="input-icon" />
                  <input
                    id="signin-password"
                    type={showPassword ? "text" : "password"}
                    autoComplete="current-password"
                    required
                    placeholder="Enter your password"
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
                    <span>Signing in...</span>
                  </>
                ) : cooldown.isActive ? (
                  <>
                    <Clock size={16} />
                    <span>Wait {cooldown.secondsLeft}s before retrying</span>
                  </>
                ) : (
                  <>
                    <span>Sign in</span>
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
                <span>Creating guest workspace...</span>
              </>
            ) : (
              <span>Continue as Guest (No account needed)</span>
            )}
          </button>
          <p className="guest-explainer">
            Guest workspaces are cryptographically isolated and saved exclusively to your current browser.
          </p>

          {accountsEnabled && (
            <div className="auth-footer">
              <span>Don't have an account? </span>
              <Link to={`/signup${location.search}`} className="font-semibold text-accent hover:underline">
                Create one now
              </Link>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
