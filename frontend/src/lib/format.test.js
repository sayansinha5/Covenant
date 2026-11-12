import { describe, expect, it } from 'vitest';

import { formatDateTime, formatMoney } from './format';

describe('formatMoney', () => {
  it('formats decimal strings with two places', () => {
    expect(formatMoney('40.00')).toBe('$40.00');
    expect(formatMoney('1234.5')).toBe('$1,234.50');
    expect(formatMoney('0.01')).toBe('$0.01');
  });

  it('keeps large amounts exact', () => {
    expect(formatMoney('9999999999.99')).toBe('$9,999,999,999.99');
  });

  it('returns an empty string for missing values', () => {
    expect(formatMoney(null)).toBe('');
    expect(formatMoney(undefined)).toBe('');
  });

  it('refuses numbers so money never passes through floats', () => {
    expect(() => formatMoney(40)).toThrow(TypeError);
    expect(() => formatMoney('40.001')).toThrow(TypeError);
  });
});

describe('formatDateTime', () => {
  it('treats timestamps without a zone as UTC and shows the zone', () => {
    const text = formatDateTime('2026-11-03T09:32:00', { locale: 'en-GB', timeZone: 'UTC' });
    expect(text).toContain('09:32');
    expect(text).toContain('UTC');
  });

  it('converts to the requested time zone', () => {
    const text = formatDateTime('2026-11-03T09:32:00Z', {
      locale: 'en-GB',
      timeZone: 'Asia/Kolkata',
    });
    expect(text).toContain('15:02');
  });
});
