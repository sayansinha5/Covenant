import { describe, expect, it } from 'vitest';

import { PASSWORD_RULES, passwordMeetsRules } from './password';

const failing = (value) => PASSWORD_RULES.filter((r) => !r.test(value)).map((r) => r.id);

describe('password rules', () => {
  it('match the backend rules', () => {
    expect(failing('correct horse battery 9')).toEqual([]);
    expect(failing('short1')).toEqual(['length']);
    expect(failing('123456789012')).toEqual(['letter']);
    expect(failing('no numbers here')).toEqual(['number']);
  });

  it('rejects passwords over the maximum length', () => {
    expect(passwordMeetsRules(`a1${'x'.repeat(126)}`)).toBe(true);
    expect(passwordMeetsRules(`a1${'x'.repeat(127)}`)).toBe(false);
  });
});
