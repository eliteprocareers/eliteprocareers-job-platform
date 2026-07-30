-- ============================================================
-- Migration 0017: allow multi-org-per-user membership
-- (Phase 4, roadmap item carried forward across seven handovers,
-- unparked 2026-07-29 at founder's direction)
-- ============================================================
-- Context: organization_members was always schema-correct for
-- many-to-many (unique(organization_id, user_id), not
-- unique(user_id) -- see migration 0007) and every RLS helper
-- (is_org_member, is_org_admin, can_view_org_resource) was already
-- written as an EXISTS(...) check against the full membership set,
-- not a single-row assumption. The block was entirely at the RPC
-- layer: create_organization_with_owner() and
-- accept_organization_invite() both explicitly raised "You already
-- belong to an organization" if the caller had any existing
-- membership row. This migration removes that guard from both.
--
-- leave_organization() previously took no argument and did
-- `select * into ... where user_id = auth.uid()` with no org
-- filter -- correct (and the only sane option) when a user has at
-- most one membership row, silently arbitrary (Postgres just takes
-- whichever row postgres happens to pick, no error) once a user can
-- have several. Now takes p_organization_id explicitly and scopes
-- every clause (lookup, last-owner guard, delete) to that org.
--
-- App-layer companion change (not in this migration): the FastAPI
-- CurrentUser dependency's organization_id resolution changes from
-- `.limit(1)` (arbitrary single membership) to an explicit
-- X-Organization-Id header, validated against the caller's full
-- membership list and 403'd if they're not actually a member of
-- what they asked for -- falling back to the single membership
-- (oldest by created_at) when no header is sent, so every existing
-- single-org caller sees zero behavior change. See
-- api/dependencies.py.
-- ============================================================

create or replace function create_organization_with_owner(
  p_name text,
  p_org_type text default 'individual'
)
returns organizations
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_org public.organizations;
begin
  if (select auth.uid()) is null then
    raise exception 'Not authenticated.';
  end if;

  if p_name is null or length(trim(p_name)) = 0 then
    raise exception 'Organization name is required.';
  end if;

  insert into public.organizations (name, org_type)
  values (trim(p_name), coalesce(p_org_type, 'individual'))
  returning * into v_org;

  insert into public.organization_members (organization_id, user_id, role)
  values (v_org.id, (select auth.uid()), 'owner');

  return v_org;
end;
$$;

create or replace function accept_organization_invite(p_token text)
returns uuid
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_invite public.organization_invites;
  v_caller_email text;
begin
  if (select auth.uid()) is null then
    raise exception 'Not authenticated.';
  end if;

  select * into v_invite
  from public.organization_invites
  where token = p_token
  for update;

  if not found then
    raise exception 'Invite not found or already used.';
  end if;

  if v_invite.status = 'accepted' then
    raise exception 'This invite has already been accepted.';
  end if;

  if v_invite.status = 'revoked' then
    raise exception 'This invite has been revoked.';
  end if;

  if v_invite.status != 'pending' or v_invite.expires_at < now() then
    update public.organization_invites set status = 'expired' where id = v_invite.id;
    raise exception 'This invite has expired.';
  end if;

  v_caller_email := lower((select auth.jwt() ->> 'email'));
  if v_caller_email is null or v_caller_email != lower(v_invite.email) then
    raise exception 'This invite was sent to a different email address.';
  end if;

  if exists (
    select 1 from public.organization_members
    where user_id = (select auth.uid())
      and organization_id = v_invite.organization_id
  ) then
    raise exception 'You are already a member of this organization.';
  end if;

  insert into public.organization_members (organization_id, user_id, role)
  values (v_invite.organization_id, (select auth.uid()), v_invite.role);

  update public.organization_invites
  set status = 'accepted', accepted_at = now()
  where id = v_invite.id;

  return v_invite.organization_id;
end;
$$;

create or replace function leave_organization(p_organization_id uuid)
returns uuid
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_membership public.organization_members;
begin
  if (select auth.uid()) is null then
    raise exception 'Not authenticated.';
  end if;

  select * into v_membership
  from public.organization_members
  where user_id = (select auth.uid())
    and organization_id = p_organization_id
  for update;

  if not found then
    raise exception 'You are not a member of that organization.';
  end if;

  if v_membership.role = 'owner' and (
    select count(*) from public.organization_members
    where organization_id = v_membership.organization_id and role = 'owner'
  ) <= 1 then
    raise exception 'Can''t leave as the organization''s last owner. Promote another member to owner first, or delete the organization.';
  end if;

  delete from public.organization_members where id = v_membership.id;

  return v_membership.organization_id;
end;
$$;

-- Signature changed (0 args -> 1 arg) -- drop the old zero-arg
-- overload explicitly so callers get a clear "function does not
-- exist" instead of silently resolving to a stale version.
drop function if exists leave_organization();

grant execute on function create_organization_with_owner(text, text) to authenticated;
grant execute on function accept_organization_invite(text) to authenticated;
grant execute on function leave_organization(uuid) to authenticated;
