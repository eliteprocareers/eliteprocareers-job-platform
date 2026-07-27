-- Migration 0010: prevent duplicate applications per (cv_track_id, job_id)
--
-- Found live in production 2026-07-27: two matching runs could overlap
-- on the same track (no guard existed against this until this same
-- session's trigger_matching fix), and both would pass the
-- check-then-insert idempotency check in auto_apply.maybe_auto_apply /
-- applications.create_application for the same job before either
-- committed its insert -- producing duplicate application rows.
-- Confirmed real duplicates on both the test track (auto-apply path)
-- and a real track (manual create_application path, alongside an
-- already-submitted real application for a Cloudflare role).
--
-- This index was applied directly to production via the Supabase SQL
-- Editor earlier in this same session, before this migration file was
-- written -- captured here now so migrations/ doesn't drift from the
-- live schema the way 0004/0005 did (flagged in prior handovers).
-- Running this migration against production again is a safe no-op
-- (IF NOT EXISTS).

create unique index if not exists uq_applications_track_job
  on applications (cv_track_id, job_id);
