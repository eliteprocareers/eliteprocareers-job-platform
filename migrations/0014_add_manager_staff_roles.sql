-- ============================================================
-- Migration 0014: Four-tier role model (Phase 4, part 8 -- RBAC foundation)
-- ============================================================
-- Context: organization_members.role and organization_invites.role
-- were 3-tier (owner/admin/member) since migration 0007. This expands
-- to 4 tiers (owner/admin/manager/staff), the foundation for a real
-- permission system rather than the binary is_org_admin()-or-not
-- checks used so far. 'member' is retired in favor of 'staff' as the
-- base tier -- confirmed by grep that no RLS policy or function
-- references the literal string 'member' anywhere except these two
-- CHECK constraints and their defaults, so this is a clean rename,
-- not a breaking change to anything else.
--
-- is_org_admin() (owner/admin) and is_org_member() (any role) are
-- both untouched -- they don't need to change. Every existing
-- RLS policy gated by is_org_admin() keeps exactly its current
-- meaning: owners and admins still get org-administration privileges;
-- manager/staff do not. What manager/staff *can* do is enforced at
-- the application layer via organizations/permissions.py, not new
-- RLS -- the existing org-scoped tables (candidate_profiles,
-- cv_tracks, applications, generated_documents, user_job_matches)
-- already scope by organization_id via is_org_member(), which
-- includes manager/staff already; further row-level restriction by
-- role within an org is an app-layer permission check, not an RLS
-- concern, consistent with how this project has drawn that line so
-- far (RLS = tenant isolation, app layer = who-can-do-what within a
-- tenant).
-- ============================================================

-- Existing data: rename 'member' -> 'staff' before changing the
-- constraint, so nothing is briefly in an invalid state.
update organization_members set role = 'staff' where role = 'member';
update organization_invites set role = 'staff' where role = 'member';

alter table organization_members drop constraint organization_members_role_check;
alter table organization_members
  add constraint organization_members_role_check
  check (role in ('owner', 'admin', 'manager', 'staff'));
alter table organization_members alter column role set default 'staff';

alter table organization_invites drop constraint organization_invites_role_check;
alter table organization_invites
  add constraint organization_invites_role_check
  check (role in ('admin', 'manager', 'staff'));  -- can't invite someone in as 'owner'
alter table organization_invites alter column role set default 'staff';
