-- ============================================================
-- Migration 0016: matching_runs assignment-awareness
-- (Phase 4, part 12)
-- ============================================================
-- Context: migration 0015's own comment said matching_runs was
-- "deliberately NOT touched" because it was "an operational run-log
-- for the background matching job, not user-facing candidate data".
-- That reasoning held right up until assigned-staff support needed a
-- manager/staff member to actually trigger and poll a matching run on
-- an assigned candidate's behalf (see tracks.py's trigger_matching(),
-- flagged there 2026-07-28 as deliberately unfixed pending this real
-- design work). matching_runs' RLS (user_id = auth.uid() only, no
-- organization_id column at all) made that structurally impossible:
-- even after fixing which user_id gets attributed to a run, neither
-- the candidate nor any other assigned staff could see a run
-- triggered on the candidate's behalf, since RLS only ever admitted
-- the literal auth.uid() that matches user_id.
--
-- Fix: give matching_runs the same organization_id + can_view_org_
-- resource() treatment as the five candidate-data tables in migration
-- 0015, so a run is visible to whoever can see the candidate's other
-- data (self, org owner/admin, full-sharing org member, or assigned
-- staff) -- not just the literal triggering user.
--
-- Backfill verified safe before writing this migration: 0 cv_tracks
-- rows have a dangling organization_id, and 0 existing matching_runs
-- rows reference a cv_track_id that isn't in cv_tracks -- checked
-- directly via SQL, not assumed.
-- ============================================================

alter table matching_runs add column organization_id uuid references organizations(id);

update matching_runs r
set organization_id = t.organization_id
from cv_tracks t
where t.id = r.cv_track_id;

alter table matching_runs alter column organization_id set not null;

create index idx_matching_runs_org on matching_runs(organization_id);

drop policy "Users manage their own matching_runs" on matching_runs;

create policy "Org members view/manage assigned or own matching_runs"
  on matching_runs for all
  using (can_view_org_resource(organization_id, user_id))
  with check (can_view_org_resource(organization_id, user_id));
