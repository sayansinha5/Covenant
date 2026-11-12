const TONE = {
  settled: 'settled',
  partially_settled: 'settled',
  refunded: 'released',
  cancelled: 'released',
  expired: 'released',
  needs_attention: 'danger',
  under_appeal: 'danger',
  funding: 'held',
  funded: 'held',
  verifying: 'held',
};

export function stateTone(state) {
  return TONE[state] ?? 'info';
}

export function stateLabel(state) {
  return String(state ?? '').replaceAll('_', ' ');
}
