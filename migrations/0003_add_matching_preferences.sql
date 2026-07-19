-- ============================================================
-- Migration 0003: Add structured candidate preferences (cv_tracks)
-- and normalized job attributes (jobs), for staged Stage-1/Stage-2
-- matching. Designed for Kenya-first MVP, scaling to Gulf/global.
-- Applied directly to Supabase via MCP on 2026-07-19.
-- ============================================================

-- Candidate preferences are per-track (not per-profile): a candidate
-- may accept Gulf relocation on one track but not another. Each field
-- exists to drive a specific Stage-1 filter -- no speculative fields.

alter table cv_tracks
  add column preferred_locations text[] not null default '{}',
  add column preferred_countries text[] not null default '{}',
  add column employment_types text[] not null default '{}',
  add column seniority_levels text[] not null default '{}',
  add column industries text[] not null default '{}',
  add column work_mode text[] not null default '{}',
  add column willing_to_relocate boolean not null default false,
  add column visa_sponsorship_required boolean,
  add column work_authorization_status text,
  add column salary_expectation_min numeric,
  add column salary_expectation_max numeric,
  add column salary_currency text;

-- Job attributes: a normalized, connector-populated layer separate
-- from raw_json (which stays the untouched per-source dump). Keys are
-- a known, versioned set (employment_type, seniority_level, industry,
-- work_mode, country, visa_sponsorship, salary_min/max/currency).
-- Connectors populate whatever subset they can actually extract --
-- absent keys are just absent, never guessed. The filtering engine
-- must check key presence before applying a rule, so missing
-- attributes are gracefully skipped, not treated as a failed match.

alter table jobs
  add column attributes jsonb not null default '{}'::jsonb;

create index idx_jobs_attributes on jobs using gin (attributes);
