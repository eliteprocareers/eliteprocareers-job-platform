-- ============================================================
-- Migration 0011: Organization creation + invite flow (Phase 4, part 2)
-- ============================================================
-- Context: 0007 stood up the organizations/organization_members schema
-- and RLS, but deliberately left org creation and membership bootstrap
-- unimplemented in application code (per 0007's own comment: "no insert
-- policy on organizations... org creation goes through the backend's
-- service_role key"). As of this migration, that path still doesn't
-- exist anywhere -- confirmed by inspection (no INSERT policy on
-- organizations, is_org_admin()-gated INSERT on organization_members
-- with no bootstrap route, zero rows in organization_invites because
-- the table didn't exist). This migration closes that gap.
--
-- Design decision (deviates from 0007's stated plan, deliberately):
-- rather than routing org-creation and invite-acceptance through the
-- backend's service_role key (two non-atomic REST calls each), both
-- are implemented as single SECURITY DEFINER Postgres functions,
-- called with the user's own JWT (auth.uid()/auth.jwt() available
-- inside the function body). This is the same atomic-RPC pattern
-- already proven on this project's sibling codebase (Trimora POS's
-- complete_salon_onboarding fix, commits 776edab/9129d73) and avoids
-- the exact failure class this project has already hit twice
-- (Bug #1, Bug #3 in handover v31 -- silent partial writes from
-- multi-step operations with no transaction wrapping them). It also
-- means service_role stays untouched by anything request-triggered,
-- consistent with dependencies.py's original load-bearing rule.
--
-- One org per user, for now: create_organization_with_owner() and
-- accept_organization_invite() both reject the call if the caller
-- already belongs to an organization. CurrentUser.organization_id
-- (api/dependencies.py) resolves via `limit 1` against
-- organization_members, which only works if membership is unambiguous.
-- Multi-org-per-user is a real future decision, not built here --
-- flagged explicitly in this session's handover.
-- ============================================================

-- ============================================================
-- organization_invites
-- ============================================================

create table organization_invites (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references organizations(id) on delete cascade,
  email text not null,
  role text not null default 'member'
    check (role in ('admin', 'member')),  -- can't invite someone in as 'owner'
  token text not null unique default replace(gen_random_uuid()::text, '-', ''),
  status text not null default 'pending'
    check (status in ('pending', 'accepted', 'revoked', 'expired')),
  invited_by uuid not null references auth.users(id),
  created_at timestamptz not null default now(),
  expires_at timestamptz not null default (now() + interval '7 days'),
  accepted_at timestamptz
);

alter table organization_invites enable row level security;

create index idx_organization_invites_org on organization_invites(organization_id);
create index idx_organization_invites_email on organization_invites(lower(email));

-- ============================================================
-- RLS: organization_invites
-- Admin/owner-facing operations (create, list, revoke) go through
-- normal RLS via is_org_admin(), same as organization_members already
-- does -- no new bootstrap problem here, since the caller is already
-- a member by definition. Only the invitee-facing operations (preview
-- an invite before accepting, accept it) cross a membership boundary
-- that RLS structurally can't authorize -- those are the two SECURITY
-- DEFINER functions below, not RLS policies.
-- ============================================================

create policy "Admins/owners can view invites for their org"
  on organization_invites for select
  using (is_org_admin(organization_id));

create policy "Admins/owners can create invites for their org"
  on organization_invites for insert
  with check (is_org_admin(organization_id));

create policy "Admins/owners can revoke invites for their org"
  on organization_invites for update
  using (is_org_admin(organization_id))
  with check (is_org_admin(organization_id));

-- ============================================================
-- create_organization_with_owner: atomic org creation + owner seat.
-- Runs as the calling user (their JWT provides auth.uid()); SECURITY
-- DEFINER lets it bypass the (deliberately absent) INSERT policy on
-- organizations and the is_org_admin()-gated INSERT policy on
-- organization_members, for this one bootstrap case only.
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

  if exists (
    select 1 from public.organization_members
    where user_id = (select auth.uid())
  ) then
    raise exception 'You already belong to an organization. Multi-org membership per user is not supported yet.';
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

grant execute on function create_organization_with_owner(text, text) to authenticated;

-- ============================================================
-- get_invite_preview: read-only, unauthenticated-safe lookup by token,
-- for a "you've been invited to X" landing page before the person has
-- even logged in. Deliberately returns only what's safe to show
-- someone holding the link -- no internal ids, no other members.
-- ============================================================

create or replace function get_invite_preview(p_token text)
returns table (
  organization_name text,
  email text,
  role text,
  status text,
  expires_at timestamptz
)
language sql
security definer
set search_path = ''
stable
as $$
  select o.name, i.email, i.role, i.status, i.expires_at
  from public.organization_invites i
  join public.organizations o on o.id = i.organization_id
  where i.token = p_token;
$$;

grant execute on function get_invite_preview(text) to anon, authenticated;

-- ============================================================
-- accept_organization_invite: atomic claim. Validates the invite
-- (exists, pending, not expired, email matches the caller's verified
-- JWT email -- never a client-supplied email), then inserts membership
-- and marks the invite accepted in the same transaction. Mirrors the
-- Trimora POS complete_salon_onboarding fix (atomic invite claiming
-- inside the RPC, not two separate calls).
-- ============================================================

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
  for update;  -- lock the row: two near-simultaneous accepts on the same token must not both succeed

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
  ) then
    raise exception 'You already belong to an organization. Multi-org membership per user is not supported yet.';
  end if;

  insert into public.organization_members (organization_id, user_id, role)
  values (v_invite.organization_id, (select auth.uid()), v_invite.role);

  update public.organization_invites
  set status = 'accepted', accepted_at = now()
  where id = v_invite.id;

  return v_invite.organization_id;
end;
$$;

grant execute on function accept_organization_invite(text) to authenticated;
