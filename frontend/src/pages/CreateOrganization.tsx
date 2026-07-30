import { useState } from 'react';
import type { FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import axios from 'axios';
import { api } from '../lib/api';
import { useAuth } from '../context/AuthContext';
import type { Organization, OrgType } from '../lib/types';

const ORG_TYPES: { value: OrgType; label: string }[] = [
  { value: 'individual', label: 'Individual' },
  { value: 'agency', label: 'Agency' },
  { value: 'staffing_firm', label: 'Staffing firm' },
  { value: 'company', label: 'Company' },
  { value: 'university', label: 'University' },
  { value: 'career_coaching_firm', label: 'Career coaching firm' },
  { value: 'enterprise', label: 'Enterprise' },
];

export default function CreateOrganization() {
  const [name, setName] = useState('');
  const [orgType, setOrgType] = useState<OrgType>('individual');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();
  const { setActiveOrganizationId } = useAuth();
  const queryClient = useQueryClient();

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const { data } = await api.post<Organization>('/organizations', { name, org_type: orgType });
      // Multi-org (migration 0017): a caller who already belongs to
      // an org can create another. Without this, navigating to
      // /organization right after would show whichever org the
      // backend defaults to (the caller's oldest membership) --
      // confusingly not the one they just created. Explicitly switch
      // the active org context to the new one and refresh the org
      // list so the switcher picks it up immediately.
      setActiveOrganizationId(data.id);
      queryClient.invalidateQueries({ queryKey: ['organizations-mine'] });
      navigate('/organization');
    } catch (err: unknown) {
      const detail = axios.isAxiosError(err) ? err.response?.data?.detail : null;
      setError(detail ?? 'Could not create organization');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-950">
      <form onSubmit={handleSubmit} className="bg-slate-900 p-8 rounded-lg shadow-lg w-full max-w-sm space-y-4">
        <div>
          <h1 className="text-xl font-semibold text-slate-100">Create an organization</h1>
          <p className="text-sm text-slate-400 mt-1">
            You'll be the owner. You can invite others once it's set up. If you already belong to
            another organization, this creates an additional one -- you can switch between them
            afterward.
          </p>
        </div>
        <div>
          <label className="block text-sm text-slate-300 mb-1">Organization name</label>
          <input
            type="text"
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Acme Recruiting"
            className="w-full rounded bg-slate-800 text-slate-100 px-3 py-2 outline-none focus:ring-2 focus:ring-indigo-500"
          />
        </div>
        <div>
          <label className="block text-sm text-slate-300 mb-1">Organization type</label>
          <select
            value={orgType}
            onChange={(e) => setOrgType(e.target.value as OrgType)}
            className="w-full rounded bg-slate-800 text-slate-100 px-3 py-2 outline-none focus:ring-2 focus:ring-indigo-500"
          >
            {ORG_TYPES.map((t) => (
              <option key={t.value} value={t.value}>
                {t.label}
              </option>
            ))}
          </select>
        </div>
        {error && <p className="text-sm text-red-400">{error}</p>}
        <button
          type="submit"
          disabled={loading}
          className="w-full bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white rounded py-2 font-medium"
        >
          {loading ? 'Creating...' : 'Create organization'}
        </button>
      </form>
    </div>
  );
}
