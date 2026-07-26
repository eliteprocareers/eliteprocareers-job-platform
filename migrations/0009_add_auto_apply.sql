-- Migration 0009: Auto-apply (Stage 5 extension).
--
-- Founder decisions (2026-07-26):
-- - Auto-apply behavior at launch: auto-create + auto-tailor docs +
--   auto-advance to 'ready_to_submit' after the undo window. Real
--   per-site form auto-fill is NOT part of this migration or this
--   session's build -- it needs its own per-ATS audit (Greenhouse/
--   Lever/BrighterMonday/MyJobMag each differ, and the existing
--   ApplicationRepository docstring flags real ToS/infrastructure
--   tradeoffs around automating submission that a prior session
--   already considered once -- not re-litigated here).
-- - min_score default 0.85, configurable per track.
-- - undo_window_minutes: user-configurable (0/5/15/30, or NULL for
--   "manual approval only" -- auto-apply never fires without an
--   explicit approval step for that track).
-- - Failure handling: retry_count/last_attempt_at/failure_reason exist
--   now so the state machine is ready, but nothing populates them yet
--   -- there's no real submission action to fail against until the
--   auto-fill work lands.

alter table cv_tracks
  add column auto_apply_enabled boolean not null default false,
  add column auto_apply_min_score numeric not null default 0.85,
  add column undo_window_minutes integer default 15;

comment on column cv_tracks.undo_window_minutes is
  'Minutes between an auto-apply queuing an application and it advancing to ready_to_submit. NULL means manual-approval-only: auto-apply never fires automatically for this track.';

-- Extend the status machine. Existing values unchanged; four new ones
-- for the auto-apply lifecycle: queued, ready_to_submit,
-- needs_attention, cancelled.
alter table applications drop constraint applications_status_check;
alter table applications add constraint applications_status_check
  check (status = ANY (ARRAY[
    'draft', 'queued', 'ready_to_submit', 'submitted', 'interviewing',
    'rejected', 'offer', 'withdrawn', 'needs_attention', 'cancelled'
  ]));

alter table applications
  add column auto_applied boolean not null default false,
  add column queued_at timestamptz,
  add column undo_deadline timestamptz,
  add column retry_count integer not null default 0,
  add column last_attempt_at timestamptz,
  add column failure_reason text;

comment on column applications.auto_applied is
  'True if created by the auto-apply trigger (match score >= track.auto_apply_min_score), false if created manually.';
comment on column applications.undo_deadline is
  'queued_at + track.undo_window_minutes at creation time. Once now() passes this, a queued application is eligible to advance to ready_to_submit (applied lazily on read).';
