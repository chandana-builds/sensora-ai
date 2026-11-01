# Sensora AI — Local Supabase & Mailpit Email Testing Guide

This guide provides step-by-step instructions for running a **local Supabase development environment with Mailpit** on Windows. This eliminates email rate-limit issues during development by capturing all verification and password-reset emails in a local web inbox.

---

## 1. Architecture & Port Mapping

When the local Supabase stack is running, the following endpoints are available:

| Service | Local Endpoint | Purpose |
| :--- | :--- | :--- |
| **Supabase API Gateway** | `http://127.0.0.1:54321` | REST API, GoTrue Auth, PostgREST |
| **Supabase Studio** | `http://127.0.0.1:54323` | Web UI for PostgreSQL tables & Auth users |
| **Mailpit / Inbucket Web Inbox** | `http://127.0.0.1:54324` | Catch-all local inbox for verification & reset emails |
| **PostgreSQL Database** | `127.0.0.1:54322` | Direct PostgreSQL connection (`postgres:postgres`) |
| **Sensora Frontend (Vite)** | `http://127.0.0.1:5173` | Web application |
| **Sensora Backend (FastAPI)** | `http://127.0.0.1:8000` | Troubleshooting orchestrator & API |

---

## 2. Prerequisites

Before starting the local Supabase stack, ensure the following are installed on Windows:

1. **Docker Desktop**:
   - Download and install [Docker Desktop for Windows](https://www.docker.com/products/docker-desktop/).
   - Ensure the WSL 2 backend is enabled in Docker Desktop settings.
   - Start Docker Desktop and verify it is running in PowerShell:
     ```powershell
     docker --version
     docker ps
     ```
2. **Node.js & npx**:
   - Verify Node.js and npx are available:
     ```powershell
     node --version
     npx --version
     ```
   - Node v18+ is supported (v20 or v24 recommended).

---

## 3. Step-by-Step Developer Setup (Windows PowerShell)

Open PowerShell in the project root: `C:\Users\LENOVO\OneDrive\Desktop\Sensora AI`

### Step 1: Start Docker Desktop
Ensure Docker Desktop is open and showing "Engine running" in green.

### Step 2: Start Local Supabase Stack
Run the following command to download containers and initialize the local stack:
```powershell
npx supabase start
```
*(On first run, Docker will download the official Supabase service containers: Postgres, GoTrue Auth, PostgREST, Studio, and Inbucket/Mailpit. This takes 1-3 minutes).*

### Step 3: Retrieve Local Credentials
Inspect the running local services and copy your local API keys:
```powershell
npx supabase status
```
This prints the local URLs and generated keys:
- **API URL**: `http://127.0.0.1:54321`
- **anon key**: `eyJhbGciOiJIUzI1NiIsIn...`
- **service_role key**: `eyJhbGciOiJIUzI1NiIsIn...`
- **Inbucket/Mailpit URL**: `http://127.0.0.1:54324`

### Step 4: Apply Local Database Migrations
Run the migrations to create all application tables:
```powershell
npx supabase db reset
```
This automatically applies in order:
1. `001_initial_schema.sql` (Profiles, troubleshooting sessions, preferences)
2. `002_milestone3.sql` (Workflow states, verification tracking, evidence frames)
3. `003_m4_store.sql` (Sensora session store, messages, steps, and preferences)
4. `seed.sql` (Local seed data)

---

## 4. Connecting the Frontend & Backend

### Frontend Configuration
Create or update `frontend/.env.local` (Vite loads `.env.local` with priority over `.env`):
```ini
VITE_API_URL=http://127.0.0.1:8000
VITE_API_BASE_URL=http://127.0.0.1:8000
VITE_SUPABASE_URL=http://127.0.0.1:54321
VITE_SUPABASE_ANON_KEY=<anon-key-from-npx-supabase-status>
VITE_LOCAL_MAILPIT_URL=http://127.0.0.1:54324
```

### Backend Configuration
Update `backend/.env` (or set in development):
```ini
SUPABASE_URL=http://127.0.0.1:54321
SUPABASE_ANON_KEY=<anon-key-from-npx-supabase-status>
SUPABASE_SERVICE_ROLE_KEY=<service-role-key-from-npx-supabase-status>
STORAGE_BACKEND=sqlite
```

---

## 5. Testing the Email Verification Flow

1. **Sign Up**:
   - Open [http://localhost:5173/signup](http://localhost:5173/signup).
   - Enter your name, email (e.g. `testuser@example.com`), and a password.
   - Click **Create Account**.
   - Notice the badge: **Local Mailpit Dev**.
2. **Inspect Mailpit Inbox**:
   - Open [http://127.0.0.1:54324](http://127.0.0.1:54324) in your browser (or click the **"Open Mailpit Inbox"** button directly on the confirmation screen).
   - Click on the confirmation email from Sensora AI.
   - Click the confirmation link (or copy the confirmation URL).
3. **Sign In**:
   - Return to [http://localhost:5173/signin](http://localhost:5173/signin).
   - Sign in with your verified credentials.
   - You are redirected to your personalized Dashboard!
4. **Password Reset Flow**:
   - Open [http://localhost:5173/forgot-password](http://localhost:5173/forgot-password).
   - Enter your email and click **Send Reset Link**.
   - Switch to Mailpit (`http://127.0.0.1:54324`) to see the recovery email.

---

## 6. Stopping Local Services

When you finish development, stop the containers to free system memory:
```powershell
npx supabase stop
```
To stop and clean local database containers:
```powershell
npx supabase stop --no-backup
```

---

## 7. Protection of Hosted Supabase Project

- The local Supabase stack is completely isolated inside Docker containers on port `54321`.
- The hosted production project (`https://vkkwwrkaovkaeqkdojbl.supabase.co`) is **never modified, reset, or contacted** when using `http://127.0.0.1:54321`.
- To switch back to hosted Supabase, simply delete or rename `frontend/.env.local`, and Vite will instantly resume using your hosted `.env`.
