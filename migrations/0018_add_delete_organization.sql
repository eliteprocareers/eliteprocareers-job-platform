-- ============================================================
-- Migration 0018: delete_organization (Phase 4, roadmap item
-- flagged as a known limitation in v37's handover §8: multi-org
-- shipped a one-click "+ New org" flow with no corresponding
-- undo, so a mistakenly-created org was permanent)
-- ============================================================
-- Context: `organizations` has no DELETE RLS policy at all
-- (confirmed by reading pg_policy directly) -- a plain
-- client-scoped delete would be blocked outright, regardless of
-- FK constraints. And even if RLS allowed it, six tables
-- (candidate_profiles, cv_tracks, applications, matching_runs,
-- user_job_matches, generated_documents) have a NOT NULL,
-- no-default organization_id FK with ON DELETE NO ACTION
-- (confirmed against information_schema/referential_constraints,
-- not assumed) -- deleting an org with any real career data
-- attached would fail at the database level with a raw FK
-- violation, or -- worse, if those FKs are ever loosened later --
-- silently orphan a candidate's CV tracks, applications, and
-- generated documents. Neither outcome is acceptable, so this is
-- deliberately NOT a general-purpose "delete my org and everything
-- in it" operation. It only deletes an org that has zero rows in
-- any of those six tables -- i.e. exactly the "created it by
-- accident via the one-click + New org link, never used it"
-- scenario this was built for. An org with real data can still
-- only be abandoned via leave_organization() (if another owner
-- exists) or left as-is; a genuine "delete my org and all its
-- data" feature, if ever wanted, is a deliberately separate,
-- much heavier decision and out of scope here.
--
-- Confirmed create_organization_with_owner() only ever inserts
-- into organizations + organization_members (no auto-created
-- cv_track/candidate_profile) -- so a freshly-created, never-used
-- org is genuinely empty of all six guarded tables, and this
-- guard doesn't block the actual target scenario.
--
-- Additional guards, same defense-in-depth style as
-- leave_organization():
--   - only an owner may delete (checked here at the RPC layer,
--     not just via the app-layer Permission.delete_organization --
--     same belt-and-suspenders as every other org-boundary RPC)
--   - refuses if any other member exists (deleting out from under
--     other members without their knowledge is a separate,
--     unbuilt flow -- they'd need to be removed first via the
--     existing admin remove_member path)
--   - refuses if this is the caller's only organization membership
--     -- CurrentUser's active-org resolution (migration 0017) falls
--     back to "the caller's oldest membership" when no header is
--     sent, and has no defined behavior for zero memberships; this
--     guard prevents ever reaching that undefined state
--
-- organization_invites/organization_candidate_assignments/
-- organization_members rows for this org all cascade automatically
-- (ON DELETE CASCADE, confirmed against
-- information_schema.referential_constraints) -- an empty org by
-- definition has no assignments, and any pending invites to a
-- deleted org are correctly meaningless, so no explicit cleanup
-- needed for those three.
-- ============================================================

create or replace function delete_organization(p_organization_id uuid)
returns uuid
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_role text;
  v_other_membership_count int;
begin
  if (select auth.uid()) is null then
    raise exception 'Not authenticated.';
  end if;

  select role into v_role
  from public.organization_members
  where organization_id = p_organization_id
    and user_id = (select auth.uid());

  if v_role is null then
    raise exception 'You are not a member of that organization.';
  end if;

  if v_role != 'owner' then
    raise exception 'Only an owner can delete an organization.';
  end if;

  if exists (
    select 1 from public.organization_members
    where organization_id = p_organization_id
      and user_id != (select auth.uid())
  ) then
    raise exception 'Remove all other members before deleting this organization.';
  end if;

  select count(*) into v_other_membership_count
  from public.organization_members
  where user_id = (select auth.uid())
    and organization_id != p_organization_id;

  if v_other_membership_count = 0 then
    raise exception 'Can''t delete your only organization. Create or join another organization first.';
  end if;

  if exists (select 1 from public.candidate_profiles where organization_id = p_organization_id)
    or exists (select 1 from public.cv_tracks where organization_id = p_organization_id)
    or exists (select 1 from public.applications where organization_id = p_organization_id)
    or exists (select 1 from public.matching_runs where organization_id = p_organization_id)
    or exists (select 1 from public.user_job_matches where organization_id = p_organization_id)
    or exists (select 1 from public.generated_documents where organization_id = p_organization_id)
  then
    raise exception 'This organization has candidates, tracks, applications, or documents and can''t be deleted.';
  end if;

  delete from public.organizations where id = p_organization_id;

  return p_organization_id;
end;
$$;

grant execute on function delete_organization(uuid) to authenticated;
