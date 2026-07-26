-- ============================================================
-- Rollback for migration 0007 (multi-tenant organizations layer)
-- ============================================================
-- Restores every RLS policy to its exact pre-0007 definition (verified
-- against production's live pg_policies output, not just the local
-- migration files, since this project has known migration-tracking
-- drift -- see handover v35 §9/§11).
-- Run this as a single transaction. Safe to run even if 0007 partially
-- applied, EXCEPT: if new rows were inserted into organizations /
-- organization_members by application code (not just the backfill)
-- after 0007 went live, those rows and any data that came to depend
-- on them are lost on rollback. Check for that before running this in
-- production (see the pre-rollback check query at the bottom of this
-- file's companion review).
-- ============================================================

-- ---- 1. Restore child-table policies (profile_id-scoped) ----

drop policy if exists "Org members manage candidate_skills" on candidate_skills;
create policy "Users manage their own candidate_skills"
  on candidate_skills for all
  using (profile_id in (select id from candidate_profiles where user_id = (select auth.uid())))
  with check (profile_id in (select id from candidate_profiles where user_id = (select auth.uid())));

drop policy if exists "Org members manage work_experience" on work_experience;
create policy "Users manage their own work_experience"
  on work_experience for all
  using (profile_id in (select id from candidate_profiles where user_id = (select auth.uid())))
  with check (profile_id in (select id from candidate_profiles where user_id = (select auth.uid())));

drop policy if exists "Org members manage education" on education;
create policy "Users manage their own education"
  on education for all
  using (profile_id in (select id from candidate_profiles where user_id = (select auth.uid())))
  with check (profile_id in (select id from candidate_profiles where user_id = (select auth.uid())));

drop policy if exists "Org members manage certifications" on certifications;
create policy "Users manage their own certifications"
  on certifications for all
  using (profile_id in (select id from candidate_profiles where user_id = (select auth.uid())))
  with check (profile_id in (select id from candidate_profiles where user_id = (select auth.uid())));

drop policy if exists "Org members manage languages" on languages;
create policy "Users manage their own languages"
  on languages for all
  using (profile_id in (select id from candidate_profiles where user_id = (select auth.uid())))
  with check (profile_id in (select id from candidate_profiles where user_id = (select auth.uid())));

drop policy if exists "Org members manage projects" on projects;
create policy "Users manage their own projects"
  on projects for all
  using (profile_id in (select id from candidate_profiles where user_id = (select auth.uid())))
  with check (profile_id in (select id from candidate_profiles where user_id = (select auth.uid())));

drop policy if exists "Org members manage achievements" on achievements;
create policy "Users manage their own achievements"
  on achievements for all
  using (profile_id in (select id from candidate_profiles where user_id = (select auth.uid())))
  with check (profile_id in (select id from candidate_profiles where user_id = (select auth.uid())));

drop policy if exists "Org members manage references" on "references";
create policy "Users manage their own references"
  on "references" for all
  using (profile_id in (select id from candidate_profiles where user_id = (select auth.uid())))
  with check (profile_id in (select id from candidate_profiles where user_id = (select auth.uid())));

-- ---- 2. Restore the 5 owner-keyed table policies ----

drop policy if exists "Org members manage candidate_profiles" on candidate_profiles;
create policy "Users manage their own profile"
  on candidate_profiles for all
  using (user_id = (select auth.uid()))
  with check (user_id = (select auth.uid()));

drop policy if exists "Org members manage cv_tracks" on cv_tracks;
create policy "Users manage their own cv_tracks"
  on cv_tracks for all
  using (user_id = (select auth.uid()))
  with check (user_id = (select auth.uid()));

drop policy if exists "Org members manage user_job_matches" on user_job_matches;
create policy "Users manage their own user_job_matches"
  on user_job_matches for all
  using (user_id = (select auth.uid()))
  with check (user_id = (select auth.uid()));

drop policy if exists "Org members manage applications" on applications;
create policy "Users manage their own applications"
  on applications for all
  using (user_id = (select auth.uid()))
  with check (user_id = (select auth.uid()));

drop policy if exists "Org members manage generated_documents" on generated_documents;
create policy "Users manage their own generated_documents"
  on generated_documents for all
  using (user_id = (select auth.uid()))
  with check (user_id = (select auth.uid()));

-- ---- 3. Drop organization_id columns + their indexes ----

drop index if exists idx_candidate_profiles_org;
drop index if exists idx_cv_tracks_org;
drop index if exists idx_user_job_matches_org;
drop index if exists idx_applications_org;
drop index if exists idx_generated_documents_org;

alter table candidate_profiles drop column if exists organization_id;
alter table cv_tracks drop column if exists organization_id;
alter table user_job_matches drop column if exists organization_id;
alter table applications drop column if exists organization_id;
alter table generated_documents drop column if exists organization_id;

-- ---- 4. Drop organizations / organization_members + helper functions ----

drop policy if exists "Members can view their organizations" on organizations;
drop policy if exists "Admins/owners can update their organization" on organizations;
drop policy if exists "Members can view fellow org members" on organization_members;
drop policy if exists "Admins/owners can add members" on organization_members;
drop policy if exists "Admins/owners can update member roles" on organization_members;
drop policy if exists "Admins/owners can remove members" on organization_members;

drop index if exists idx_organization_members_org;
drop index if exists idx_organization_members_user;

drop table if exists organization_members;
drop table if exists organizations;

drop function if exists is_org_member(uuid);
drop function if exists is_org_admin(uuid);
