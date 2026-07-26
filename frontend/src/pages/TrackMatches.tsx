import { useParams, Link } from 'react-router-dom';
import { useQuery, useMutation } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { api } from '../lib/api';
import type { MatchTriggerResponse, MatchWithJob } from '../lib/types';

const POLL_INTERVAL_MS = 10000;
const POLL_DURATION_MS = 5 * 60 * 1000;

export default function TrackMatches() {
  const { trackId } = useParams<{ trackId: string }>();
  const [minScore, setMinScore] = useState<number>(0);
  const [isPolling, setIsPolling] = useState(false);
  const [triggerMessage, setTriggerMessage] = useState<string | null>(null);

  const { data, isLoading, error, refetch, dataUpdatedAt } = useQuery({
    queryKey: ['matches', trackId, minScore],
    queryFn: async () => {
      const { data } = await api.get<MatchWithJob[]>(`/tracks/${trackId}/matches`, {
        params: { limit: 50, ...(minScore > 0 ? { min_score: minScore } : {}) },
      });
      return data;
    },
    enabled: !!trackId,
    refetchInterval: isPolling ? POLL_INTERVAL_MS : false,
  });

  useEffect(() => {
    if (!isPolling) return;
    const timeout = setTimeout(() => setIsPolling(false), POLL_DURATION_MS);
    return () => clearTimeout(timeout);
  }, [isPolling]);

  const triggerMutation = useMutation({
    mutationFn: async () => {
      const { data } = await api.post<MatchTriggerResponse>(`/tracks/${trackId}/match`);
      return data;
    },
    onSuccess: (res) => {
      setTriggerMessage(res.message);
      setIsPolling(true);
    },
    onError: () => {
      setTriggerMessage('Failed to start matching run.');
    },
  });

  return (
    <div className="min-h-screen bg-slate-950 p-8">
      <Link to="/tracks" className="text-sm text-slate-400 hover:text-slate-200">← Back to tracks</Link>
      <div className="flex justify-between items-center mt-4 mb-2">
        <h1 className="text-2xl font-semibold text-slate-100">Matches</h1>
        <div className="flex items-center gap-3">
          <Link
            to={`/tracks/${trackId}/applications`}
            className="text-sm bg-slate-800 hover:bg-slate-700 text-slate-200 rounded px-3 py-2"
          >
            Applications
          </Link>
          <label className="text-sm text-slate-400">
            Min score:{' '}
            <input type="number" min={0} max={1} step={0.05} value={minScore}
              onChange={(e) => setMinScore(Number(e.target.value))}
              className="ml-2 w-20 bg-slate-800 text-slate-100 rounded px-2 py-1" />
          </label>
          <button onClick={() => refetch()}
            className="text-sm bg-slate-800 hover:bg-slate-700 text-slate-200 rounded px-3 py-2">
            Refresh
          </button>
          <button onClick={() => triggerMutation.mutate()} disabled={triggerMutation.isPending}
            className="text-sm bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white rounded px-3 py-2 font-medium">
            {triggerMutation.isPending ? 'Starting...' : 'Run matching'}
          </button>
        </div>
      </div>

      {triggerMessage && (
        <p className="text-sm text-indigo-300 mb-4">
          {triggerMessage}
          {isPolling && ' Checking for new results every 10s...'}
        </p>
      )}
      {dataUpdatedAt > 0 && (
        <p className="text-xs text-slate-500 mb-4">Last loaded: {new Date(dataUpdatedAt).toLocaleTimeString()}</p>
      )}

      {isLoading && <p className="text-slate-300">Loading matches...</p>}
      {error && <p className="text-red-400">Failed to load matches.</p>}

      <div className="space-y-3">
        {data?.map((m) => (
          <div key={m.match_id} className="bg-slate-900 rounded-lg p-4 flex justify-between items-start">
            <div>
              <h2 className="text-slate-100 font-medium">
                {m.job_url ? (
                  <a href={m.job_url} target="_blank" rel="noreferrer" className="hover:underline">{m.job_title}</a>
                ) : m.job_title}
              </h2>
              <p className="text-sm text-slate-400">{m.job_company}{m.job_location ? ` · ${m.job_location}` : ''}</p>
              {m.ai_rationale && <p className="text-sm text-slate-500 mt-2 max-w-xl">{m.ai_rationale}</p>}
            </div>
            <div className="flex flex-col items-end gap-2 shrink-0 ml-4">
              <span className="text-lg font-semibold text-indigo-400">
                {m.match_score !== null ? m.match_score.toFixed(4) : '—'}
              </span>
              <Link
                to={`/tracks/${trackId}/jobs/${m.job_id}/documents`}
                state={{
                  job: {
                    job_title: m.job_title,
                    job_company: m.job_company,
                    job_url: m.job_url,
                  },
                }}
                className="text-xs bg-slate-800 hover:bg-slate-700 text-slate-200 rounded px-3 py-1.5"
              >
                Generate documents
              </Link>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
