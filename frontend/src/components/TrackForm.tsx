import { useState } from 'react';
import type { FormEvent } from 'react';
import type { CreateTrackRequest, CVTrack } from '../lib/types';

interface TrackFormProps {
  initial?: CVTrack;
  submitLabel: string;
  onSubmit: (payload: CreateTrackRequest) => void;
  isSubmitting: boolean;
  errorMessage?: string | null;
}

function toCsv(arr: string[] | undefined): string {
  return (arr ?? []).join(', ');
}

function fromCsv(value: string): string[] {
  return value
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean);
}

export default function TrackForm({ initial, submitLabel, onSubmit, isSubmitting, errorMessage }: TrackFormProps) {
  const [trackName, setTrackName] = useState(initial?.track_name ?? '');
  const [targetRoles, setTargetRoles] = useState(toCsv(initial?.target_roles));
  const [preferredLocations, setPreferredLocations] = useState(toCsv(initial?.preferred_locations));
  const [preferredCountries, setPreferredCountries] = useState(toCsv(initial?.preferred_countries));
  const [employmentTypes, setEmploymentTypes] = useState(toCsv(initial?.employment_types));
  const [seniorityLevels, setSeniorityLevels] = useState(toCsv(initial?.seniority_levels));
  const [industries, setIndustries] = useState(toCsv(initial?.industries));
  const [workMode, setWorkMode] = useState(toCsv(initial?.work_mode));
  const [willingToRelocate, setWillingToRelocate] = useState(initial?.willing_to_relocate ?? false);
  const [visaSponsorship, setVisaSponsorship] = useState<'' | 'true' | 'false'>(
    initial?.visa_sponsorship_required === true
      ? 'true'
      : initial?.visa_sponsorship_required === false
      ? 'false'
      : ''
  );
  const [workAuthStatus, setWorkAuthStatus] = useState(initial?.work_authorization_status ?? '');
  const [salaryMin, setSalaryMin] = useState(initial?.salary_expectation_min?.toString() ?? '');
  const [salaryMax, setSalaryMax] = useState(initial?.salary_expectation_max?.toString() ?? '');
  const [salaryCurrency, setSalaryCurrency] = useState(initial?.salary_currency ?? '');

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    const payload: CreateTrackRequest = {
      track_name: trackName.trim(),
      target_roles: fromCsv(targetRoles),
      preferred_locations: fromCsv(preferredLocations),
      preferred_countries: fromCsv(preferredCountries),
      employment_types: fromCsv(employmentTypes),
      seniority_levels: fromCsv(seniorityLevels),
      industries: fromCsv(industries),
      work_mode: fromCsv(workMode),
      willing_to_relocate: willingToRelocate,
      visa_sponsorship_required: visaSponsorship === '' ? null : visaSponsorship === 'true',
      work_authorization_status: workAuthStatus.trim() === '' ? null : workAuthStatus.trim(),
      salary_expectation_min: salaryMin.trim() === '' ? null : Number(salaryMin),
      salary_expectation_max: salaryMax.trim() === '' ? null : Number(salaryMax),
      salary_currency: salaryCurrency.trim() === '' ? null : salaryCurrency.trim(),
    };
    onSubmit(payload);
  }

  const inputClass = 'w-full bg-slate-800 text-slate-100 rounded px-3 py-2 mt-1';
  const labelClass = 'text-sm text-slate-400';

  return (
    <form onSubmit={handleSubmit} className="space-y-5 max-w-2xl">
      <div>
        <label className={labelClass}>Track name *</label>
        <input required value={trackName} onChange={(e) => setTrackName(e.target.value)} className={inputClass} />
      </div>

      <div>
        <label className={labelClass}>Target roles (comma-separated)</label>
        <input value={targetRoles} onChange={(e) => setTargetRoles(e.target.value)} className={inputClass}
          placeholder="Product Manager, Supply Chain Analyst" />
      </div>

      <div className="grid sm:grid-cols-2 gap-4">
        <div>
          <label className={labelClass}>Preferred locations (comma-separated)</label>
          <input value={preferredLocations} onChange={(e) => setPreferredLocations(e.target.value)} className={inputClass}
            placeholder="Nairobi, Remote" />
        </div>
        <div>
          <label className={labelClass}>Preferred countries (comma-separated)</label>
          <input value={preferredCountries} onChange={(e) => setPreferredCountries(e.target.value)} className={inputClass}
            placeholder="Kenya, UAE" />
        </div>
      </div>

      <div className="grid sm:grid-cols-2 gap-4">
        <div>
          <label className={labelClass}>Employment types (comma-separated)</label>
          <input value={employmentTypes} onChange={(e) => setEmploymentTypes(e.target.value)} className={inputClass}
            placeholder="full_time, contract" />
        </div>
        <div>
          <label className={labelClass}>Seniority levels (comma-separated)</label>
          <input value={seniorityLevels} onChange={(e) => setSeniorityLevels(e.target.value)} className={inputClass}
            placeholder="mid, senior" />
        </div>
      </div>

      <div className="grid sm:grid-cols-2 gap-4">
        <div>
          <label className={labelClass}>Industries (comma-separated)</label>
          <input value={industries} onChange={(e) => setIndustries(e.target.value)} className={inputClass}
            placeholder="SaaS, Logistics" />
        </div>
        <div>
          <label className={labelClass}>Work mode (comma-separated)</label>
          <input value={workMode} onChange={(e) => setWorkMode(e.target.value)} className={inputClass}
            placeholder="remote, hybrid" />
        </div>
      </div>

      <div className="flex items-center gap-3">
        <input type="checkbox" checked={willingToRelocate} onChange={(e) => setWillingToRelocate(e.target.checked)}
          id="relocate" className="h-4 w-4" />
        <label htmlFor="relocate" className="text-sm text-slate-300">Willing to relocate</label>
      </div>

      <div>
        <label className={labelClass}>Visa sponsorship required</label>
        <select value={visaSponsorship} onChange={(e) => setVisaSponsorship(e.target.value as '' | 'true' | 'false')}
          className={inputClass}>
          <option value="">Not specified</option>
          <option value="true">Yes</option>
          <option value="false">No</option>
        </select>
      </div>

      <div>
        <label className={labelClass}>Work authorization status</label>
        <input value={workAuthStatus} onChange={(e) => setWorkAuthStatus(e.target.value)} className={inputClass}
          placeholder="e.g. Kenyan citizen, no visa required" />
      </div>

      <div className="grid sm:grid-cols-3 gap-4">
        <div>
          <label className={labelClass}>Salary min</label>
          <input type="number" value={salaryMin} onChange={(e) => setSalaryMin(e.target.value)} className={inputClass} />
        </div>
        <div>
          <label className={labelClass}>Salary max</label>
          <input type="number" value={salaryMax} onChange={(e) => setSalaryMax(e.target.value)} className={inputClass} />
        </div>
        <div>
          <label className={labelClass}>Currency</label>
          <input value={salaryCurrency} onChange={(e) => setSalaryCurrency(e.target.value)} className={inputClass}
            placeholder="KES" />
        </div>
      </div>

      {errorMessage && <p className="text-red-400 text-sm">{errorMessage}</p>}

      <button type="submit" disabled={isSubmitting}
        className="bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white rounded px-5 py-2 font-medium">
        {isSubmitting ? 'Saving...' : submitLabel}
      </button>
    </form>
  );
}
