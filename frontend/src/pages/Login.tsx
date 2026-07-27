import { useState } from 'react';
import type { FormEvent } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

export default function Login() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const { login } = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const redirectTo = searchParams.get('redirect') || '/tracks';

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await login(email, password);
      navigate(redirectTo);
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? 'Login failed');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-950">
      <form onSubmit={handleSubmit} className="bg-slate-900 p-8 rounded-lg shadow-lg w-full max-w-sm space-y-4">
        <h1 className="text-xl font-semibold text-slate-100">ElitePro AI Platform</h1>
        <div>
          <label className="block text-sm text-slate-300 mb-1">Email</label>
          <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)}
            className="w-full rounded bg-slate-800 text-slate-100 px-3 py-2 outline-none focus:ring-2 focus:ring-indigo-500" />
        </div>
        <div>
          <label className="block text-sm text-slate-300 mb-1">Password</label>
          <input type="password" required value={password} onChange={(e) => setPassword(e.target.value)}
            className="w-full rounded bg-slate-800 text-slate-100 px-3 py-2 outline-none focus:ring-2 focus:ring-indigo-500" />
        </div>
        {error && <p className="text-sm text-red-400">{error}</p>}
        <button type="submit" disabled={loading}
          className="w-full bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white rounded py-2 font-medium">
          {loading ? 'Signing in...' : 'Sign in'}
        </button>
        <p className="text-sm text-slate-400 text-center">
          Don't have an account?{' '}
          <Link
            to={`/signup${redirectTo !== '/tracks' ? `?redirect=${encodeURIComponent(redirectTo)}` : ''}`}
            className="text-indigo-400 hover:text-indigo-300"
          >
            Sign up
          </Link>
        </p>
      </form>
    </div>
  );
}
