-- ============================================================
-- Migration 0005: Add cv_uploads, for real status-polling on
-- background CV parse jobs triggered via POST /profile/cv-upload.
-- Same status-polling shape as matching_runs (migration 0004) --
-- the frontend already knows this pattern from Stage 2.
--
-- Deliberately does NOT store the uploaded file itself (no bytea
-- column, no Supabase Storage reference yet) -- only the extracted
-- raw_text, for debugging/audit and so a failed *parse* (LLM step)
-- could in principle be retried without re-extraction. A failed
-- *extraction* (unreadable PDF/DOCX) still requires re-upload.
-- Storing the original file is a known follow-up, not done here --
-- see handover.
-- ============================================================

create table cv_uploads (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  filename text not null,
  file_size_bytes integer not null,
  status text not null default 'processing'
    check (status in ('processing','completed','failed')),
  raw_text text,
  fields_extracted integer,
  error_message text,
  started_at timestamptz not null default now(),
  completed_at timestamptz
);

alter table cv_uploads enable row level security;

create policy "Users manage their own cv_uploads"
  on cv_uploads for all
  using (user_id = auth.uid())
  with check (user_id = auth.uid());

create index idx_cv_uploads_user on cv_uploads(user_id);
