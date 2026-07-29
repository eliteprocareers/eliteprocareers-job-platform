import { useParams, useLocation, Link } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { api } from '../lib/api';
import type { ApplicationStatus, ApplicationWithJob } from '../lib/types';
import ApplicationStatusBadge from '../components/ApplicationStatusBadge';
import { APPLICATION_STATUS_LABELS, APPLICATION_STATUS_ORDER } from '../lib/applicationStatus';

function formatDate(iso: string | null): string {
  if (!iso) return '—';
  return new Date(iso).toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  });
}

export default function TrackApplications() {
  const { trackId } = useParams<{ trackId: string }>();
  const location = useLocation();
  const queryClient = useQueryClient();
  const [notesDraft, setNotesDraft] = useState<Record<string, string>>({});
  const [rowError, setRowError] = useState<Record<string, string>>({});

  const queryKey = ['applications', trackId];
  const { data, isLoading, error } = useQuery({
    queryKey,
    queryFn: async () => {
      const { data } = await api.get<ApplicationWithJob[]>(`/tracks/${trackId}/applications`);
      return data;
    },
    enabled: !!trackId,
  });

  const statusMutation = useMutation({
    mutationFn: async ({
      applicationId,
      status,
      notes,
    }: {
      applicationId: string;
      status: ApplicationStatus;
      notes?: string | null;
    }) => {
      const { data } = await api.patch<ApplicationWithJob>(
        `/tracks/${trackId}/applications/${applicationId}`,
        { status, notes }
      );
      return data;
    },
    onMutate: ({ applicationId }) => {
      setRowError((prev) => ({ ...prev, [applicationId]: '' }));
    },
    onSuccess: (updated, { applicationId }) => {
      queryClient.setQueryData<ApplicationWithJob[]>(queryKey, (prev) =>
        prev?.map((a) =>
          a.id === applicationId
            ? { ...a, status: updated.status, applied_at: updated.applied_at, notes: updated.notes }
            : a
        )
      );
    },
    onError: (_err, { applicationId }) => {
      setRowError((prev) => ({ ...prev, [applicationId]: 'Update failed. Try again.' }));
    },
  });

  return (
    <div className="min-h-screen bg-slate-950 p-8">
      <Link
        to={`/tracks/${trackId}/matches`}
        state={location.state}
        className="text-sm text-slate-400 hover:text-slate-200"
      >
        ← Back to matches
      </Link>

      <div className="mt-4 mb-6">
        <h1 className="text-2xl font-semibold text-slate-100">Applications</h1>
        <p className="text-sm text-slate-400 mt-1">
          Track the real-world status of applications you've submitted. Creating and generating
          documents doesn't submit anything on your behalf — this is a manual status tracker only.
        </p>
      </div>

      {isLoading && <p className="text-slate-300">Loading applications...</p>}
      {error && <p className="text-red-400">Failed to load applications.</p>}
      {data && data.length === 0 && (
        <p className="text-sm text-slate-500">
          No applications yet. Open a job from your matches list and create one from there.
        </p>
      )}

      <div className="space-y-3">
        {data?.map((a) => {
          const notes = notesDraft[a.id] ?? a.notes ?? '';
          const notesChanged = notes !== (a.notes ?? '');
          return (
            <div key={a.id} className="bg-slate-900 rounded-lg p-4">
              <div className="flex justify-between items-start gap-4">
                <div className="min-w-0">
                  <h2 className="text-slate-100 font-medium truncate">
                    {a.job_url ? (
                      <a href={a.job_url} target="_blank" rel="noreferrer" className="hover:underline">
                        {a.job_title}
                      </a>
                    ) : (
                      a.job_title
                    )}
                  </h2>
                  <p className="text-sm text-slate-400">{a.job_company}</p>
                  <p className="text-xs text-slate-500 mt-1">
                    Created {formatDate(a.created_at)}
                    {a.applied_at ? ` · Applied ${formatDate(a.applied_at)}` : ''}
                  </p>
                </div>
                <div className="flex flex-col items-end gap-2 shrink-0">
                  <ApplicationStatusBadge status={a.status} />
                  <select
                    value={a.status}
                    disabled={statusMutation.isPending}
                    onChange={(e) =>
                      statusMutation.mutate({
                        applicationId: a.id,
                        status: e.target.value as ApplicationStatus,
                        notes: a.notes,
                      })
                    }
                    className="text-xs bg-slate-800 text-slate-200 rounded px-2 py-1"
                  >
                    {APPLICATION_STATUS_ORDER.map((s) => (
                      <option key={s} value={s}>
                        {APPLICATION_STATUS_LABELS[s]}
                      </option>
                    ))}
                  </select>
                  <Link
                    to={`/tracks/${trackId}/jobs/${a.job_id}/documents`}
                    state={{
                      job: { job_title: a.job_title, job_company: a.job_company, job_url: a.job_url },
                    }}
                    className="text-xs text-indigo-400 hover:text-indigo-300"
                  >
                    View documents
                  </Link>
                </div>
              </div>

              <div className="mt-3 flex gap-2 items-start">
                <textarea
                  value={notes}
                  onChange={(e) => setNotesDraft((prev) => ({ ...prev, [a.id]: e.target.value }))}
                  placeholder="Notes (optional)"
                  rows={1}
                  className="flex-1 bg-slate-800 text-slate-100 rounded px-3 py-1.5 text-sm placeholder:text-slate-500"
                />
                <button
                  onClick={() =>
                    statusMutation.mutate({ applicationId: a.id, status: a.status, notes })
                  }
                  disabled={!notesChanged || statusMutation.isPending}
                  className="text-xs bg-slate-800 hover:bg-slate-700 disabled:opacity-40 text-slate-200 rounded px-3 py-1.5"
                >
                  Save notes
                </button>
              </div>
              {rowError[a.id] && <p className="text-red-400 text-xs mt-2">{rowError[a.id]}</p>}
            </div>
          );
        })}
      </div>
    </div>
  );
}
