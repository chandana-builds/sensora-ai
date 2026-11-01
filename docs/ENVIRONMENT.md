# Environment variables

Secrets live only in the Render/Vercel dashboards or a local, git-ignored `.env`. `.env.example` has every variable. Run `python backend/scripts/preflight.py` to validate. In production the backend **refuses to start** on unsafe settings.

## Backend (Render)
| Variable | Required | Notes |
|---|---|---|
| `ENV` | prod | `production` enables strict validation, hides `/docs` |
| `ALLOWED_ORIGINS` | prod | exact `https://` frontend origin(s), comma-separated, no wildcard, no trailing slash |
| `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` | prod | storage; **secret**, server only |
| `SUPABASE_ANON_KEY` | for accounts | used to verify user tokens (public-type key) |
| `APP_SECRET` | if guests on | ≥32 random chars; signs guest tokens (`generateValue` in render.yaml) |
| `ALLOW_ANONYMOUS_DEMO` | no | `true` = guest demo (production default `false`; render.yaml sets `true`) |
| `MODEL_API_KEY` | for live AI | Meta Model API key; **secret**. Absent + `AI_MODE=auto` → labelled DEMO mode |
| `AI_MODE` | no | `auto` (default) / `real` (needs key) / `demo` |
| `STORAGE_BACKEND` | no | `supabase` (prod default) / `sqlite` (local; **ephemeral on Render free**) / `memory` (dev/test only; refused in prod) |
| `META_*`, `DEMO_SCENARIO` | no | model ids, timeout, language bias, `router`\|`induction` |
| `RATE_LIMIT_PER_MIN`, `EXPENSIVE_LIMIT_PER_MIN`, `MAX_TURNS_PER_DAY`, `MAX_BODY_BYTES`, `MAX_SESSIONS_PER_USER`, `MAX_MESSAGES_PER_SESSION`, `EVIDENCE_RETENTION_DAYS` | no | abuse/cost/storage guards |

## Frontend (Vercel, build-time, public)
`VITE_API_URL` (Render URL), `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY` (optional, enables accounts). **Never** put the service-role key, `MODEL_API_KEY` or `APP_SECRET` in a `VITE_` variable: everything `VITE_` is shipped to browsers. `scripts/check_deploy_config.py` flags this.
