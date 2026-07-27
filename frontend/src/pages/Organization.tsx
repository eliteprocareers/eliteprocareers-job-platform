import { useState } from 'react';
import type { FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import axios from 'axios';
import { api } from '../lib/api';
import { useAuth } from '../context/AuthContext';
import type {
  CreateInviteRequest,
  InvitableRole,
  Organization as OrganizationType,
  OrganizationInvite,
  OrganizationInviteCreated,
  OrganizationMember,
} from '../lib/types';

const INVITABLE_ROLES: { value: InvitableRole; label: string }[] = [
  { value: 'member', label: 'Member' },
  { value: 'admin', label: 'Admin' },
];

const STATUS_COLORS: Record<string, string> = {
  pending: 'text-amber-400',
  accepted: 'text-emerald-400',
  revoked: 'text-slate-500',
  expired: 'text-slate-500',
};

function shortId(id: string) {
  return id.slice(0, 8);
}

export default function Organization() {
  const { email, logout, userId } = useAuth();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [inviteEmail, setInviteEmail] = useState('');
  const [inviteRole, setInviteRole] = useState<InvitableRole>('member');
  const [inviteError, setInviteError] = useState<string | null>(null);
  // The invite token is only ever returned once, at creation time --
  // keep it around locally to show the shareable link, since a
  // subsequent GET /organizations/invites never includes it again
  // (see backend comment on OrganizationInviteCreated).
  const [lastCreatedInvite, setLastCreatedInvite] = useState<OrganizationInviteCreated | null>(null);

  const orgQuery = useQuery({
    queryKey: ['organization'],
    queryFn: async () => {
      const { data } = await api.get<OrganizationType>('/organizations/me');
      return data;
    },
    retry: false,
  });

  const membersQuery = useQuery({
    queryKey: ['organization-members'],
    queryFn: async () => {
      const { data } = await api.get<OrganizationMember[]>('/organizations/members');
      return data;
    },
    enabled: !!orgQuery.data,
  });

  const currentMember = membersQuery.data?.find((m) => m.user_id === userId);
  const isAdmin = currentMember?.role === 'owner' || currentMember?.role === 'admin';

  // Only admins/owners can list invites at all (RLS-enforced on the
  // backend, not just this check) -- don't even attempt the query
  // otherwise, so a member doesn't see a confusing 403 in the network
  // tab for a request they were never going to be allowed to make.
  const invitesQuery = useQuery({
    queryKey: ['organization-invites'],
    queryFn: async () => {
      const { data } = await api.get<OrganizationInvite[]>('/organizations/invites');
      return data;
    },
    enabled: !!orgQuery.data && isAdmin,
  });

  const createInviteMutation = useMutation({
    mutationFn: async (payload: CreateInviteRequest) => {
      const { data } = await api.post<OrganizationInviteCreated>('/organizations/invites', payload);
      return data;
    },
    onSuccess: (data) => {
      setLastCreatedInvite(data);
      setInviteEmail('');
      setInviteRole('member');
      queryClient.invalidateQueries({ queryKey: ['organization-invites'] });
    },
  });

  const revokeInviteMutation = useMutation({
    mutationFn: async (inviteId: string) => {
      await api.delete(`/organizations/invites/${inviteId}`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['organization-invites'] });
    },
  });

  function handleInviteSubmit(e: FormEvent) {
    e.preventDefault();
    setInviteError(null);
    setLastCreatedInvite(null);
    createInviteMutation.mutate(
      { email: inviteEmail, role: inviteRole },
      {
        onError: (err) => {
          const detail = axios.isAxiosError(err) ? err.response?.data?.detail : null;
          setInviteError(detail ?? 'Could not create invite');
        },
      }
    );
  }

  function handleLogout() {
    logout();
    navigate('/login');
  }

  const inviteLink = lastCreatedInvite
    ? `${window.location.origin}/invites/accept?token=${lastCreatedInvite.token}`
    : null;

  if (orgQuery.isLoading) {
    return <div className="p-8 text-slate-300">Loading organization...</div>;
  }

  // 404 from GET /organizations/me means "no organization yet" -- not
  // an error state, just the signal to show the create flow, same
  // convention as a missing profile pointing at the CV upload flow.
  if (orgQuery.isError) {
    const status = axios.isAxiosError(orgQuery.error) ? orgQuery.error.response?.status : null;
    if (status === 404) {
      return (
        <div className="min-h-screen flex items-center justify-center bg-slate-950">
          <div className="bg-slate-900 p-8 rounded-lg shadow-lg w-full max-w-sm space-y-4 text-center">
            <h1 className="text-xl font-semibold text-slate-100">No organization yet</h1>
            <p className="text-sm text-slate-400">Create one to start inviting people.</p>
            <Link
              to="/organizations/new"
              className="inline-block w-full bg-indigo-600 hover:bg-indigo-500 text-white rounded py-2 font-medium"
            >
              Create organization
            </Link>
          </div>
        </div>
      );
    }
    return <div className="p-8 text-red-400">Failed to load organization.</div>;
  }

  const org = orgQuery.data!;

  return (
    <div className="min-h-screen bg-slate-950 p-8">
      <div className="flex justify-between items-center mb-6">
        <div>
          <h1 className="text-2xl font-semibold text-slate-100">{org.name}</h1>
          <p className="text-sm text-slate-400 mt-1 capitalize">{org.org_type.replace(/_/g, ' ')}</p>
        </div>
        <div className="flex items-center gap-4">
          <span className="text-sm text-slate-400">{email}</span>
          <Link to="/tracks" className="text-sm bg-slate-800 hover:bg-slate-700 text-slate-200 rounded px-3 py-2">
            Tracks
          </Link>
          <button onClick={handleLogout} className="text-sm text-slate-400 hover:text-slate-200">
            Log out
          </button>
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Members */}
        <div className="bg-slate-900 rounded-lg p-5">
          <h2 className="text-lg font-medium text-slate-100 mb-4">Members</h2>
          {membersQuery.isLoading && <p className="text-sm text-slate-400">Loading members...</p>}
          {membersQuery.isError && <p className="text-sm text-red-400">Failed to load members.</p>}
          <ul className="space-y-2">
            {membersQuery.data?.map((m) => (
              <li key={m.id} className="flex justify-between items-center text-sm bg-slate-800 rounded px-3 py-2">
                <span className="text-slate-200">
                  {shortId(m.user_id)}
                  {m.user_id === userId && <span className="text-slate-500"> (you)</span>}
                </span>
                <span className="text-slate-400 capitalize">{m.role}</span>
              </li>
            ))}
          </ul>
          <p className="text-xs text-slate-500 mt-3">
            Showing member IDs -- displaying member emails isn't wired up yet.
          </p>
        </div>

        {/* Invites -- admins/owners only */}
        {isAdmin && (
          <div className="bg-slate-900 rounded-lg p-5">
            <h2 className="text-lg font-medium text-slate-100 mb-4">Invite someone</h2>
            <form onSubmit={handleInviteSubmit} className="space-y-3">
              <div className="flex gap-2">
                <input
                  type="email"
                  required
                  placeholder="email@example.com"
                  value={inviteEmail}
                  onChange={(e) => setInviteEmail(e.target.value)}
                  className="flex-1 rounded bg-slate-800 text-slate-100 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-indigo-500"
                />
                <select
                  value={inviteRole}
                  onChange={(e) => setInviteRole(e.target.value as InvitableRole)}
                  className="rounded bg-slate-800 text-slate-100 px-2 py-2 text-sm outline-none focus:ring-2 focus:ring-indigo-500"
                >
                  {INVITABLE_ROLES.map((r) => (
                    <option key={r.value} value={r.value}>
                      {r.label}
                    </option>
                  ))}
                </select>
                <button
                  type="submit"
                  disabled={createInviteMutation.isPending}
                  className="bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white text-sm rounded px-4 py-2 font-medium"
                >
                  Invite
                </button>
              </div>
              {inviteError && <p className="text-sm text-red-400">{inviteError}</p>}
            </form>

            {inviteLink && (
              <div className="mt-3 bg-slate-800 rounded p-3">
                <p className="text-xs text-slate-400 mb-1">
                  Share this link -- it won't be shown again. There's no email-sending set up yet.
                </p>
                <input
                  readOnly
                  value={inviteLink}
                  onFocus={(e) => e.target.select()}
                  className="w-full bg-slate-900 text-slate-200 text-xs rounded px-2 py-1.5 outline-none"
                />
              </div>
            )}

            <h3 className="text-sm font-medium text-slate-300 mt-5 mb-2">Pending &amp; past invites</h3>
            {invitesQuery.isLoading && <p className="text-sm text-slate-400">Loading invites...</p>}
            {invitesQuery.isError && <p className="text-sm text-red-400">Failed to load invites.</p>}
            <ul className="space-y-2">
              {invitesQuery.data?.map((invite) => (
                <li key={invite.id} className="flex justify-between items-center text-sm bg-slate-800 rounded px-3 py-2">
                  <div>
                    <span className="text-slate-200">{invite.email}</span>
                    <span className="text-slate-500"> · {invite.role}</span>
                    <span className={`ml-2 ${STATUS_COLORS[invite.status] ?? 'text-slate-400'}`}>
                      {invite.status}
                    </span>
                  </div>
                  {invite.status === 'pending' && (
                    <button
                      onClick={() => revokeInviteMutation.mutate(invite.id)}
                      disabled={revokeInviteMutation.isPending}
                      className="text-xs text-red-400 hover:text-red-300 disabled:opacity-50"
                    >
                      Revoke
                    </button>
                  )}
                </li>
              ))}
              {invitesQuery.data?.length === 0 && (
                <li className="text-sm text-slate-500">No invites yet.</li>
              )}
            </ul>
          </div>
        )}
      </div>
    </div>
  );
}
