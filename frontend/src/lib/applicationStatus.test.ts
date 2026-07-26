import { describe, it, expect } from 'vitest';
import {
  APPLICATION_STATUS_ORDER,
  APPLICATION_STATUS_LABELS,
  APPLICATION_STATUS_COLORS,
} from './applicationStatus';

describe('applicationStatus', () => {
  it('has exactly one label for every status in the order list', () => {
    for (const status of APPLICATION_STATUS_ORDER) {
      expect(APPLICATION_STATUS_LABELS[status]).toBeTruthy();
    }
    expect(Object.keys(APPLICATION_STATUS_LABELS)).toHaveLength(
      APPLICATION_STATUS_ORDER.length,
    );
  });

  it('has exactly one color class set for every status in the order list', () => {
    for (const status of APPLICATION_STATUS_ORDER) {
      expect(APPLICATION_STATUS_COLORS[status]).toBeTruthy();
    }
    expect(Object.keys(APPLICATION_STATUS_COLORS)).toHaveLength(
      APPLICATION_STATUS_ORDER.length,
    );
  });

  it('lists draft first, since it is the only status the backend sets on create', () => {
    expect(APPLICATION_STATUS_ORDER[0]).toBe('draft');
  });

  it('mirrors the backend CHECK constraint\'s six statuses', () => {
    expect(APPLICATION_STATUS_ORDER).toEqual([
      'draft',
      'submitted',
      'interviewing',
      'rejected',
      'offer',
      'withdrawn',
    ]);
  });
});
