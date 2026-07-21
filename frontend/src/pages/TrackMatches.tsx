import { useParams, Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { api } from '../lib/api';
import type { MatchWithJob } from '../lib/types';

export default function TrackMatches() {
  const { trackId } = useParams<{ trackId: string }>();
  const [minScore, setMinScore] = useState<number>(0);

  const { data, isLoading, error } = useQuery({
    queryKey: ['matches', trackId, minScore],
    queryFn: async () => {
      const { data } = await api.get<MatchWithJob[]>(`/tracks/${trackId}/matches`, {
        params: { limit: 50, ...(minScore > 0 ? { min_score: minScore } : {}) },
      });
      return data;
    },
    enabled: !!trackId,
  });

  return (
    <div className="min-h-screen bg-slate-950 p-8">
      <Link to="/tracks" className="text-sm text-slate-400 hover:text-slate-200">← Back to tracks</Link>
      <div className="flex justify-between items-center mt-4 mb-6">
        <h1 className="text-2xl font-semibold text-slate-100">Matches</h1>
        <label className="text-sm text-slate-400">
          Min score:{' '}
          <input type="number" min={0} max={1} step={0.05} value={minScore}
            onChange={(e) => setMinScore(Number(e.target.value))}
            className="ml-2 w-20 bg-slate-800 text-slate-100 rounded px-2 py-1" />
        </label>
      </div>

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
            <span className="text-lg font-semibold text-indigo-400 shrink-0 ml-4">
              {m.match_score !== null ? m.match_score.toFixed(4) : '—'}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
