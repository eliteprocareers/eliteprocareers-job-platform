import type { ApplicationStatus } from '../lib/types';
import { APPLICATION_STATUS_COLORS, APPLICATION_STATUS_LABELS } from '../lib/applicationStatus';

export default function ApplicationStatusBadge({ status }: { status: ApplicationStatus }) {
  return (
    <span
      className={`text-xs rounded px-2 py-0.5 font-medium ${APPLICATION_STATUS_COLORS[status]}`}
    >
      {APPLICATION_STATUS_LABELS[status]}
    </span>
  );
}
