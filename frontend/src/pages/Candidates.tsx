import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { api } from '../lib/api';
import { useAuth } from '../context/AuthContext';
import { hasPermission } from '../lib/permissions';
import type {
  CandidateAssignment,
  CVTrack,
  Organization as OrganizationType,
  OrganizationMember,
} from '../lib/types';

/**
 * The frontend surface for the mechanism/payoff gap flagged across
 * v33/v34's handovers: migration 0015 + the part-10 API fix made it
 * possible for a manager/staff to see an assigned candidate's tracks,
 * but nothing called GET /tracks?candidate_user_id=X or linked into
 * the existing track pages for anyone but the caller's own tracks.
 * This page is that missing link.
 *
 * GET /organizations/assignments is already RLS/permission-scoped
 * correctly (view_assignments -- all four roles have it): owners/
 * admins get every assignment in the org, managers/staff get only
 * their own caseload. This page does no additional filtering on top
 * of that -- same pattern Organization.tsx already uses for the same
 * endpoint.
 */
export default function Candidates() {
  const { email, logout, userId } = useAuth();
  const navigate = useNavigate();
  const [expandedCandidateId, setExpandedCandidateId] = useState<string | null>(null);

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
  const canManageAssignments = hasPermission(currentMember?.role, 'manage_assignments');

  const assignmentsQuery = useQuery({
    queryKey: ['organization-assignments'],
    queryFn: async () => {
      const { data } = await api.get<CandidateAssignment[]>('/organizations/assignments');
      return data;
    },
    enabled: !!orgQuery.data,
  });

  // Candidates are org members too (every candidate_profiles row has
  // been in organization_members since migration 0007's backfill), so
  // the members list already fetched above is enough to resolve an
  // assignment's candidate_user_id to a real email -- no separate
  // candidate-lookup endpoint needed.
  function memberFor(memberUserId: string): OrganizationMember | undefined {
    return membersQuery.data?.find((m) => m.user_id === memberUserId);
  }

  const tracksQuery = useQuery({
    queryKey: ['candidate-tracks', expandedCandidateId],
    queryFn: async () => {
      const { data } = await api.get<CVTrack[]>('/tracks', {
        params: { candidate_user_id: expandedCandidateId },
      });
      return data;
    },
    enabled: !!expandedCandidateId,
  });

  function handleLogout() {
    logout();
    navigate('/login');
  }

  function toggleExpanded(candidateUserId: string) {
    setExpandedCandidateId((current) => (current === candidateUserId ? null : candidateUserId));
  }

  const isLoading = orgQuery.isLoading || (!!orgQuery.data && (membersQuery.isLoading || assignmentsQuery.isLoading));

  return (
    <div className="min-h-screen bg-slate-950 p-8">
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-2xl font-semibold text-slate-100">
          {canManageAssignments ? 'Candidates' : 'My Assigned Candidates'}
        </h1>
        <div className="flex items-center gap-4">
          <span className="text-sm text-slate-400">{email}</span>
          <Link to="/tracks" className="text-sm bg-slate-800 hover:bg-slate-700 text-slate-200 rounded px-3 py-2">
            My Tracks
          </Link>
          <Link to="/profile" className="text-sm bg-slate-800 hover:bg-slate-700 text-slate-200 rounded px-3 py-2">
            Profile
          </Link>
          <Link to="/organization" className="text-sm bg-slate-800 hover:bg-slate-700 text-slate-200 rounded px-3 py-2">
            Organization
          </Link>
          <button onClick={handleLogout} className="text-sm text-slate-400 hover:text-slate-200">Log out</button>
        </div>
      </div>

      {orgQuery.isError && (
        <p className="text-sm text-slate-400">
          You're not part of an organization, so there are no assigned candidates to show.
        </p>
      )}

      {isLoading && <p className="text-slate-300">Loading candidates...</p>}
      {assignmentsQuery.isError && <p className="text-red-400">Failed to load assignments.</p>}

      {orgQuery.data && assignmentsQuery.data?.length === 0 && (
        <p className="text-sm text-slate-500">
          {canManageAssignments
            ? 'No candidate assignments exist yet -- create one from the Organization page.'
            : "No candidates are assigned to you yet. Ask an owner or admin to assign one from the Organization page."}
        </p>
      )}

      <div className="space-y-3">
        {assignmentsQuery.data?.map((a) => {
          const candidate = memberFor(a.candidate_user_id);
          const assignedTo = memberFor(a.assigned_to);
          const isExpanded = expandedCandidateId === a.candidate_user_id;

          return (
            <div key={a.id} className="bg-slate-900 rounded-lg p-5">
              <div className="flex justify-between items-center">
                <div>
                  <h2 className="text-lg font-medium text-slate-100">
                    {candidate?.email ?? `Candidate ${a.candidate_user_id.slice(0, 8)}`}
                  </h2>
                  {canManageAssignments && (
                    <p className="text-sm text-slate-400 mt-1">
                      Assigned to {assignedTo?.email ?? a.assigned_to.slice(0, 8)}
                      {assignedTo ? ` (${assignedTo.role})` : ''}
                    </p>
                  )}
                </div>
                <button
                  onClick={() => toggleExpanded(a.candidate_user_id)}
                  className="text-sm bg-slate-800 hover:bg-slate-700 text-slate-200 rounded px-3 py-2"
                >
                  {isExpanded ? 'Hide tracks' : 'View tracks'}
                </button>
              </div>

              {isExpanded && (
                <div className="mt-4 border-t border-slate-800 pt-4">
                  {tracksQuery.isLoading && (
                    <p className="text-sm text-slate-400">Loading tracks...</p>
                  )}
                  {tracksQuery.isError && (
                    <p className="text-sm text-red-400">Failed to load this candidate's tracks.</p>
                  )}
                  {tracksQuery.data?.length === 0 && (
                    <p className="text-sm text-slate-500">This candidate has no CV tracks yet.</p>
                  )}
                  <div className="grid gap-3 sm:grid-cols-2">
                    {tracksQuery.data?.map((track) => (
                      <Link
                        key={track.id}
                        to={`/tracks/${track.id}/matches`}
                        state={{ backTo: '/candidates', backLabel: 'Back to candidates' }}
                        className="block bg-slate-800 hover:bg-slate-700 rounded-lg p-4 transition"
                      >
                        <h3 className="text-slate-100 font-medium">{track.track_name}</h3>
                        <p className="text-sm text-slate-400 mt-1">
                          {track.target_roles.join(', ') || 'No target roles set'}
                        </p>
                      </Link>
                    ))}
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
