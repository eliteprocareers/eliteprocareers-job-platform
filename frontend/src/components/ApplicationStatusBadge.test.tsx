import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import ApplicationStatusBadge from './ApplicationStatusBadge';
import { APPLICATION_STATUS_ORDER, APPLICATION_STATUS_LABELS } from '../lib/applicationStatus';

describe('ApplicationStatusBadge', () => {
  it.each(APPLICATION_STATUS_ORDER)('renders the correct label for status "%s"', (status) => {
    render(<ApplicationStatusBadge status={status} />);
    expect(screen.getByText(APPLICATION_STATUS_LABELS[status])).toBeInTheDocument();
  });

  it('renders the submitted status with indigo styling', () => {
    render(<ApplicationStatusBadge status="submitted" />);
    const badge = screen.getByText('Submitted');
    expect(badge.className).toContain('indigo');
  });

  it('renders the rejected status with red styling', () => {
    render(<ApplicationStatusBadge status="rejected" />);
    const badge = screen.getByText('Rejected');
    expect(badge.className).toContain('red');
  });
});
