import { useNavigate, Link } from 'react-router-dom';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { api } from '../lib/api';
import type { CreateTrackRequest, CVTrack } from '../lib/types';
import TrackForm from '../components/TrackForm';

export default function TrackCreate() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: async (payload: CreateTrackRequest) => {
      const { data } = await api.post<CVTrack>('/tracks', payload);
      return data;
    },
    onSuccess: (track) => {
      queryClient.invalidateQueries({ queryKey: ['tracks'] });
      navigate(`/tracks/${track.id}/matches`);
    },
    onError: () => {
      setErrorMessage('Failed to create track. Check the fields and try again.');
    },
  });

  return (
    <div className="min-h-screen bg-slate-950 p-8">
      <Link to="/tracks" className="text-sm text-slate-400 hover:text-slate-200">← Back to tracks</Link>
      <h1 className="text-2xl font-semibold text-slate-100 mt-4 mb-6">New CV Track</h1>
      <TrackForm
        submitLabel="Create track"
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
