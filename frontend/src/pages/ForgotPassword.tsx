import React, { useState, useRef } from "react";
import { Link } from "react-router-dom";
import { ArrowLeft, ArrowRight, CheckCircle, Mail, AlertCircle, KeyRound, Clock, RefreshCw } from "lucide-react";
import { useAuth } from "../context/AuthContext";
import { AuthApiError } from "../lib/auth";
import { useAuthCooldown } from "../hooks/useAuthCooldown";

export default function ForgotPassword() {
  const { resetPassword, accountsEnabled, isLocalSupabase, localMailpitUrl } = useAuth();
  const [email, setEmail] = useState("");
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [rateLimitNotice, setRateLimitNotice] = useState<string | null>(null);
  const [resendSuccess, setResendSuccess] = useState(false);
  const [isLoading, setIsLoading] = useState(false);

  const cooldown = useAuthCooldown("password_reset", 60);
  const isSubmittingRef = useRef(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (isSubmittingRef.current || isLoading || cooldown.isActive) {
      return;
    }

    const cleanEmail = email.trim();
    if (!cleanEmail) {
      setError("Please enter your registered email address.");
      return;
    }

    isSubmittingRef.current = true;
    setError(null);
    setRateLimitNotice(null);
    setResendSuccess(false);
    setIsLoading(true);

    try {
      await resetPassword(cleanEmail);
      setSubmitted(true);
      cooldown.startCooldown(60);
    } catch (err: unknown) {
      if (err instanceof AuthApiError && (err.isEmailRateLimit || err.isRateLimit)) {
        cooldown.startCooldown(err.retryAfterSeconds || 60);
        setRateLimitNotice(err.message);
      } else if (err instanceof Error && /rate limit/i.test(err.message)) {
        cooldown.startCooldown(60);
        setRateLimitNotice(err.message);
      } else {
        setError(err instanceof Error ? err.message : "Failed to send reset instructions. Please check the address.");
      }
    } finally {
      setIsLoading(false);
      isSubmittingRef.current = false;
    }
  };

  const handleResend = async () => {
    if (isSubmittingRef.current || isLoading || cooldown.isActive || !email.trim()) {
      return;
    }

    isSubmittingRef.current = true;
    setError(null);
    setRateLimitNotice(null);
    setResendSuccess(false);
    setIsLoading(true);

    try {
      await resetPassword(email.trim());
      setResendSuccess(true);
      cooldown.startCooldown(60);
    } catch (err: unknown) {
      if (err instanceof AuthApiError && (err.isEmailRateLimit || err.isRateLimit)) {
        cooldown.startCooldown(err.retryAfterSeconds || 60);
        setRateLimitNotice(err.message);
      } else if (err instanceof Error && /rate limit/i.test(err.message)) {
        cooldown.startCooldown(60);
        setRateLimitNotice(err.message);
      } else {
        setError(err instanceof Error ? err.message : "Failed to resend reset email.");
      }
    } finally {
      setIsLoading(false);
      isSubmittingRef.current = false;
    }
  };

  return (
    <div className="auth-page">
      <div className="auth-container">
        <div className="auth-card">
          <div className="auth-header">
            <div className="auth-brand-badge">
              <KeyRound size={20} className="text-accent" />
              <span>Password Recovery</span>
              {isLocalSupabase && (
                <span className="badge badge-guest" style={{ marginLeft: "auto", textTransform: "none", fontSize: "0.72rem" }}>
                  Local Mailpit Dev
                </span>
              )}
            </div>
            <h1 className="auth-title">Reset your password</h1>
            <p className="auth-subtitle">
              Enter your account's email address and we'll send you a secure recovery link.
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

          {!accountsEnabled ? (
            <div className="notice mb-4">
              <p className="font-medium text-slate-800 m-0">Demo Mode Active</p>
              <p className="text-xs text-slate-600 m-0 mt-1">
                Password recovery requires an active Supabase Auth configuration. In demo mode, sessions use isolated tokens.
              </p>
              <div className="mt-3">
                <Link to="/signin" className="btn btn-secondary btn-small">
                  Back to Sign In
                </Link>
              </div>
            </div>
          ) : submitted ? (
            <div className="auth-success-card">
              <CheckCircle size={36} className="text-emerald-600 mb-2" />
              <h2 className="text-lg font-bold text-slate-900">Reset instructions sent</h2>
              <p className="text-sm text-slate-600 mb-4 leading-relaxed">
                If an account exists for <strong>{email}</strong>, you will receive an email shortly with instructions to reset your password.
              </p>

              {isLocalSupabase && (
                <div className="notice mb-4" style={{ background: "#ecfdf5", borderColor: "#10b981", textAlign: "left" }}>
                  <p className="text-xs font-bold text-emerald-900 m-0">
                    Local Email Testing (Mailpit / Inbucket)
                  </p>
                  <p className="text-xs text-emerald-800 m-0 mt-1 leading-relaxed">
                    Reset email captured locally. Open Mailpit to inspect the recovery link:
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
                    A fresh recovery link has been dispatched to your email.
                  </p>
                </div>
              )}

              <div className="flex flex-col gap-2 mb-4">
                <button
                  type="button"
                  className="btn btn-secondary btn-block"
                  onClick={handleResend}
                  disabled={isLoading || cooldown.isActive}
                >
                  {isLoading ? (
                    <>
                      <span className="spinner spinner-sm" />
                      <span>Sending reset email...</span>
                    </>
                  ) : cooldown.isActive ? (
                    <>
                      <Clock size={16} />
                      <span>Resend available in {cooldown.secondsLeft}s</span>
                    </>
                  ) : (
                    <>
                      <RefreshCw size={16} />
                      <span>Resend recovery email</span>
                    </>
                  )}
                </button>

                <Link to="/signin" className="btn btn-primary btn-block">
                  Return to Sign In
                </Link>
              </div>
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="auth-form">
              <div className="form-group">
                <label htmlFor="reset-email">Email address</label>
                <div className="input-wrap">
                  <Mail size={18} className="input-icon" />
                  <input
                    id="reset-email"
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

              <button
                type="submit"
                className="btn btn-primary btn-block"
                disabled={isLoading || cooldown.isActive}
              >
                {isLoading ? (
                  <>
                    <span className="spinner spinner-sm" />
                    <span>Sending instructions...</span>
                  </>
                ) : cooldown.isActive ? (
                  <>
                    <Clock size={16} />
                    <span>Wait {cooldown.secondsLeft}s before retrying</span>
                  </>
                ) : rateLimitNotice ? (
                  <span>Retry Sending Link</span>
                ) : (
                  <span>Send Reset Link</span>
                )}
              </button>

              <div className="auth-footer">
                <Link to="/signin" className="inline-flex items-center gap-1 text-sm text-slate-600 hover:text-slate-900">
                  <ArrowLeft size={16} />
                  <span>Back to Sign In</span>
                </Link>
              </div>
            </form>
          )}
        </div>
      </div>
    </div>
  );
}
