import { useState } from 'react';
import { Check } from 'lucide-react';
import { useQueryClient } from '@tanstack/react-query';

import { api, problemOf } from '../../lib/api';
import { cn } from '../../lib/cn';
import { formatDateTime, formatMoney } from '../../lib/format';
import { CONTRACT_KEY, CONTRACTS_KEY } from '../../lib/queries';
import { Alert } from '../ui/Alert';
import { Button } from '../ui/Button';
import { Modal } from '../ui/Modal';
import { checkSummary } from './checks';

export function ContractReview({ contract, open, onClose, canFund }) {
  const queryClient = useQueryClient();
  const [change, setChange] = useState('');
  const [asking, setAsking] = useState(false);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [pending, setPending] = useState('');
  const [copied, setCopied] = useState(false);
  const [seenId, setSeenId] = useState(contract?.id);
  if (contract && contract.id !== seenId) {
    setSeenId(contract.id);
    setAsking(false);
    setChange('');
    setError('');
    setCopied(false);
  }
  if (!contract) return null;
  const spec = contract.spec ?? {};
  const hash = (contract.spec_fingerprint ?? '').slice(0, 12);
  const bands = spec.bands ?? {};
  const passMin = Math.round((bands.pass_min ?? 0.9) * 100);
  const partialMin = Math.round((bands.partial_min ?? 0.5) * 100);
  const checks = spec.hard_checks ?? [];
  const rubric = spec.rubric ?? [];

  function dismiss() {
    if (busy) return;
    setAsking(false);
    setError('');
    onClose();
  }

  async function agree() {
    setAsking(false);
    setBusy(true);
    setPending('agree');
    setError('');
    try {
      await api.post(`/contracts/${contract.id}/agree`, null, {
        headers: { 'Idempotency-Key': crypto.randomUUID() },
      });
      await queryClient.invalidateQueries({ queryKey: CONTRACT_KEY });
      await queryClient.invalidateQueries({ queryKey: CONTRACTS_KEY });
      onClose();
    } catch (err) {
      setError(problemOf(err).detail);
    } finally {
      setBusy(false);
      setPending('');
    }
  }

  async function revise() {
    setBusy(true);
    setPending('revise');
    setError('');
    try {
      await api.post(`/contracts/${contract.id}/revise`, { change_request: change });
      await queryClient.invalidateQueries({ queryKey: CONTRACT_KEY });
      setAsking(false);
      setChange('');
    } catch (err) {
      setError(problemOf(err).detail);
    } finally {
      setBusy(false);
      setPending('');
    }
  }

  async function decline() {
    setBusy(true);
    setPending('decline');
    setError('');
    try {
      await api.post(`/contracts/${contract.id}/cancel`, null, {
        headers: { 'Idempotency-Key': crypto.randomUUID() },
      });
      await queryClient.invalidateQueries({ queryKey: CONTRACT_KEY });
      onClose();
    } catch (err) {
      setError(problemOf(err).detail);
    } finally {
      setBusy(false);
      setPending('');
    }
  }

  async function copyHash() {
    try {
      await navigator.clipboard.writeText(contract.spec_fingerprint);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false);
    }
  }

  const waiting = contract.state === 'awaiting_agreement';
  const canAct = waiting && canFund;
  return (
    <Modal
      open={open}
      title="Review contract"
      onClose={dismiss}
      busy={busy}
      width="lg"
      footer={
        <div className="flex w-full flex-wrap items-center justify-between gap-2">
          <Button variant="secondary" disabled={busy} onClick={dismiss}>
            Close
          </Button>
          {canAct && (
            <div className="flex flex-wrap justify-end gap-2">
              <Button variant="ghost" disabled={busy} onClick={() => void decline()}>
                Decline
              </Button>
              <Button
                variant="secondary"
                disabled={busy}
                onClick={() => setAsking((value) => !value)}
              >
                Ask for changes
              </Button>
              <Button
                loading={pending === 'agree'}
                loadingText="Asking PayPal"
                disabled={busy}
                onClick={() => void agree()}
              >
                Agree and fund
              </Button>
            </div>
          )}
        </div>
      }
    >
      <div className="flex flex-col gap-5 text-base">
        {error && <Alert tone="danger">{error}</Alert>}

        <div className="rounded-lg border border-line bg-wash px-4 py-3">
          <p className="text-sm text-ink-muted">
            {contract.number} · {contract.worker_name}
          </p>
          <p className="mt-1 text-2xl font-semibold tracking-tight tabular-nums">
            {formatMoney(contract.amount, contract.currency)}
          </p>
          <p className="mt-1 text-sm text-ink-muted">
            PayPal holds this before the work starts. You pay only for the part that passes.
          </p>
        </div>

        <section className="flex flex-col gap-2">
          <h3 className="text-sm font-medium">What you will get</h3>
          <p>{spec.deliverable_description || contract.request_text}</p>
          {contract.deadline_at && (
            <p className="text-sm text-ink-muted">Due {formatDateTime(contract.deadline_at)}</p>
          )}
        </section>

        {checks.length > 0 && (
          <section className="flex flex-col gap-2">
            <div>
              <h3 className="text-sm font-medium">Must be true</h3>
              <p className="text-sm text-ink-muted">Every line here has to pass.</p>
            </div>
            <ul className="flex flex-col gap-2">
              {checks.map((check) => (
                <li
                  key={check.id}
                  className="flex items-start gap-2 rounded-md border border-line px-3 py-2 text-sm"
                >
                  <Check
                    size={16}
                    strokeWidth={1.5}
                    aria-hidden="true"
                    className="mt-0.5 shrink-0 text-brand"
                  />
                  <span>{checkSummary(check)}</span>
                </li>
              ))}
            </ul>
          </section>
        )}

        {rubric.length > 0 && (
          <section className="flex flex-col gap-2">
            <div>
              <h3 className="text-sm font-medium">How the work is scored</h3>
              <p className="text-sm text-ink-muted">The score is a mix of these.</p>
            </div>
            <ul className="flex flex-col gap-2">
              {rubric.map((item) => (
                <li key={item.id} className="rounded-md border border-line px-3 py-2">
                  <div className="flex items-baseline justify-between gap-3">
                    <span className="font-medium">{item.name}</span>
                    <span className="shrink-0 text-sm text-ink-muted tabular-nums">
                      {Math.round(item.weight * 100)}% of the score
                    </span>
                  </div>
                  {item.description && (
                    <p className="mt-0.5 text-sm text-ink-muted">{item.description}</p>
                  )}
                </li>
              ))}
            </ul>
          </section>
        )}

        <section className="flex flex-col gap-2">
          <h3 className="text-sm font-medium">How the money moves</h3>
          <div className="grid gap-2 sm:grid-cols-3">
            <Outcome
              tone="settled"
              title="Full payment"
              detail={`${passMin}% or more of the work passes.`}
            />
            <Outcome
              tone="held"
              title="Part of it"
              detail={`From ${partialMin}% passes. The rest is released.`}
            />
            <Outcome
              tone="released"
              title="Nothing is paid"
              detail="Below that, or the delivery tries to game the check."
            />
          </div>
        </section>

        {hash && (
          <p className="flex flex-wrap items-center gap-2 text-sm text-ink-muted">
            <span>
              Agreement record <span className="font-mono text-ink">{hash}</span>
            </span>
            <button
              type="button"
              className="text-brand hover:underline"
              onClick={() => void copyHash()}
            >
              {copied ? 'Copied' : 'Copy'}
            </button>
          </p>
        )}

        {asking && (
          <div className="flex flex-col gap-2 rounded-lg border border-line bg-wash p-3">
            <label htmlFor="contract-change" className="text-sm font-medium">
              What should change?
            </label>
            <textarea
              id="contract-change"
              className="min-h-24 rounded-md border border-line bg-surface p-3 text-base placeholder:text-ink-muted focus:border-brand focus:outline-none"
              value={change}
              onChange={(event) => setChange(event.target.value)}
              placeholder="The deadline, the price, or what done means"
            />
            <div className="flex justify-end gap-2">
              <Button variant="secondary" disabled={busy} onClick={() => setAsking(false)}>
                Back
              </Button>
              <Button
                loading={pending === 'revise'}
                loadingText="Revising"
                disabled={change.trim().length === 0}
                onClick={() => void revise()}
              >
                Revise contract
              </Button>
            </div>
          </div>
        )}
      </div>
    </Modal>
  );
}

function Outcome({ tone, title, detail }) {
  return (
    <div className={cn('rounded-md px-3 py-2', TONE[tone])}>
      <p className="text-sm font-medium">{title}</p>
      <p className="mt-0.5 text-sm">{detail}</p>
    </div>
  );
}

const TONE = {
  settled: 'bg-settled-bg text-settled',
  held: 'bg-held-bg text-held',
  released: 'bg-released-bg text-released',
};
