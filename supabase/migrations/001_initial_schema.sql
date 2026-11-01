-- Sensora AI — initial schema (Milestone 1)
-- Apply with the Supabase SQL editor, or `supabase db push` if you use the Supabase CLI.
-- Access model: the FastAPI backend connects with the service-role key and scopes every
-- query by user_id. RLS is enabled with NO policies, so the anon/authenticated roles
-- (i.e. anything using the public anon key from a browser) cannot read or write these tables.

create or replace function public.set_updated_at() returns trigger
language plpgsql as $$
begin
  new.updated_at = now();
  return new;
end $$;

-- Users / profiles -------------------------------------------------------
-- id is the Supabase Auth user id when AUTH_MODE=supabase, or the anonymous
-- client UUID in Milestone 1's default anonymous mode (hence no FK to auth.users).
create table if not exists public.profiles (
  id            uuid primary key,
  display_name  text,
  is_anonymous  boolean not null default true,
  created_at    timestamptz not null default now()
);

-- User preferences -------------------------------------------------------
create table if not exists public.user_preferences (
  user_id           uuid primary key references public.profiles(id) on delete cascade,
  experience_level  text    not null default 'beginner' check (experience_level in ('beginner','experienced')),
  speak_responses   boolean not null default true,
  speech_rate       numeric(3,2) not null default 1.00 check (speech_rate between 0.5 and 2.0),
  larger_text       boolean not null default false,
  high_contrast     boolean not null default false,
  reduce_motion     boolean not null default false,
  save_transcripts  boolean not null default true,
  updated_at        timestamptz not null default now()
);
drop trigger if exists trg_user_preferences_updated on public.user_preferences;
create trigger trg_user_preferences_updated before update on public.user_preferences
  for each row execute function public.set_updated_at();

-- Troubleshooting sessions -----------------------------------------------
create table if not exists public.troubleshooting_sessions (
  id                   uuid primary key default gen_random_uuid(),
  user_id              uuid not null references public.profiles(id) on delete cascade,
  title                text not null,
  device_name          text,
  problem_description  text,
  experience_level     text not null default 'beginner' check (experience_level in ('beginner','experienced')),
  status               text not null default 'active'
                       check (status in ('active','resolved','unresolved','escalated','abandoned')),
  started_at           timestamptz not null default now(),
  ended_at             timestamptz,
  updated_at           timestamptz not null default now()
);
create index if not exists idx_sessions_user_started on public.troubleshooting_sessions (user_id, started_at desc);
create index if not exists idx_sessions_user_status  on public.troubleshooting_sessions (user_id, status);
drop trigger if exists trg_sessions_updated on public.troubleshooting_sessions;
create trigger trg_sessions_updated before update on public.troubleshooting_sessions
  for each row execute function public.set_updated_at();

-- Conversation messages --------------------------------------------------
create table if not exists public.conversation_messages (
  id            uuid primary key default gen_random_uuid(),
  session_id    uuid not null references public.troubleshooting_sessions(id) on delete cascade,
  role          text not null check (role in ('user','assistant','system')),
  content       text not null,
  input_mode    text not null default 'text' check (input_mode in ('text','speech')),
  safety_level  text not null default 'ok' check (safety_level in ('ok','caution','stop')),
  created_at    timestamptz not null default now()
);
create index if not exists idx_messages_session_created on public.conversation_messages (session_id, created_at);

-- Troubleshooting steps --------------------------------------------------
-- `verification` records HOW a step outcome was established. 'visually_verified'
-- must only ever be set by server-side vision analysis (Milestone 2+), never by a client.
create table if not exists public.troubleshooting_steps (
  id            uuid primary key default gen_random_uuid(),
  session_id    uuid not null references public.troubleshooting_sessions(id) on delete cascade,
  step_number   integer not null check (step_number > 0),
  instruction   text not null,
  status        text not null default 'pending'
                check (status in ('pending','in_progress','completed','failed','skipped')),
  verification  text not null default 'not_verified'
                check (verification in ('not_verified','user_confirmed','visually_verified')),
  outcome_note  text,
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now(),
  unique (session_id, step_number)
);
drop trigger if exists trg_steps_updated on public.troubleshooting_steps;
create trigger trg_steps_updated before update on public.troubleshooting_steps
  for each row execute function public.set_updated_at();

-- Session summaries ------------------------------------------------------
create table if not exists public.session_summaries (
  session_id         uuid primary key references public.troubleshooting_sessions(id) on delete cascade,
  summary            text not null,
  unresolved_issues  jsonb not null default '[]'::jsonb,
  generated_by       text not null default 'system' check (generated_by in ('user','system','ai')),
  created_at         timestamptz not null default now(),
  updated_at         timestamptz not null default now()
);
drop trigger if exists trg_summaries_updated on public.session_summaries;
create trigger trg_summaries_updated before update on public.session_summaries
  for each row execute function public.set_updated_at();

-- Row-level security: deny everything except the service role ------------
alter table public.profiles                 enable row level security;
alter table public.user_preferences         enable row level security;
alter table public.troubleshooting_sessions enable row level security;
alter table public.conversation_messages    enable row level security;
alter table public.troubleshooting_steps    enable row level security;
alter table public.session_summaries        enable row level security;

revoke all on public.profiles, public.user_preferences, public.troubleshooting_sessions,
              public.conversation_messages, public.troubleshooting_steps, public.session_summaries
  from anon, authenticated;
