-- ============================================================
-- Migration 0004: Add matching_runs, for real status-polling on
-- background matching runs triggered via POST /tracks/{id}/match.
-- Replaces the frontend's client-side timed-poll workaround.
-- ============================================================

create table matching_runs (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  cv_track_id uuid not null references cv_tracks(id) on delete cascade,
  status text not null default 'running'
    check (status in ('running','completed','failed')),
  jobs_total integer,
  jobs_processed integer not null default 0,
  error_message text,
  started_at timestamptz not null default now(),
  completed_at timestamptz
);

alter table matching_runs enable row level security;

create policy "Users manage their own matching_runs"
  on matching_runs for all
  using (user_id = auth.uid())
  with check (user_id = auth.uid());

create index idx_matching_runs_track on matching_runs(cv_track_id);
create index idx_matching_runs_user on matching_runs(user_id);
