import { useQuery } from '@tanstack/react-query';
import { Link, useNavigate } from 'react-router-dom';
import { api } from '../lib/api';
import type { CVTrack } from '../lib/types';
import { useAuth } from '../context/AuthContext';

export default function Tracks() {
  const { logout, email } = useAuth();
  const navigate = useNavigate();

  const { data, isLoading, error } = useQuery({
    queryKey: ['tracks'],
    queryFn: async () => {
      const { data } = await api.get<CVTrack[]>('/tracks');
      return data;
    },
  });

  function handleLogout() {
    logout();
    navigate('/login');
  }

  if (isLoading) return <div className="p-8 text-slate-300">Loading tracks...</div>;
  if (error) return <div className="p-8 text-red-400">Failed to load tracks.</div>;

  return (
    <div className="min-h-screen bg-slate-950 p-8">
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-2xl font-semibold text-slate-100">CV Tracks</h1>
        <div className="flex items-center gap-4">
          <span className="text-sm text-slate-400">{email}</span>
          <button onClick={handleLogout} className="text-sm text-slate-400 hover:text-slate-200">Log out</button>
        </div>
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        {data?.map((track) => (
          <Link key={track.id} to={`/tracks/${track.id}/matches`}
            className="block bg-slate-900 hover:bg-slate-800 rounded-lg p-5 transition">
            <h2 className="text-lg font-medium text-slate-100">{track.track_name}</h2>
            <p className="text-sm text-slate-400 mt-1">{track.target_roles.join(', ') || 'No target roles set'}</p>
          </Link>
        ))}
      </div>
    </div>
  );
}
