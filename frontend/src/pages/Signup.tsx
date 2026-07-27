import { useState } from 'react';
import type { FormEvent } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import axios from 'axios';
import { useAuth } from '../context/AuthContext';

export default function Signup() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  // Shown instead of the form once signup succeeds but the account
  // isn't usable yet -- this Supabase project's email-confirmation
  // setting isn't known ahead of time, so both outcomes are handled
  // explicitly rather than assuming one (see AuthContext.signup).
  const [confirmationNeeded, setConfirmationNeeded] = useState(false);
  const { signup } = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const redirectTo = searchParams.get('redirect') || '/tracks';

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);

    if (password !== confirmPassword) {
      setError('Passwords do not match.');
      return;
    }
    if (password.length < 8) {
      setError('Password must be at least 8 characters.');
      return;
    }

    setLoading(true);
    try {
      const result = await signup(email, password);
      if (result.requires_confirmation) {
        setConfirmationNeeded(true);
      } else {
        navigate(redirectTo);
      }
    } catch (err: unknown) {
      const detail = axios.isAxiosError(err) ? err.response?.data?.detail : null;
      setError(detail ?? 'Sign-up failed');
    } finally {
      setLoading(false);
    }
  }

  const loginLink = `/login${redirectTo !== '/tracks' ? `?redirect=${encodeURIComponent(redirectTo)}` : ''}`;

  if (confirmationNeeded) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-950">
        <div className="bg-slate-900 p-8 rounded-lg shadow-lg w-full max-w-sm space-y-4 text-center">
          <h1 className="text-xl font-semibold text-slate-100">Check your email</h1>
          <p className="text-sm text-slate-400">
            We sent a confirmation link to <span className="text-slate-200">{email}</span>. Click
            it, then come back and log in.
          </p>
          <Link
            to={loginLink}
            className="inline-block w-full bg-indigo-600 hover:bg-indigo-500 text-white rounded py-2 font-medium"
          >
            Go to login
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-950">
      <form onSubmit={handleSubmit} className="bg-slate-900 p-8 rounded-lg shadow-lg w-full max-w-sm space-y-4">
        <h1 className="text-xl font-semibold text-slate-100">Create your account</h1>
        <div>
          <label className="block text-sm text-slate-300 mb-1">Email</label>
          <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)}
            className="w-full rounded bg-slate-800 text-slate-100 px-3 py-2 outline-none focus:ring-2 focus:ring-indigo-500" />
        </div>
        <div>
          <label className="block text-sm text-slate-300 mb-1">Password</label>
          <input type="password" required minLength={8} value={password} onChange={(e) => setPassword(e.target.value)}
            className="w-full rounded bg-slate-800 text-slate-100 px-3 py-2 outline-none focus:ring-2 focus:ring-indigo-500" />
        </div>
        <div>
          <label className="block text-sm text-slate-300 mb-1">Confirm password</label>
          <input type="password" required minLength={8} value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)}
            className="w-full rounded bg-slate-800 text-slate-100 px-3 py-2 outline-none focus:ring-2 focus:ring-indigo-500" />
        </div>
        {error && <p className="text-sm text-red-400">{error}</p>}
        <button type="submit" disabled={loading}
          className="w-full bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white rounded py-2 font-medium">
          {loading ? 'Creating account...' : 'Sign up'}
        </button>
        <p className="text-sm text-slate-400 text-center">
          Already have an account?{' '}
          <Link to={loginLink} className="text-indigo-400 hover:text-indigo-300">
            Sign in
          </Link>
        </p>
      </form>
    </div>
  );
}
