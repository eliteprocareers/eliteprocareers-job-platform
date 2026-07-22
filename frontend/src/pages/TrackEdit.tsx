import { useParams, useNavigate, Link } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { api } from '../lib/api';
import type { CreateTrackRequest, CVTrack } from '../lib/types';
import TrackForm from '../components/TrackForm';

export default function TrackEdit() {
  const { trackId } = useParams<{ trackId: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const { data: track, isLoading, error } = useQuery({
    queryKey: ['track', trackId],
    queryFn: async () => {
      const { data } = await api.get<CVTrack>(`/tracks/${trackId}`);
      return data;
    },
    enabled: !!trackId,
  });

  const mutation = useMutation({
    mutationFn: async (payload: CreateTrackRequest) => {
      const { data } = await api.put<CVTrack>(`/tracks/${trackId}`, payload);
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['tracks'] });
      queryClient.invalidateQueries({ queryKey: ['track', trackId] });
      navigate(`/tracks/${trackId}/matches`);
    },
    onError: () => {
      setErrorMessage('Failed to update track. Check the fields and try again.');
    },
  });

  if (isLoading) return <div className="p-8 text-slate-300">Loading track...</div>;
  if (error || !track) return <div className="p-8 text-red-400">Failed to load track.</div>;

  return (
    <div className="min-h-screen bg-slate-950 p-8">
      <Link to="/tracks" className="text-sm text-slate-400 hover:text-slate-200">← Back to tracks</Link>
      <h1 className="text-2xl font-semibold text-slate-100 mt-4 mb-6">Edit CV Track</h1>
      <TrackForm
        initial={track}
        submitLabel="Save changes"
        isSubmitting={mutation.isPending}
        errorMessage={errorMessage}
        onSubmit={(payload) => {
          setErrorMessage(null);
          mutation.mutate(payload);
        }}
      />
    </div>
  );
}
