-- ============================================================
-- Migration 0007: Multi-tenant organizations layer (Phase 4, part 1)
-- ============================================================
-- Design (per founder direction, this session):
--   - A "tenant" is a generic `organization`, not a recruitment-agency
--     -specific concept. org_type distinguishes flavors later.
--   - Every user belongs to one or more organizations via
--     organization_members, with a role (owner/admin/member).
--   - Every EXISTING individual account is backfilled into its own
--     single-member 'individual' organization, so current behavior is
--     unchanged: one user, one org, same effective access as today.
--   - Org creation and membership bootstrap (the first owner row) go
--     through the backend's service_role key, same convention already
--     used for jobs ingestion -- there is deliberately no insert
--     policy on `organizations`, and `organization_members` insert
--     requires an existing admin/owner (see is_org_admin below), which
--     the very first membership row can't satisfy from the client.
--     This is intentional, not an oversight.
--   - This migration is schema + backfill only. It does not change any
--     application code path yet -- API/frontend still read/write
--     exactly as before against user_id-owned rows; org_id is present
--     and populated but not yet load-bearing in app logic. That's the
--     deliberately separate next step, not bundled into this migration.
-- ============================================================

-- ============================================================
-- ORGANIZATIONS + MEMBERSHIP
-- ============================================================

create table organizations (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  org_type text not null default 'individual'
    check (org_type in (
      'individual', 'agency', 'staffing_firm', 'company',
      'university', 'career_coaching_firm', 'enterprise'
    )),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table organizations enable row level security;

create trigger trg_organizations_updated_at
  before update on organizations
  for each row execute function set_updated_at();

create table organization_members (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references organizations(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  role text not null default 'member'
    check (role in ('owner', 'admin', 'member')),
  created_at timestamptz not null default now(),
  unique (organization_id, user_id)
);

alter table organization_members enable row level security;

-- ============================================================
-- Helper functions (security definer -- avoids RLS self-recursion
-- when organization_members' own policies need to check membership)
-- ============================================================

create or replace function is_org_member(org_id uuid)
returns boolean
language sql
security definer
set search_path = ''
stable
as $$
  select exists (
    select 1 from public.organization_members
    where organization_id = org_id
      and user_id = (select auth.uid())
  );
$$;

create or replace function is_org_admin(org_id uuid)
returns boolean
language sql
security definer
set search_path = ''
stable
as $$
  select exists (
    select 1 from public.organization_members
    where organization_id = org_id
      and user_id = (select auth.uid())
      and role in ('owner', 'admin')
  );
$$;

-- ============================================================
-- RLS: organizations / organization_members
-- ============================================================

create policy "Members can view their organizations"
  on organizations for select
  using (is_org_member(id));

create policy "Admins/owners can update their organization"
  on organizations for update
  using (is_org_admin(id))
  with check (is_org_admin(id));

-- No insert/delete policy for authenticated users -- org creation and
-- deletion go through the backend via service_role, same convention
-- as `jobs`.

create policy "Members can view fellow org members"
  on organization_members for select
  using (is_org_member(organization_id));

create policy "Admins/owners can add members"
  on organization_members for insert
  with check (is_org_admin(organization_id));

create policy "Admins/owners can update member roles"
  on organization_members for update
  using (is_org_admin(organization_id))
  with check (is_org_admin(organization_id));

create policy "Admins/owners can remove members"
  on organization_members for delete
  using (is_org_admin(organization_id));

create index idx_organization_members_org on organization_members(organization_id);
create index idx_organization_members_user on organization_members(user_id);

-- ============================================================
-- Backfill: one 'individual' organization per existing user,
-- across every currently user_id-owned table
-- ============================================================

create temporary table _user_org_map as
select u.user_id, gen_random_uuid() as organization_id
from (
  select distinct user_id from candidate_profiles
  union select distinct user_id from cv_tracks
  union select distinct user_id from user_job_matches
  union select distinct user_id from applications
  union select distinct user_id from generated_documents
) u;

insert into organizations (id, name, org_type)
select
  m.organization_id,
  coalesce(cp.full_name, 'Individual Workspace'),
  'individual'
from _user_org_map m
left join candidate_profiles cp on cp.user_id = m.user_id;

insert into organization_members (organization_id, user_id, role)
select organization_id, user_id, 'owner' from _user_org_map;

-- ============================================================
-- Add organization_id to every owner-keyed table, backfill, lock down
-- ============================================================

alter table candidate_profiles add column organization_id uuid references organizations(id);
update candidate_profiles cp set organization_id = m.organization_id
  from _user_org_map m where m.user_id = cp.user_id;
alter table candidate_profiles alter column organization_id set not null;

alter table cv_tracks add column organization_id uuid references organizations(id);
update cv_tracks t set organization_id = m.organization_id
  from _user_org_map m where m.user_id = t.user_id;
alter table cv_tracks alter column organization_id set not null;

alter table user_job_matches add column organization_id uuid references organizations(id);
update user_job_matches j set organization_id = m.organization_id
  from _user_org_map m where m.user_id = j.user_id;
alter table user_job_matches alter column organization_id set not null;

alter table applications add column organization_id uuid references organizations(id);
update applications a set organization_id = m.organization_id
  from _user_org_map m where m.user_id = a.user_id;
alter table applications alter column organization_id set not null;

alter table generated_documents add column organization_id uuid references organizations(id);
update generated_documents d set organization_id = m.organization_id
  from _user_org_map m where m.user_id = d.user_id;
alter table generated_documents alter column organization_id set not null;

drop table _user_org_map;

create index idx_candidate_profiles_org on candidate_profiles(organization_id);
create index idx_cv_tracks_org on cv_tracks(organization_id);
create index idx_user_job_matches_org on user_job_matches(organization_id);
create index idx_applications_org on applications(organization_id);
create index idx_generated_documents_org on generated_documents(organization_id);

-- ============================================================
-- Rewrite RLS on the 5 owner-keyed tables: org membership instead of
-- direct user_id match. For a single-member 'individual' org this is
-- behaviorally identical to today -- is_org_member(organization_id)
-- is true for exactly the same one user that user_id = auth.uid() was
-- true for.
-- ============================================================

drop policy "Users manage their own profile" on candidate_profiles;
create policy "Org members manage candidate_profiles"
  on candidate_profiles for all
  using (is_org_member(organization_id))
  with check (is_org_member(organization_id));

drop policy "Users manage their own cv_tracks" on cv_tracks;
create policy "Org members manage cv_tracks"
  on cv_tracks for all
  using (is_org_member(organization_id))
  with check (is_org_member(organization_id));

drop policy "Users manage their own user_job_matches" on user_job_matches;
create policy "Org members manage user_job_matches"
  on user_job_matches for all
  using (is_org_member(organization_id))
  with check (is_org_member(organization_id));

drop policy "Users manage their own applications" on applications;
create policy "Org members manage applications"
  on applications for all
  using (is_org_member(organization_id))
  with check (is_org_member(organization_id));

drop policy "Users manage their own generated_documents" on generated_documents;
create policy "Org members manage generated_documents"
  on generated_documents for all
  using (is_org_member(organization_id))
  with check (is_org_member(organization_id));

-- ============================================================
-- Rewrite RLS on child tables that hang off candidate_profiles, so
-- they follow the same org-membership check via the parent profile's
-- organization_id rather than the old user_id = auth.uid() path.
-- ============================================================

drop policy "Users manage their own candidate_skills" on candidate_skills;
create policy "Org members manage candidate_skills"
  on candidate_skills for all
  using (profile_id in (select id from candidate_profiles where is_org_member(organization_id)))
  with check (profile_id in (select id from candidate_profiles where is_org_member(organization_id)));

drop policy "Users manage their own work_experience" on work_experience;
create policy "Org members manage work_experience"
  on work_experience for all
  using (profile_id in (select id from candidate_profiles where is_org_member(organization_id)))
  with check (profile_id in (select id from candidate_profiles where is_org_member(organization_id)));

drop policy "Users manage their own education" on education;
create policy "Org members manage education"
  on education for all
  using (profile_id in (select id from candidate_profiles where is_org_member(organization_id)))
  with check (profile_id in (select id from candidate_profiles where is_org_member(organization_id)));

drop policy "Users manage their own certifications" on certifications;
create policy "Org members manage certifications"
  on certifications for all
  using (profile_id in (select id from candidate_profiles where is_org_member(organization_id)))
  with check (profile_id in (select id from candidate_profiles where is_org_member(organization_id)));

drop policy "Users manage their own languages" on languages;
create policy "Org members manage languages"
  on languages for all
  using (profile_id in (select id from candidate_profiles where is_org_member(organization_id)))
  with check (profile_id in (select id from candidate_profiles where is_org_member(organization_id)));

drop policy "Users manage their own projects" on projects;
create policy "Org members manage projects"
  on projects for all
  using (profile_id in (select id from candidate_profiles where is_org_member(organization_id)))
  with check (profile_id in (select id from candidate_profiles where is_org_member(organization_id)));

drop policy "Users manage their own achievements" on achievements;
create policy "Org members manage achievements"
  on achievements for all
  using (profile_id in (select id from candidate_profiles where is_org_member(organization_id)))
  with check (profile_id in (select id from candidate_profiles where is_org_member(organization_id)));

drop policy "Users manage their own references" on "references";
create policy "Org members manage references"
  on "references" for all
  using (profile_id in (select id from candidate_profiles where is_org_member(organization_id)))
  with check (profile_id in (select id from candidate_profiles where is_org_member(organization_id)));
