-- ============================================================
-- ElitePro AI Platform — Phase 0 Initial Schema
-- Multi-tenant, RLS-enforced, normalized candidate profile model
-- ============================================================

-- Reusable trigger to keep updated_at current
create or replace function set_updated_at()
returns trigger as $$
begin
  new.updated_at = now();
  return new;
end;
$$ language plpgsql;

-- ============================================================
-- PROFILE DOMAIN
-- ============================================================

create table candidate_profiles (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null unique references auth.users(id) on delete cascade,
  full_name text,
  headline text,
  summary text,
  location text,
  email text,
  phone text,
  linkedin_url text,
  portfolio_url text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table candidate_profiles enable row level security;

create policy "Users manage their own profile"
  on candidate_profiles for all
  using (user_id = auth.uid())
  with check (user_id = auth.uid());

create trigger trg_candidate_profiles_updated_at
  before update on candidate_profiles
  for each row execute function set_updated_at();


create table skills (
  id uuid primary key default gen_random_uuid(),
  name text not null unique,
  created_at timestamptz not null default now()
);

alter table skills enable row level security;

create policy "Authenticated users can read skills catalog"
  on skills for select
  using (auth.role() = 'authenticated');

create policy "Authenticated users can add new skills"
  on skills for insert
  with check (auth.role() = 'authenticated');


create table candidate_skills (
  id uuid primary key default gen_random_uuid(),
  profile_id uuid not null references candidate_profiles(id) on delete cascade,
  skill_id uuid not null references skills(id) on delete cascade,
  proficiency_level text check (proficiency_level in ('beginner','intermediate','advanced','expert')),
  years_experience numeric,
  created_at timestamptz not null default now(),
  unique (profile_id, skill_id)
);

alter table candidate_skills enable row level security;

create policy "Users manage their own candidate_skills"
  on candidate_skills for all
  using (profile_id in (select id from candidate_profiles where user_id = auth.uid()))
  with check (profile_id in (select id from candidate_profiles where user_id = auth.uid()));


create table work_experience (
  id uuid primary key default gen_random_uuid(),
  profile_id uuid not null references candidate_profiles(id) on delete cascade,
  company text not null,
  title text not null,
  location text,
  start_date date,
  end_date date,
  is_current boolean not null default false,
  description text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table work_experience enable row level security;

create policy "Users manage their own work_experience"
  on work_experience for all
  using (profile_id in (select id from candidate_profiles where user_id = auth.uid()))
  with check (profile_id in (select id from candidate_profiles where user_id = auth.uid()));

create trigger trg_work_experience_updated_at
  before update on work_experience
  for each row execute function set_updated_at();


create table education (
  id uuid primary key default gen_random_uuid(),
  profile_id uuid not null references candidate_profiles(id) on delete cascade,
  institution text not null,
  degree text,
  field_of_study text,
  start_date date,
  end_date date,
  description text,
  created_at timestamptz not null default now()
);

alter table education enable row level security;

create policy "Users manage their own education"
  on education for all
  using (profile_id in (select id from candidate_profiles where user_id = auth.uid()))
  with check (profile_id in (select id from candidate_profiles where user_id = auth.uid()));


create table certifications (
  id uuid primary key default gen_random_uuid(),
  profile_id uuid not null references candidate_profiles(id) on delete cascade,
  name text not null,
  issuer text,
  issue_date date,
  expiry_date date,
  credential_id text,
  credential_url text,
  created_at timestamptz not null default now()
);

alter table certifications enable row level security;

create policy "Users manage their own certifications"
  on certifications for all
  using (profile_id in (select id from candidate_profiles where user_id = auth.uid()))
  with check (profile_id in (select id from candidate_profiles where user_id = auth.uid()));


create table languages (
  id uuid primary key default gen_random_uuid(),
  profile_id uuid not null references candidate_profiles(id) on delete cascade,
  language text not null,
  proficiency text check (proficiency in ('basic','conversational','fluent','native')),
  created_at timestamptz not null default now()
);

alter table languages enable row level security;

create policy "Users manage their own languages"
  on languages for all
  using (profile_id in (select id from candidate_profiles where user_id = auth.uid()))
  with check (profile_id in (select id from candidate_profiles where user_id = auth.uid()));


create table projects (
  id uuid primary key default gen_random_uuid(),
  profile_id uuid not null references candidate_profiles(id) on delete cascade,
  name text not null,
  description text,
  url text,
  start_date date,
  end_date date,
  created_at timestamptz not null default now()
);

alter table projects enable row level security;

create policy "Users manage their own projects"
  on projects for all
  using (profile_id in (select id from candidate_profiles where user_id = auth.uid()))
  with check (profile_id in (select id from candidate_profiles where user_id = auth.uid()));


create table achievements (
  id uuid primary key default gen_random_uuid(),
  profile_id uuid not null references candidate_profiles(id) on delete cascade,
  work_experience_id uuid references work_experience(id) on delete set null,
  description text not null,
  achieved_date date,
  created_at timestamptz not null default now()
);

alter table achievements enable row level security;

create policy "Users manage their own achievements"
  on achievements for all
  using (profile_id in (select id from candidate_profiles where user_id = auth.uid()))
  with check (profile_id in (select id from candidate_profiles where user_id = auth.uid()));


create table "references" (
  id uuid primary key default gen_random_uuid(),
  profile_id uuid not null references candidate_profiles(id) on delete cascade,
  name text not null,
  relationship text,
  company text,
  email text,
  phone text,
  created_at timestamptz not null default now()
);

alter table "references" enable row level security;

create policy "Users manage their own references"
  on "references" for all
  using (profile_id in (select id from candidate_profiles where user_id = auth.uid()))
  with check (profile_id in (select id from candidate_profiles where user_id = auth.uid()));


-- ============================================================
-- CV TRACKS
-- ============================================================

create table cv_tracks (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  track_name text not null,
  target_roles text[],
  scoring_weights jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table cv_tracks enable row level security;

create policy "Users manage their own cv_tracks"
  on cv_tracks for all
  using (user_id = auth.uid())
  with check (user_id = auth.uid());

create trigger trg_cv_tracks_updated_at
  before update on cv_tracks
  for each row execute function set_updated_at();


-- ============================================================
-- JOBS (globally deduped — no user_id)
-- ============================================================

create table jobs (
  id uuid primary key default gen_random_uuid(),
  source text not null,           -- 'greenhouse' | 'lever' | 'workday'
  external_id text not null,      -- ID from the ATS's own system
  company text not null,
  title text not null,
  description text,
  url text,
  location text,
  posted_at timestamptz,
  ingested_at timestamptz not null default now(),
  raw_json jsonb,
  unique (source, external_id)
);

alter table jobs enable row level security;

create policy "Authenticated users can read jobs"
  on jobs for select
  using (auth.role() = 'authenticated');

-- No insert/update/delete policy for authenticated users —
-- job ingestion writes via the service_role key, which bypasses RLS entirely.


-- ============================================================
-- SCORING: per-user, per-track match against a job
-- ============================================================

create table user_job_matches (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  job_id uuid not null references jobs(id) on delete cascade,
  cv_track_id uuid not null references cv_tracks(id) on delete cascade,
  match_score numeric,
  ai_rationale text,
  scored_at timestamptz not null default now(),
  unique (user_id, job_id, cv_track_id)
);

alter table user_job_matches enable row level security;

create policy "Users manage their own user_job_matches"
  on user_job_matches for all
  using (user_id = auth.uid())
  with check (user_id = auth.uid());


-- ============================================================
-- APPLICATIONS
-- ============================================================

create table applications (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  job_id uuid not null references jobs(id) on delete cascade,
  cv_track_id uuid not null references cv_tracks(id) on delete cascade,
  status text not null default 'draft'
    check (status in ('draft','submitted','interviewing','rejected','offer','withdrawn')),
  applied_at timestamptz,
  notes text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table applications enable row level security;

create policy "Users manage their own applications"
  on applications for all
  using (user_id = auth.uid())
  with check (user_id = auth.uid());

create trigger trg_applications_updated_at
  before update on applications
  for each row execute function set_updated_at();


-- ============================================================
-- GENERATED DOCUMENTS (versioned — never overwritten)
-- ============================================================

create table generated_documents (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  cv_track_id uuid not null references cv_tracks(id) on delete cascade,
  application_id uuid references applications(id) on delete set null,
  doc_type text not null check (doc_type in ('cv','cover_letter','screening_answer')),
  content text not null,
  version integer not null default 1,
  ai_model_used text,
  created_at timestamptz not null default now()
);

alter table generated_documents enable row level security;

create policy "Users manage their own generated_documents"
  on generated_documents for all
  using (user_id = auth.uid())
  with check (user_id = auth.uid());


-- ============================================================
-- INDEXES for common lookups
-- ============================================================

create index idx_candidate_skills_profile on candidate_skills(profile_id);
create index idx_work_experience_profile on work_experience(profile_id);
create index idx_education_profile on education(profile_id);
create index idx_certifications_profile on certifications(profile_id);
create index idx_cv_tracks_user on cv_tracks(user_id);
create index idx_jobs_source_external on jobs(source, external_id);
create index idx_user_job_matches_user on user_job_matches(user_id);
create index idx_user_job_matches_job on user_job_matches(job_id);
create index idx_applications_user on applications(user_id);
create index idx_applications_job on applications(job_id);
create index idx_generated_documents_user on generated_documents(user_id);
create index idx_generated_documents_track on generated_documents(cv_track_id);
