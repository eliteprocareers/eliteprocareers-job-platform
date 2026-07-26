-- ============================================================
-- Migration 0008: Add cover_letter_style_samples.
--
-- Per founder decision (2026-07-26): a cover letter "upload" is NOT
-- a real cover letter document -- it's a writing sample used only to
-- influence the tone/style of future AI-generated cover letters. It
-- never becomes a generated_documents row and is never presented to
-- an employer.
--
-- One row per user (unique user_id) -- uploading a new sample
-- replaces the old one, there's no versioning/history here, since
-- only the single most recent sample is ever used to steer style.
-- Stores extracted raw_text only, same reasoning as cv_uploads not
-- storing the original file bytes.
-- ============================================================

create table cover_letter_style_samples (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null unique references auth.users(id) on delete cascade,
  filename text not null,
  sample_text text not null,
  uploaded_at timestamptz not null default now()
);

alter table cover_letter_style_samples enable row level security;

create policy "Users manage their own cover_letter_style_samples"
  on cover_letter_style_samples for all
  using (user_id = auth.uid())
  with check (user_id = auth.uid());

create index idx_cover_letter_style_samples_user on cover_letter_style_samples(user_id);
