# Supabase Setup (Local & Hosted)

## A. Local Development with Mailpit (Recommended for Development)
To test signups, email confirmations, and password resets locally without hitting email rate limits:
1. Start Docker Desktop on Windows.
2. Run `npx supabase start`.
3. Check status and keys: `npx supabase status`.
4. Apply migrations: `npx supabase db reset`.
5. Open local Mailpit web inbox: `http://127.0.0.1:54324`.
See [docs/SUPABASE_LOCAL_DEV.md](../docs/SUPABASE_LOCAL_DEV.md) for full instructions.

## B. Hosted Supabase Setup (Production)
1. Create a project at [supabase.com](https://supabase.com).
2. Open **SQL Editor**, paste `migrations/003_m4_store.sql` (and `migrations/001_initial_schema.sql`), run it.
3. **Project Settings → API**: copy the project URL and the `service_role` key into `.env`
   (`SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`). The service-role key is server-only.
4. For production email delivery without rate limits, configure Custom SMTP under **Project Settings → Authentication → SMTP Settings** (see [docs/SUPABASE_SETUP.md](../docs/SUPABASE_SETUP.md)).
