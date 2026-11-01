-- Milestone 4: tables used by the production backend (DocMemoryStore over Supabase REST).
-- Self-contained: it does not depend on the earlier 001/002 tables (you may ignore or drop those).
-- Security model: RLS is ON with NO policies and anon/authenticated roles are revoked, so the public anon key can read nothing.
-- Only the backend (service-role key, never sent to the browser) reads/writes. Ownership is enforced by the backend on every query (owner = verified user id).
create table if not exists sensora_sessions (
  owner text not null, id text not null, seq bigint not null, created_at timestamptz not null default now(), data jsonb not null,
  primary key (owner, id));
create index if not exists ix_sensora_sessions_owner_seq on sensora_sessions(owner, seq desc);

create table if not exists sensora_messages (
  id text primary key, owner text not null, sid text not null, seq bigint not null, created_at timestamptz not null default now(),
  role text not null check (role in ('user','assistant','system')), content text not null, metadata jsonb not null default '{}');
create index if not exists ix_sensora_messages on sensora_messages(owner, sid, seq);

create table if not exists sensora_steps (
  id text primary key, owner text not null, sid text not null, seq bigint not null, created_at timestamptz not null default now(), data jsonb not null);
create index if not exists ix_sensora_steps on sensora_steps(owner, sid, seq);

create table if not exists sensora_observations (
  id text primary key, owner text not null, sid text not null, seq bigint not null, created_at timestamptz not null default now(),
  text text not null, simulated boolean not null default false);
create index if not exists ix_sensora_obs on sensora_observations(owner, sid, seq);

-- Selected evidence FRAMES only (never video); stored only after the user consents; capped per session by the backend; expiring.
create table if not exists sensora_evidence (
  id text primary key, owner text not null, sid text not null, seq bigint not null, note text,
  size integer not null check (size <= 1500000), captured_at timestamptz not null default now(), expires_at timestamptz not null, data bytea not null);
create index if not exists ix_sensora_evidence on sensora_evidence(owner, sid);
create index if not exists ix_sensora_evidence_exp on sensora_evidence(expires_at);

create table if not exists sensora_prefs (owner text primary key, user_level text check (user_level in ('beginner','experienced')), remember_level boolean not null default false);

alter table sensora_sessions enable row level security;
alter table sensora_messages enable row level security;
alter table sensora_steps enable row level security;
alter table sensora_observations enable row level security;
alter table sensora_evidence enable row level security;
alter table sensora_prefs enable row level security;
revoke all on sensora_sessions, sensora_messages, sensora_steps, sensora_observations, sensora_evidence, sensora_prefs from anon, authenticated;

create or replace function purge_expired_evidence() returns integer language sql security invoker as
$$ with d as (delete from sensora_evidence where expires_at < now() returning 1) select count(*)::int from d $$;
revoke all on function purge_expired_evidence() from anon, authenticated;
-- Optional daily purge (the backend also deletes on consent withdrawal):  select cron.schedule('purge-evidence','0 3 * * *','select purge_expired_evidence()');
