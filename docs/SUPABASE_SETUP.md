# Sensora AI — Supabase Auth & Storage Setup Guide

This document explains how Supabase Authentication and Database Storage are connected in Sensora AI, why the `"email rate limit exceeded"` error occurs, and how to resolve it for development and production.

---

## 1. Why "email rate limit exceeded" (`over_email_send_rate_limit`) Occurs

When using Supabase's hosted service on the free tier:
- Supabase provides a **default shared email service** (via AWS SES) intended only for basic initial testing.
- This shared pool has a strict rate limit of approximately **3 to 4 emails per hour** per project for signup confirmations, password recovery emails, and magic links.
- When multiple test accounts are created, verification links are resent, or repeated requests are fired, Supabase GoTrue returns:
  ```json
  HTTP 429 Too Many Requests
  {
    "code": 429,
    "error_code": "over_email_send_rate_limit",
    "msg": "email rate limit exceeded"
  }
  ```

---

## 2. Sensora AI Safeguards Against Rate Limits

The application includes robust frontend and backend protections against duplicate requests and email exhaustion:

1. **Synchronous In-Flight Locks (`useRef`)**:
   - Form submission and button clicks use immediate reference locks (`isSubmittingRef.current = true`) to prevent rapid double-clicks or repeated keyboard Enter presses from dispatching duplicate API calls before React state updates.

2. **Persistent Cooldown Timers (`useAuthCooldown`)**:
   - When a rate limit or email dispatch occurs, an automated 60-second cooldown is initiated.
   - The cooldown timestamp is stored in `sessionStorage`, so page refreshes or component remounts **cannot** bypass the timer.
   - Submit buttons display a live countdown: `Wait 45s before retrying` and remain disabled until the cooldown finishes.

3. **Form Input Preservation**:
   - Form fields (`displayName`, `email`, `password`) are maintained in state during rate limit errors so users do not lose their inputs.

4. **Dedicated Verification Resend Flow**:
   - On the confirmation screen, a distinct "Resend verification email" action is available with a 60-second cooldown timer, preventing users from repeatedly hitting the signup endpoint.

5. **Instant Guest Workspace Fallback**:
   - If rate limits occur or emails are delayed, users can click **"Continue as Guest"** for instant, cryptographically isolated access to the full troubleshooting environment without waiting for an email.

---

## 3. How to Resolve the Rate Limit in Supabase

You have two simple options in the Supabase Dashboard:

### Option A: Turn Off "Confirm Email" (Fastest for Development & Testing)

If you are developing locally or presenting a live demo and do not require email verification:
1. Open your [Supabase Dashboard](https://supabase.com/dashboard).
2. Navigate to **Authentication** → **Providers** → **Email**.
3. Toggle **Confirm email** to **OFF**.
4. Click **Save**.

*Result*: New signups will automatically sign in immediately (`autoSignedIn = true`), eliminating email dispatch entirely and never triggering the rate limit.

---

### Option B: Configure Custom SMTP (Recommended for Production)

Configuring your own SMTP provider removes Supabase's 3-4 emails/hour restriction and uses your email provider's high-volume quota (e.g. Resend free tier includes 3,000 emails/month or 100/day).

1. Open your [Supabase Dashboard](https://supabase.com/dashboard).
2. Go to **Project Settings** (gear icon) → **Authentication**.
3. Scroll down to **SMTP Settings** and switch **Enable Custom SMTP** to **ON**.
4. Fill in your SMTP provider details:

#### Example: Using [Resend](https://resend.com) (Recommended)
- **Sender email**: `noreply@yourdomain.com` (or your verified domain email)
- **Sender name**: `Sensora AI`
- **Host**: `smtp.resend.com`
- **Port**: `465` (SSL) or `587` (TLS)
- **Minimum TLS version**: `TLSv1.2`
- **User**: `resend`
- **Password**: `re_123456789...` (your Resend API key)

#### Example: Using [SendGrid](https://sendgrid.com)
- **Sender email**: `noreply@yourdomain.com`
- **Sender name**: `Sensora AI`
- **Host**: `smtp.sendgrid.net`
- **Port**: `587`
- **User**: `apikey`
- **Password**: `SG.xxxxxxxx...` (your SendGrid API key)

#### Example: Using [Brevo / Sendinblue](https://brevo.com)
- **Host**: `smtp-relay.brevo.com`
- **Port**: `587`
- **User**: your Brevo login email
- **Password**: your Brevo SMTP key

5. Click **Save Changes** at the bottom of the page.

---

## 4. Checking Supabase Auth Logs

To inspect authentication events, error codes, and rate limits:
1. Open your Supabase Dashboard.
2. In the left navigation, click **Logs** → **Auth Logs**.
3. Search for `over_email_send_rate_limit` or filter by status `429`.
4. Inspect the timestamp, user email, and request endpoint (`/signup`, `/recover`, `/resend`).

---

## 5. Environment Variables Configuration

Ensure the following variables are defined in your environment files:

### Root `.env` & `backend/.env`
```ini
SUPABASE_URL=https://<your-project-ref>.supabase.co
SUPABASE_ANON_KEY=sb_publishable_...
SUPABASE_SERVICE_ROLE_KEY=sb_secret_...
APP_SECRET=sensora-super-secret-key-32-chars-long-minimum-jwt-secret-m4
STORAGE_BACKEND=sqlite    # or supabase (requires running 003_m4_store.sql)
```

### `frontend/.env`
```ini
VITE_API_URL=http://127.0.0.1:8000
VITE_API_BASE_URL=http://127.0.0.1:8000
VITE_SUPABASE_URL=https://<your-project-ref>.supabase.co
VITE_SUPABASE_ANON_KEY=sb_publishable_...
```

---

## 6. Database Table Setup (When using `STORAGE_BACKEND=supabase`)

If you wish to store sessions and transcripts directly in Supabase PostgreSQL:
1. Open **SQL Editor** in the Supabase Dashboard.
2. Copy the SQL script from `supabase/migrations/003_m4_store.sql`.
3. Paste and click **Run**.
4. Set `STORAGE_BACKEND=supabase` in `.env`.
5. Restart the backend.
