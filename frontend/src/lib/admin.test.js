import { describe, expect, it } from 'vitest';

import { isRunActive, labelOf, webhookStatus, workerTone } from './admin';

describe('webhookStatus', () => {
  it('shows a failed verification as rejected, whatever else is set', () => {
    expect(webhookStatus({ verified: false, processed: false, result: null })).toEqual({
      tone: 'danger',
      label: 'Rejected',
    });
  });

  it('shows a verified event waiting for the runner as queued', () => {
    expect(webhookStatus({ verified: true, processed: false, result: null }).label).toBe('Queued');
  });

  it('labels processed events by their result', () => {
    expect(webhookStatus({ verified: true, processed: true, result: 'needs_attention' })).toEqual({
      tone: 'danger',
      label: 'Needs attention',
    });
    expect(webhookStatus({ verified: true, processed: true, result: 'fixed' }).tone).toBe(
      'settled',
    );
  });
});

describe('isRunActive', () => {
  it('polls only while a run is queued or running', () => {
    expect(isRunActive({ status: 'queued' })).toBe(true);
    expect(isRunActive({ status: 'running' })).toBe(true);
    expect(isRunActive({ status: 'done' })).toBe(false);
    expect(isRunActive(null)).toBe(false);
  });
});

describe('labels', () => {
  it('turns API values into sentence case', () => {
    expect(labelOf('in_sync')).toBe('In sync');
    expect(labelOf(null)).toBe('');
  });

  it('marks suspended workers as danger', () => {
    expect(workerTone('suspended')).toBe('danger');
    expect(workerTone('unknown')).toBe('released');
  });
});
