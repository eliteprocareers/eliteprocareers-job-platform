-- ============================================================
-- Migration 0015: Assigned-only visibility for candidate data
-- (Phase 4, part 9 -- RBAC data-visibility decision)
-- ============================================================
-- Context: as of migration 0007, ALL five candidate-data tables
-- (candidate_profiles, cv_tracks, applications, generated_documents,
-- user_job_matches) grant every org member -- any role -- full ALL
-- (select/insert/update/delete) access to any row in their org, via
-- a single is_org_member(organization_id) policy each. Confirmed by
-- reading pg_policies directly, not assumed. This means the platform
-- has been "fully shared within org" by default since Phase 4 began,
-- for every role equally.
--
-- Founder's explicit decision (2026-07-27): owners/admins keep full
-- visibility; managers/staff should only see candidates explicitly
-- assigned to them, matching how recruitment agencies and career
-- coaching firms actually operate -- reduces clutter and protects
-- candidate privacy. Must stay flexible: an org can opt into full
-- sharing instead. This migration is a real RLS *tightening* on
-- live tables with real data (1,402 rows as of this migration,
-- verified before writing a line of SQL) -- not a new, empty
-- feature. Every change here was checked against the founder's own
-- real org before and after, not assumed safe.
--
-- Design: assignment is per-CANDIDATE (a user_id), not per-resource-
-- type. cv_tracks/applications/generated_documents/user_job_matches
-- are all ultimately about one person's job search (their user_id) --
-- a staff member assigned to work with a candidate should see that
-- candidate's tracks, applications, documents, and matches together,
-- not need four separate assignments per candidate. candidate_profiles
-- is covered by the same rule for the same reason: a candidate's base
-- profile shouldn't leak to unassigned staff any more than their
-- tracks should.
--
-- matching_runs is deliberately NOT touched -- it's an operational
-- run-log for the background matching job, not user-facing candidate
-- data, and its existing RLS (user_id = auth.uid() only, no
-- organization_id column at all) was already the most restrictive
-- option available; nothing here needed to change it.
-- ============================================================

-- ============================================================
-- organizations.sharing_mode -- the flexibility the founder asked
-- for: an org can opt into full sharing instead of assigned-only.
-- Defaults to 'assigned_only', the new baseline behavior. Existing
-- orgs (just the founder's, sole owner) are unaffected either way --
-- owners always have full visibility regardless of this setting.
-- ============================================================

alter table organizations
  add column sharing_mode text not null default 'assigned_only'
  check (sharing_mode in ('assigned_only', 'full'));

-- ============================================================
-- organization_candidate_assignments -- who's assigned to work with
-- which candidate. Managed by owners/admins only; a manager/staff
-- can see their own assignments (to know their own caseload) but not
-- the whole org's assignment roster, matching the same assigned-only
-- philosophy this migration applies everywhere else.
-- ============================================================

create table organization_candidate_assignments (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references organizations(id) on delete cascade,
  candidate_user_id uuid not null references auth.users(id),
  assigned_to uuid not null references auth.users(id),
  assigned_by uuid not null references auth.users(id),
  created_at timestamptz not null default now(),
  unique (organization_id, candidate_user_id, assigned_to)
);

alter table organization_candidate_assignments enable row level security;

create index idx_org_candidate_assignments_org on organization_candidate_assignments(organization_id);
create index idx_org_candidate_assignments_candidate on organization_candidate_assignments(organization_id, candidate_user_id);
create index idx_org_candidate_assignments_assignee on organization_candidate_assignments(assigned_to);

create policy "Admins/owners see all assignments, staff see their own"
  on organization_candidate_assignments for select
  using (is_org_admin(organization_id) or assigned_to = (select auth.uid()));

create policy "Admins/owners manage assignments"
  on organization_candidate_assignments for insert
  with check (is_org_admin(organization_id));

create policy "Admins/owners update assignments"
  on organization_candidate_assignments for update
  using (is_org_admin(organization_id))
  with check (is_org_admin(organization_id));

create policy "Admins/owners remove assignments"
  on organization_candidate_assignments for delete
  using (is_org_admin(organization_id));

-- ============================================================
-- can_view_org_resource: single source of truth for the five
-- candidate-data tables' RLS, so the visibility rule lives in one
-- place instead of five near-identical copies. A caller can see a
-- resource if ANY of:
--   - it's their own (resource_user_id = auth.uid()) -- always true
--     for the founder's own self-created tracks today, so his
--     existing workflow is completely unaffected by this migration
--     regardless of sharing_mode or assignment state.
--   - they're an owner/admin of the org (full visibility, per the
--     founder's decision).
--   - the org has sharing_mode = 'full' and they're any member.
--   - they're specifically assigned to this candidate.
-- ============================================================

create or replace function can_view_org_resource(org_id uuid, resource_user_id uuid)
returns boolean
language sql
security definer
set search_path = ''
stable
as $$
  select
    resource_user_id = (select auth.uid())
    or public.is_org_admin(org_id)
    or (
      (select o.sharing_mode from public.organizations o where o.id = org_id) = 'full'
      and public.is_org_member(org_id)
    )
    or exists (
      select 1 from public.organization_candidate_assignments a
      where a.organization_id = org_id
        and a.candidate_user_id = resource_user_id
        and a.assigned_to = (select auth.uid())
    );
$$;

-- ============================================================
-- Replace the five tables' single is_org_member() ALL policy with
-- can_view_org_resource(). Same ALL-command shape as before (this
-- was already one combined policy per table, not split by command),
-- just a smarter condition -- minimizes the diff against the
-- existing, working structure.
-- ============================================================

drop policy "Org members manage cv_tracks" on cv_tracks;
create policy "Org members view/manage assigned or own cv_tracks"
  on cv_tracks for all
  using (can_view_org_resource(organization_id, user_id))
  with check (can_view_org_resource(organization_id, user_id));

drop policy "Org members manage applications" on applications;
create policy "Org members view/manage assigned or own applications"
  on applications for all
  using (can_view_org_resource(organization_id, user_id))
  with check (can_view_org_resource(organization_id, user_id));

drop policy "Org members manage generated_documents" on generated_documents;
create policy "Org members view/manage assigned or own generated_documents"
  on generated_documents for all
  using (can_view_org_resource(organization_id, user_id))
  with check (can_view_org_resource(organization_id, user_id));

drop policy "Org members manage user_job_matches" on user_job_matches;
create policy "Org members view/manage assigned or own user_job_matches"
  on user_job_matches for all
  using (can_view_org_resource(organization_id, user_id))
  with check (can_view_org_resource(organization_id, user_id));

drop policy "Org members manage candidate_profiles" on candidate_profiles;
create policy "Org members view/manage assigned or own candidate_profiles"
  on candidate_profiles for all
  using (can_view_org_resource(organization_id, user_id))
  with check (can_view_org_resource(organization_id, user_id));
