-- ============================================================
-- Migration 0013: Leave organization (Phase 4, part 7)
-- ============================================================
-- Context: organization_members' only DELETE policy (migration 0007)
-- is is_org_admin(organization_id) -- confirmed by reading it
-- directly. That means a plain 'member' cannot remove themselves from
-- an org at all under the current RLS; only an admin/owner can remove
-- them. Rather than loosen that DELETE policy to also allow
-- `user_id = auth.uid()` (which would need careful thought about
-- whether a member should also be able to delete OTHER rows they
-- don't own, if the policy were written loosely), this follows the
-- same atomic-RPC pattern already established for
-- create_organization_with_owner/accept_organization_invite:
-- SECURITY DEFINER, scoped to exactly "remove my own membership,
-- nothing else", with the same last-owner orphan guard already used
-- for the admin-driven remove/demote paths (organizations.py router).
-- ============================================================

create or replace function leave_organization()
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
  for update;

  if not found then
    raise exception 'You are not a member of an organization.';
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

grant execute on function leave_organization() to authenticated;
