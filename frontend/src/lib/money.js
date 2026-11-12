/** Money input helpers. Amounts are compared as integer cents (BigInt), never as floats. */

export const AMOUNT_PATTERN = /^\d{1,10}(\.\d{1,2})?$/;

export function toCents(amount) {
  const [whole, fraction = ''] = amount.trim().split('.');
  return BigInt(whole) * 100n + BigInt(fraction.padEnd(2, '0'));
}

/** "40" → "40.00", "40.5" → "40.50"; the API expects exactly two decimals. */
export function normalizeAmount(amount) {
  const [whole, fraction = ''] = amount.trim().split('.');
  return `${BigInt(whole)}.${fraction.padEnd(2, '0')}`;
}
