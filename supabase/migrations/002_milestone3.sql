-- Milestone 3: workflow state, verification fields, observations, consented evidence, retention.
-- NOTE: adjust table/column names if your 001 migration differs. If troubleshooting_steps.status has a CHECK
-- constraint, extend it with: awaiting_user, awaiting_verification, completed_verified, completed_user_confirmed,
-- completed_simulated, failed.
alter table troubleshooting_sessions
  add column if not exists workflow_state text not null default 'problem_reported'
    check (workflow_state in ('problem_reported','information_gathering','awaiting_visual_evidence','analyzing',
      'awaiting_user_action','verifying_action','resolved','escalation_required','session_completed')),
  add column if not exists device_model text,
  add column if not exists problem text,
  add column if not exists user_level text check (user_level in ('beginner','experienced')),
  add column if not exists final_status text,
  add column if not exists evidence_consent boolean not null default false,
  add column if not exists clarify_pending boolean not null default false,
  add column if not exists safety_check_answered boolean not null default false,
  add column if not exists safety_events text[] not null default '{}',
  add column if not exists summary jsonb;

alter table troubleshooting_steps
  add column if not exists expected_result text,
  add column if not exists verification_mode text not null default 'visual' check (verification_mode in ('visual','user_confirmation')),
  add column if not exists user_reported_complete boolean not null default false,   -- the user said they did it
  add column if not exists visually_verified boolean not null default false,        -- set ONLY by the server from real visual evidence
  add column if not exists verification_outcome text not null default 'pending',
  add column if not exists verification_basis text not null default 'none',
  add column if not exists verification_note text,
  add column if not exists simulated boolean not null default false;

alter table user_preferences add column if not exists remember_level boolean not null default false;

create table if not exists session_observations (
  id uuid primary key default gen_random_uuid(),
  session_id uuid not null references troubleshooting_sessions(id) on delete cascade,
  text text not null, simulated boolean not null default false, created_at timestamptz not null default now());

-- Selected evidence FRAMES only (never continuous video). Stored only with evidence_consent = true.
create table if not exists evidence_frames (
  id uuid primary key default gen_random_uuid(),
  session_id uuid not null references troubleshooting_sessions(id) on delete cascade,
  data bytea not null check (octet_length(data) <= 1500000),
  note text, captured_at timestamptz not null default now(), expires_at timestamptz not null);

alter table session_observations enable row level security;
alter table evidence_frames enable row level security;   -- no policies: backend service role only

create or replace function purge_expired_evidence() returns integer language sql as
$$ with d as (delete from evidence_frames where expires_at < now() returning 1) select count(*)::int from d $$;
-- Schedule daily, e.g. with pg_cron: select cron.schedule('purge-evidence','0 3 * * *','select purge_expired_evidence()');
