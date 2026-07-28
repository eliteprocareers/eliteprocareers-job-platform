import type { MemberRole } from './types';

/**
 * Frontend mirror of organizations/permissions.py's Permission enum
 * and ROLE_PERMISSIONS matrix. Kept manually in sync rather than
 * generated, same as every other type in this file that mirrors a
 * backend Pydantic model -- if you change one side, change the other.
 *
 * This governs what the UI shows/hides. It is NOT the real
 * authorization boundary -- the backend re-checks every one of these
 * via require_permission() (api/routers/organizations.py), and RLS
 * underneath that. Hiding a button here is a UX nicety, not security;
 * see the backend module's own docstring for the full reasoning on
 * why RLS + backend permission checks are the real boundary.
 *
 * Only covers what this platform's org-management UI actually has
 * today (Organization.tsx) -- tracks/applications/documents/matches
 * permissions exist in the backend matrix but aren't applied to any
 * frontend page yet, because those resources are currently scoped by
 * user_id ownership only, not organization role at all (see the
 * backend session notes on this -- it's a real, still-open product
 * decision, not an oversight).
 */
export type Permission =
  | 'manage_org_settings'
  | 'manage_owners'
  | 'manage_members'
  | 'view_members'
  | 'manage_invites'
  | 'manage_assignments'
  | 'view_assignments'
  | 'manage_tracks'
  | 'view_tracks'
  | 'manage_applications'
  | 'view_applications'
  | 'manage_documents'
  | 'view_documents'
  | 'manage_matches'
  | 'view_matches';

const ALL_PERMISSIONS: Permission[] = [
  'manage_org_settings',
  'manage_owners',
  'manage_members',
  'view_members',
  'manage_invites',
  'manage_assignments',
  'view_assignments',
  'manage_tracks',
  'view_tracks',
  'manage_applications',
  'view_applications',
  'manage_documents',
  'view_documents',
  'manage_matches',
  'view_matches',
];

const ROLE_PERMISSIONS: Record<MemberRole, Permission[]> = {
  owner: ALL_PERMISSIONS,
  admin: ALL_PERMISSIONS.filter((p) => p !== 'manage_owners'),
  manager: [
    'view_members',
    'view_assignments',
    'manage_tracks',
    'view_tracks',
    'manage_applications',
    'view_applications',
    'manage_documents',
    'view_documents',
    'manage_matches',
    'view_matches',
  ],
  staff: [
    'view_members',
    'view_assignments',
    'view_tracks',
    'view_applications',
    'view_documents',
    'view_matches',
  ],
};

export function hasPermission(role: MemberRole | undefined | null, permission: Permission): boolean {
  if (!role) return false;
  return ROLE_PERMISSIONS[role]?.includes(permission) ?? false;
}
