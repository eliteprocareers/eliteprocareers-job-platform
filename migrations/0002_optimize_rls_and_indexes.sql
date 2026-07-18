-- ============================================================
-- Migration 0002: Fix auth_rls_initplan + add missing FK indexes
-- Applied directly to Supabase via MCP on 2026-07-18
-- ============================================================

-- Fix function search_path (security advisory)
alter function set_updated_at() set search_path = '';

-- ============================================================
-- Fix auth_rls_initplan: wrap auth.uid()/auth.role() in (select ...)
-- so Postgres evaluates once per query, not once per row
-- ============================================================

drop policy "Users manage their own profile" on candidate_profiles;
create policy "Users manage their own profile"
  on candidate_profiles for all
  using (user_id = (select auth.uid()))
  with check (user_id = (select auth.uid()));

drop policy "Authenticated users can read skills catalog" on skills;
create policy "Authenticated users can read skills catalog"
  on skills for select
  using ((select auth.role()) = 'authenticated');

drop policy "Authenticated users can add new skills" on skills;
create policy "Authenticated users can add new skills"
  on skills for insert
  with check ((select auth.role()) = 'authenticated');

drop policy "Users manage their own candidate_skills" on candidate_skills;
create policy "Users manage their own candidate_skills"
  on candidate_skills for all
  using (profile_id in (select id from candidate_profiles where user_id = (select auth.uid())))
  with check (profile_id in (select id from candidate_profiles where user_id = (select auth.uid())));

drop policy "Users manage their own work_experience" on work_experience;
create policy "Users manage their own work_experience"
  on work_experience for all
  using (profile_id in (select id from candidate_profiles where user_id = (select auth.uid())))
  with check (profile_id in (select id from candidate_profiles where user_id = (select auth.uid())));

drop policy "Users manage their own education" on education;
create policy "Users manage their own education"
  on education for all
  using (profile_id in (select id from candidate_profiles where user_id = (select auth.uid())))
  with check (profile_id in (select id from candidate_profiles where user_id = (select auth.uid())));

drop policy "Users manage their own certifications" on certifications;
create policy "Users manage their own certifications"
  on certifications for all
  using (profile_id in (select id from candidate_profiles where user_id = (select auth.uid())))
  with check (profile_id in (select id from candidate_profiles where user_id = (select auth.uid())));

drop policy "Users manage their own languages" on languages;
create policy "Users manage their own languages"
  on languages for all
  using (profile_id in (select id from candidate_profiles where user_id = (select auth.uid())))
  with check (profile_id in (select id from candidate_profiles where user_id = (select auth.uid())));

drop policy "Users manage their own projects" on projects;
create policy "Users manage their own projects"
  on projects for all
  using (profile_id in (select id from candidate_profiles where user_id = (select auth.uid())))
  with check (profile_id in (select id from candidate_profiles where user_id = (select auth.uid())));

drop policy "Users manage their own achievements" on achievements;
create policy "Users manage their own achievements"
  on achievements for all
  using (profile_id in (select id from candidate_profiles where user_id = (select auth.uid())))
  with check (profile_id in (select id from candidate_profiles where user_id = (select auth.uid())));

drop policy "Users manage their own references" on "references";
create policy "Users manage their own references"
  on "references" for all
  using (profile_id in (select id from candidate_profiles where user_id = (select auth.uid())))
  with check (profile_id in (select id from candidate_profiles where user_id = (select auth.uid())));

drop policy "Users manage their own cv_tracks" on cv_tracks;
create policy "Users manage their own cv_tracks"
  on cv_tracks for all
  using (user_id = (select auth.uid()))
  with check (user_id = (select auth.uid()));

drop policy "Authenticated users can read jobs" on jobs;
create policy "Authenticated users can read jobs"
  on jobs for select
  using ((select auth.role()) = 'authenticated');

drop policy "Users manage their own user_job_matches" on user_job_matches;
create policy "Users manage their own user_job_matches"
  on user_job_matches for all
  using (user_id = (select auth.uid()))
  with check (user_id = (select auth.uid()));

drop policy "Users manage their own applications" on applications;
create policy "Users manage their own applications"
  on applications for all
  using (user_id = (select auth.uid()))
  with check (user_id = (select auth.uid()));

drop policy "Users manage their own generated_documents" on generated_documents;
create policy "Users manage their own generated_documents"
  on generated_documents for all
  using (user_id = (select auth.uid()))
  with check (user_id = (select auth.uid()));

-- ============================================================
-- Add missing covering indexes for foreign keys
-- ============================================================

create index idx_achievements_profile on achievements(profile_id);
create index idx_achievements_work_experience on achievements(work_experience_id);
create index idx_applications_cv_track on applications(cv_track_id);
create index idx_candidate_skills_skill on candidate_skills(skill_id);
create index idx_generated_documents_application on generated_documents(application_id);
create index idx_languages_profile on languages(profile_id);
create index idx_projects_profile on projects(profile_id);
create index idx_references_profile on "references"(profile_id);
create index idx_user_job_matches_cv_track on user_job_matches(cv_track_id);
