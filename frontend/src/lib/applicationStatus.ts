import type { ApplicationStatus } from './types';

// Mirrors the backend's applications.status CHECK constraint exactly
// (profiles/models.py ApplicationStatus) -- draft is the only status the
// backend ever sets on create; every other value is only reachable via
// the PATCH status-update endpoint.
export const APPLICATION_STATUS_ORDER: ApplicationStatus[] = [
  'draft',
  'submitted',
  'interviewing',
  'rejected',
  'offer',
  'withdrawn',
];

export const APPLICATION_STATUS_LABELS: Record<ApplicationStatus, string> = {
  draft: 'Draft',
  submitted: 'Submitted',
  interviewing: 'Interviewing',
  rejected: 'Rejected',
  offer: 'Offer',
  withdrawn: 'Withdrawn',
};

export const APPLICATION_STATUS_COLORS: Record<ApplicationStatus, string> = {
  draft: 'bg-slate-800 text-slate-300',
  submitted: 'bg-indigo-950/60 text-indigo-300 border border-indigo-800/50',
  interviewing: 'bg-amber-950/40 text-amber-300 border border-amber-800/50',
  rejected: 'bg-red-950/40 text-red-300 border border-red-800/50',
  offer: 'bg-emerald-950/40 text-emerald-300 border border-emerald-800/50',
  withdrawn: 'bg-slate-800/60 text-slate-500',
};
