import { describe, expect, it } from 'vitest';

import { mandateSchema, mandateSentence } from './mandate';
import { normalizeAmount, toCents } from './money';

const VALID = {
  monthly_budget: '300',
  per_task_cap: '60',
  approval_threshold: '40',
  allowed_work_types: ['translation'],
};

function issuesFor(terms) {
  const result = mandateSchema.safeParse(terms);
  return result.success
    ? {}
    : Object.fromEntries(result.error.issues.map((i) => [i.path.join('.'), i.message]));
}

describe('mandateSchema', () => {
  it('accepts consistent terms', () => {
    expect(issuesFor(VALID)).toEqual({});
  });

  it('reports malformed amounts without throwing', () => {
    expect(issuesFor({ ...VALID, monthly_budget: 'abc' })).toEqual({
      monthly_budget: 'Enter the monthly budget like 40 or 40.00',
    });
    expect(issuesFor({ ...VALID, per_task_cap: '0' })).toEqual({
      per_task_cap: 'The maximum per task must be more than $0',
    });
  });

  it('puts cross-field errors on the field to fix', () => {
    expect(issuesFor({ ...VALID, per_task_cap: '300.01' })).toEqual({
      per_task_cap: "Maximum per task can't be more than the monthly budget",
    });
    expect(issuesFor({ ...VALID, approval_threshold: '60.50' })).toEqual({
      approval_threshold: "The approval threshold can't be more than the maximum per task",
    });
    expect(issuesFor({ ...VALID, allowed_work_types: [] })).toEqual({
      allowed_work_types: 'Choose at least one work type',
    });
  });
});

describe('mandateSentence', () => {
  it('matches the wording in the sign dialog', () => {
    expect(
      mandateSentence('Mira', {
        monthly_budget: '300.00',
        per_task_cap: '60.00',
        approval_threshold: '40.00',
        allowed_work_types: ['translation', 'catalog_data', 'copywriting', 'design'],
      }),
    ).toBe(
      'Mira may spend up to $300 per month, $60 per task, and will ask you before anything ' +
        'above $40, only on translation, catalogue data, copywriting and design.',
    );
  });

  it('handles one work type and cents', () => {
    expect(
      mandateSentence('Asha', {
        monthly_budget: '1250.50',
        per_task_cap: '60.00',
        approval_threshold: '40.25',
        allowed_work_types: ['design'],
      }),
    ).toContain(
      '$1,250.50 per month, $60 per task, and will ask you before anything above $40.25, only on design.',
    );
  });
});

describe('money input helpers', () => {
  it('compares amounts as exact cents', () => {
    expect(toCents('60')).toBe(6000n);
    expect(toCents('0.1')).toBe(10n);
    expect(toCents('300.05') > toCents('300.5')).toBe(false);
  });

  it('normalizes to two decimals', () => {
    expect(normalizeAmount('40')).toBe('40.00');
    expect(normalizeAmount('040.5')).toBe('40.50');
  });
});
