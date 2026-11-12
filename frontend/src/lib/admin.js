/** Display rules for the S17 Admin page. */

const WORKER_TONES = {
  verified: 'settled',
  pending: 'info',
  unhealthy: 'held',
  failed: 'danger',
  suspended: 'danger',
};
const RESULT_TONES = {
  in_sync: 'settled',
  fixed: 'settled',
  ignored: 'released',
  needs_attention: 'danger',
  error: 'danger',
};

export function workerTone(status) {
  return WORKER_TONES[status] ?? 'released';
}

export function resultTone(result) {
  return RESULT_TONES[result] ?? 'info';
}

export function labelOf(value) {
  if (!value) return '';
  const words = value.replaceAll('_', ' ');
  return words[0].toUpperCase() + words.slice(1);
}

/** A run the runner hasn't finished yet; the page keeps polling while this holds. */
export function isRunActive(run) {
  return run?.status === 'queued' || run?.status === 'running';
}

/** Where a webhook event stands, in one short label. */
export function webhookStatus(event) {
  if (!event.verified) return { tone: 'danger', label: 'Rejected' };
  if (!event.processed) return { tone: 'info', label: 'Queued' };
  return { tone: resultTone(event.result), label: labelOf(event.result) };
}
