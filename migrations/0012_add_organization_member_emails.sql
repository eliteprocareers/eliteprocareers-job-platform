-- ============================================================
-- Migration 0012: Organization member emails (Phase 4, part 4)
-- ============================================================
-- Context: Organization.tsx (v33) shows member IDs, not emails,
-- because organization_members has no email column and PostgREST
-- doesn't expose the auth schema for a client-side join -- confirmed
-- by inspection, not assumed. This closes that specific gap.
--
-- Design decision: a SECURITY DEFINER function, not a public view
-- over auth.users. A view would need its own access control bolted
-- on separately; a function lets the same is_org_member() check that
-- already gates the organization_members SELECT RLS policy gate this
-- too, in one place, with the same semantics -- any member of an org
-- can see their fellow members' emails, matching the existing
-- visibility model for who's in the org at all (the SELECT policy is
-- "Members can view fellow org members", not admin-only). This adds
-- an attribute to something already visible, not new exposure.
-- ============================================================

create or replace function list_organization_members_with_email(p_organization_id uuid)
returns table (
  id uuid,
  organization_id uuid,
  user_id uuid,
  role text,
  created_at timestamptz,
  email text
)
language sql
security definer
set search_path = ''
stable
as $$
  select m.id, m.organization_id, m.user_id, m.role, m.created_at, u.email::text
  from public.organization_members m
  join auth.users u on u.id = m.user_id
  where m.organization_id = p_organization_id
    and public.is_org_member(p_organization_id);
$$;

grant execute on function list_organization_members_with_email(uuid) to authenticated;
