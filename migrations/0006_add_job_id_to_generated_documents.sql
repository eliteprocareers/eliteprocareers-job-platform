-- ============================================================
-- Migration 0006: Add job_id to generated_documents.
--
-- This column was applied manually against production Supabase in
-- the session that built the corrected documents.py router (branch
-- fix/job-scoped-versioning, commit 0f599e7) but the migration file
-- itself was never committed to the repo -- a real gap, since
-- migrations/ is supposed to be the reproducible source of truth for
-- schema state, not something applied ad hoc via the SQL Editor and
-- left undocumented. Added here after the fact, confirmed against
-- the live table via Supabase MCP (list_tables verbose + a direct
-- pg_indexes query) this session: generated_documents.job_id exists
-- in production as a nullable uuid with a foreign key to jobs.id,
-- and an index named idx_generated_documents_track_job_doctype
-- already covers (cv_track_id, job_id, doc_type). This file makes
-- that state reproducible for a fresh environment; it does not need
-- to be re-applied to the existing production project.
--
-- Nullable, not backfilled: this project's existing rows (created
-- before job_id existed) have nothing recorded about which job they
-- were generated for. Not recoverable after the fact. New rows going
-- forward always set job_id.
--
-- Versioning implication (the actual bug this fixes): document
-- versioning is scoped by (cv_track_id, job_id, doc_type), not just
-- (cv_track_id, doc_type). Before this column existed, generating a
-- second job's CV under the same track would silently become "the"
-- latest CV for the whole track, with no way to tell the two apart.
-- ============================================================

alter table public.generated_documents
  add column job_id uuid references public.jobs(id);

create index if not exists idx_generated_documents_track_job_doctype
  on public.generated_documents (cv_track_id, job_id, doc_type);
