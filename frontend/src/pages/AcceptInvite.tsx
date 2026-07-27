import { Link, useSearchParams, useNavigate } from 'react-router-dom';
import { useMutation, useQuery } from '@tanstack/react-query';
import axios from 'axios';
import { api } from '../lib/api';
import { useAuth } from '../context/AuthContext';
import type { InvitePreview, Organization } from '../lib/types';

export default function AcceptInvite() {
  const [searchParams] = useSearchParams();
  const token = searchParams.get('token');
  const { isAuthenticated } = useAuth();
  const navigate = useNavigate();

  // No auth on this query, deliberately -- this is the "you've been
  // invited to X" page someone sees before they've ever logged in.
  // Backed by get_invite_preview(), which is anon-callable and
  // exposes only what's safe to show whoever's holding the link.
  const previewQuery = useQuery({
    queryKey: ['invite-preview', token],
    queryFn: async () => {
      const { data } = await api.get<InvitePreview>(`/organizations/invites/preview/${token}`);
      return data;
    },
    enabled: !!token,
    retry: false,
  });

  const acceptMutation = useMutation({
    mutationFn: async () => {
      const { data } = await api.post<Organization>('/organizations/invites/accept', { token });
      return data;
    },
    onSuccess: () => navigate('/organization'),
  });

  const returnTo = `/invites/accept?token=${token ?? ''}`;

  if (!token) {
    return <ErrorCard title="Invalid invite link" message="This link is missing an invite token." />;
  }

  if (previewQuery.isLoading) {
    return <div className="min-h-screen flex items-center justify-center bg-slate-950 text-slate-300">Loading invite...</div>;
  }

  if (previewQuery.isError) {
    const status = axios.isAxiosError(previewQuery.error) ? previewQuery.error.response?.status : null;
    return (
      <ErrorCard
        title="Invite not found"
        message={
          status === 404
            ? "This invite doesn't exist, or has already been used."
            : 'Something went wrong loading this invite.'
        }
      />
    );
  }

  const preview = previewQuery.data!;

  if (preview.status !== 'pending') {
    const messages: Record<string, string> = {
      accepted: 'This invite has already been accepted.',
      revoked: 'This invite has been revoked by the organization.',
      expired: 'This invite has expired. Ask the organization to send a new one.',
    };
    return <ErrorCard title={preview.organization_name} message={messages[preview.status] ?? 'This invite is no longer valid.'} />;
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-950">
      <div className="bg-slate-900 p-8 rounded-lg shadow-lg w-full max-w-sm space-y-4 text-center">
        <h1 className="text-xl font-semibold text-slate-100">You've been invited</h1>
        <p className="text-sm text-slate-400">
          Join <span className="text-slate-200">{preview.organization_name}</span> as a{' '}
          <span className="text-slate-200">{preview.role}</span>.
        </p>
        <p className="text-xs text-slate-500">Invited email: {preview.email}</p>

        {isAuthenticated ? (
          <>
            <button
              onClick={() => acceptMutation.mutate()}
              disabled={acceptMutation.isPending}
              className="w-full bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white rounded py-2 font-medium"
            >
              {acceptMutation.isPending ? 'Joining...' : 'Accept invite'}
            </button>
            {acceptMutation.isError && (
              <p className="text-sm text-red-400">
                {axios.isAxiosError(acceptMutation.error)
                  ? acceptMutation.error.response?.data?.detail ?? 'Could not accept invite'
                  : 'Could not accept invite'}
              </p>
            )}
          </>
        ) : (
          <div className="space-y-2">
            <p className="text-xs text-slate-500">
              Log in or create an account with <span className="text-slate-300">{preview.email}</span> to accept.
            </p>
            <Link
              to={`/login?redirect=${encodeURIComponent(returnTo)}`}
              className="block w-full bg-indigo-600 hover:bg-indigo-500 text-white rounded py-2 font-medium"
            >
              Log in to accept
            </Link>
            <Link
              to={`/signup?redirect=${encodeURIComponent(returnTo)}`}
              className="block w-full bg-slate-800 hover:bg-slate-700 text-slate-200 rounded py-2 font-medium"
            >
              Sign up to accept
            </Link>
          </div>
        )}
      </div>
    </div>
  );
}

function ErrorCard({ title, message }: { title: string; message: string }) {
  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-950">
      <div className="bg-slate-900 p-8 rounded-lg shadow-lg w-full max-w-sm space-y-3 text-center">
        <h1 className="text-xl font-semibold text-slate-100">{title}</h1>
        <p className="text-sm text-slate-400">{message}</p>
      </div>
    </div>
  );
}
