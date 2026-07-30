import { useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../lib/api';
import { useAuth } from '../context/AuthContext';
import type { Organization } from '../lib/types';

// Multi-org (migration 0017). Deliberately renders nothing for the
// overwhelmingly common case -- a candidate or single-org
// owner/admin/manager/staff with exactly one membership -- so this
// never adds clutter or a decision nobody asked for. Only appears
// once GET /organizations/mine actually returns more than one org.
export default function OrgSwitcher() {
  const { activeOrganizationId, setActiveOrganizationId } = useAuth();
  const queryClient = useQueryClient();

  const { data: orgs } = useQuery({
    queryKey: ['organizations-mine'],
    queryFn: async () => {
      const { data } = await api.get<Organization[]>('/organizations/mine');
      return data;
    },
  });

  if (!orgs || orgs.length <= 1) return null;

  // Mirrors the backend default exactly (api/dependencies.py: no
  // header -> oldest membership, and /organizations/mine is already
  // returned oldest-first) -- so the dropdown shows the org that's
  // actually active even before the person has ever picked one.
  const currentId = activeOrganizationId ?? orgs[0].id;

  function handleChange(newOrgId: string) {
    setActiveOrganizationId(newOrgId);
    // Every org-scoped query (organization, members, invites,
    // assignments, tracks, ...) needs to reload under the new
    // context -- none of their query keys carry an org id today, so
    // a full invalidation is the simple, correct choice here rather
    // than hand-maintaining a list that will silently go stale as
    // more org-scoped queries get added elsewhere in the app.
    queryClient.invalidateQueries();
  }

  return (
    <select
      value={currentId}
      onChange={(e) => handleChange(e.target.value)}
      className="text-sm bg-slate-800 hover:bg-slate-700 text-slate-200 rounded px-3 py-2 outline-none focus:ring-2 focus:ring-indigo-500"
      title="Switch organization"
    >
      {orgs.map((org) => (
        <option key={org.id} value={org.id}>
          {org.name}
        </option>
      ))}
    </select>
  );
}
