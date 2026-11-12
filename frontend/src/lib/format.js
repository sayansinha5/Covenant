/**
 * Money and date formatting. Amounts stay strings ("40.00") from the API until display;
 * the UI never does arithmetic on money.
 */

const moneyFormatters = new Map();

export function formatMoney(amount, currency = 'USD') {
  if (amount === null || amount === undefined || amount === '') return '';
  if (typeof amount !== 'string' || !/^-?\d+(\.\d{1,2})?$/.test(amount)) {
    throw new TypeError(`formatMoney expects a decimal string like "40.00", got ${amount}`);
  }
  if (!moneyFormatters.has(currency)) {
    moneyFormatters.set(
      currency,
      new Intl.NumberFormat('en-US', { style: 'currency', currency, minimumFractionDigits: 2 }),
    );
  }
  // Intl accepts decimal strings exactly, so no float conversion happens here.
  return moneyFormatters.get(currency).format(amount);
}

/** "$300" for whole amounts, "$40.50" otherwise; for sentences rather than tables. */
export function formatMoneyShort(amount, currency = 'USD') {
  return formatMoney(amount, currency).replace(/\.00$/, '');
}

export function formatDateTime(isoUtc, { locale, timeZone } = {}) {
  if (!isoUtc) return '';
  const value = /[zZ]|[+-]\d\d:\d\d$/.test(isoUtc) ? isoUtc : `${isoUtc}Z`;
  // dateStyle/timeStyle can't be combined with timeZoneName, so the fields are spelled out.
  return new Intl.DateTimeFormat(locale, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    timeZoneName: 'short',
    timeZone,
  }).format(new Date(value));
}
