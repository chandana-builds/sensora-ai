# Deployment: exact steps

**Status: not deployed by the author.** I had no network or accounts. These steps and `scripts/smoke_test.py` are how you prove it works.

## 0. Free-tier facts (checked against provider docs, Nov 2026; re-check pricing pages)
- **Render free web service:** spins down after 15 min idle; the next request takes up to about a minute (the app shows a "waking up" hint); **ephemeral filesystem** (so SQLite data is lost on restart/redeploy); 750 free instance hours/month; Render may restart it at any time. Keep it warm before a demo by opening `/api/health/live`.
- **Supabase free:** 500 MB database, 5 GB egress, two active projects, **pauses after 1 week of inactivity** (manually resume it); no automatic backups. Evidence frames (≤1.5 MB each, ≤5 per session, only with consent) eat the 500 MB: leave evidence consent off for the demo.
- **Vercel Hobby:** fine for a hackathon demo (non-commercial use).
- **Meta API cost:** I could not verify pricing. Each turn costs one reasoning call, plus one vision call when a frame is attached; each voice message costs one transcription call. Guard with `MAX_TURNS_PER_DAY` (render.yaml: 60) and watch the Meta dashboard.

## 1. Supabase
1. Create a project. SQL editor → run `supabase/migrations/003_m4_store.sql` (RLS on, public roles revoked).
2. Project settings → API: copy **Project URL**, the **anon/publishable** key and the **service_role/secret** key. If your project shows only the new publishable/secret key style rather than legacy JWT keys, confirm with the smoke test that REST calls work (I could not verify that variant).
3. Authentication → Providers: enable Email. For a demo, you may disable "Confirm email". Add your Vercel URL under URL configuration.

## 2. Render (backend)
1. New → Blueprint → select the repo (uses `render.yaml`, rootDir `backend`).
2. Fill the `sync: false` secrets: `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `MODEL_API_KEY`, and a temporary `ALLOWED_ORIGINS=https://placeholder.example` (fixed in step 4). `APP_SECRET` is generated.
3. Deploy. Health check: `https://<service>.onrender.com/api/health/live`. If the build fails config validation, the logs name the unsafe setting.

## 3. Vercel (frontend)
1. Edit `frontend/vercel.json`: replace `YOUR-API.onrender.com` and `YOUR-PROJECT.supabase.co` in the CSP `connect-src` with your real hosts. Run `python backend/scripts/check_deploy_config.py` (must pass).
2. Import the repo, root directory `frontend`, framework Vite. Env vars: `VITE_API_URL`, `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`. Deploy; note the URL.

## 4. Connect and verify
1. Render → set `ALLOWED_ORIGINS` to the exact Vercel origin (e.g. `https://sensora.vercel.app`), redeploy.
2. `cd backend && ENV=production ... python scripts/preflight.py` (env set as on Render) → expect `PREFLIGHT OK`.
3. `python scripts/smoke_test.py https://<service>.onrender.com --origin https://<app>.vercel.app` → every line `PASS`; it prints whether AI is LIVE or SIMULATED.
4. In a browser on the Vercel URL, run the checklist in `docs/DEMO.md` (camera/mic/voice can only be verified by hand).

## 5. Rollback / ops
Render keeps recent deploys for rollback. Rotate any leaked key in Supabase/Meta and update Render. To lock the app to real accounts, set `ALLOW_ANONYMOUS_DEMO=false`.
