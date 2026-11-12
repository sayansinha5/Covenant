import { useState } from 'react';
import { useParams } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';

import { useAuth } from '../auth/context';
import { ContractReview } from '../components/contracts/ContractReview';
import { stateLabel, stateTone } from '../components/contracts/state';
import { Alert } from '../components/ui/Alert';
import { Badge } from '../components/ui/Badge';
import { Button } from '../components/ui/Button';
import { Card } from '../components/ui/Card';
import { Spinner } from '../components/ui/Spinner';
import { api, problemOf } from '../lib/api';
import { formatDateTime, formatMoney } from '../lib/format';
import { CONTRACT_KEY, useContract } from '../lib/queries';

export function ContractDetail() {
  const { contractId } = useParams();
  const contract = useContract(contractId);
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [review, setReview] = useState(false);
  const [delivery, setDelivery] = useState('');
  const [argument, setArgument] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  if (contract.isLoading) return <Spinner />;
  if (contract.isError) return <Alert tone="danger">{problemOf(contract.error).detail}</Alert>;
  const data = contract.data;
  const canManage = ['owner', 'admin'].includes(user.membership.role);
  const provider = data.role === 'provider' || data.role === 'both';
  const hirer = data.role === 'hirer' || data.role === 'both';

  async function act(path, body) {
    setBusy(true);
    setError('');
    try {
      await api.post(path, body ?? null);
      await queryClient.invalidateQueries({ queryKey: [...CONTRACT_KEY, contractId] });
    } catch (err) {
      setError(problemOf(err).detail);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-xl font-semibold">{data.title}</h2>
          <p className="text-ink-muted">
            {data.number} · {data.worker_name} · {formatMoney(data.amount, data.currency)}
          </p>
        </div>
        <Badge tone={stateTone(data.state)}>{stateLabel(data.state)}</Badge>
      </div>
      {error && <Alert tone="danger">{error}</Alert>}
      {data.verdict?.result === 'manipulation' && (
        <Alert tone="danger">{data.verdict.reasoning}</Alert>
      )}
      {data.verdict && data.verdict.result !== 'manipulation' && (
        <Alert tone="info">
          {data.verdict.result} · {data.verdict.reasoning}
        </Alert>
      )}
      <div className="grid gap-4 lg:grid-cols-[2fr_1fr]">
        <Card className="flex flex-col gap-3 p-5">
          <h3 className="font-semibold">Timeline</h3>
          <ol className="flex flex-col gap-3">
            {data.events.map((event) => (
              <li key={event.id}>
                <div className="text-sm text-ink-muted">{formatDateTime(event.created_at)}</div>
                <div>{event.message}</div>
              </li>
            ))}
          </ol>
        </Card>
        <Card className="flex flex-col gap-2 p-5">
          <h3 className="font-semibold">Money</h3>
          {data.escrow ? (
            <>
              <p>Held {formatMoney(data.escrow.amount_held, data.currency)}</p>
              <p>Captured {formatMoney(data.escrow.amount_captured, data.currency)}</p>
              <p>Released {formatMoney(data.escrow.amount_released, data.currency)}</p>
            </>
          ) : (
            <p className="text-ink-muted">No PayPal hold yet.</p>
          )}
          {hirer && data.state === 'awaiting_agreement' && (
            <Button onClick={() => setReview(true)}>Review and fund</Button>
          )}
          {provider && data.state === 'sent_to_worker' && (
            <div className="flex gap-2">
              <Button disabled={busy} onClick={() => void act(`/contracts/${data.id}/accept`)}>
                Accept
              </Button>
              <Button
                variant="secondary"
                disabled={busy}
                onClick={() => void act(`/contracts/${data.id}/decline`)}
              >
                Decline
              </Button>
            </div>
          )}
          {provider && data.state === 'verdict_issued' && (
            <Button
              disabled={busy}
              onClick={() => void act(`/contracts/${data.id}/accept-verdict`)}
            >
              Accept verdict
            </Button>
          )}
        </Card>
      </div>
      {provider && data.state === 'in_progress' && (
        <Card className="flex flex-col gap-2 p-5">
          <h3 className="font-semibold">Submit delivery</h3>
          <textarea
            className="min-h-28 rounded-md border border-line p-2"
            value={delivery}
            onChange={(event) => setDelivery(event.target.value)}
            placeholder="Paste the delivery. JSON is fine."
          />
          <Button
            disabled={busy || !delivery.trim()}
            onClick={() =>
              void act(`/contracts/${data.id}/deliver`, { content: parseDelivery(delivery) })
            }
          >
            Submit
          </Button>
        </Card>
      )}
      {provider && data.state === 'verdict_issued' && (
        <Card className="flex flex-col gap-2 p-5">
          <h3 className="font-semibold">Appeal</h3>
          <textarea
            className="min-h-24 rounded-md border border-line p-2"
            value={argument}
            onChange={(event) => setArgument(event.target.value)}
            placeholder="At least 50 characters."
          />
          <Button
            variant="secondary"
            disabled={busy || argument.trim().length < 50}
            onClick={() => void act(`/contracts/${data.id}/appeal`, { argument })}
          >
            Submit appeal
          </Button>
        </Card>
      )}
      {hirer && canManage && data.state === 'under_appeal' && (
        <Card className="flex flex-col gap-3 p-5">
          <h3 className="font-semibold">Appeal</h3>
          <p>{data.appeal?.argument}</p>
          {data.appeal?.memo && <p className="text-ink-muted">{data.appeal.memo.summary}</p>}
          <div className="flex gap-2">
            <Button
              disabled={busy}
              onClick={() => void act(`/contracts/${data.id}/appeal-decision`, { accept: true })}
            >
              Accept appeal
            </Button>
            <Button
              variant="secondary"
              disabled={busy}
              onClick={() => void act(`/contracts/${data.id}/appeal-decision`, { accept: false })}
            >
              Uphold verdict
            </Button>
          </div>
        </Card>
      )}
      {hirer && canManage && data.verdict?.result === 'needs_review' && (
        <div className="flex gap-2">
          {['pass', 'partial', 'fail'].map((band) => (
            <Button
              key={band}
              variant="secondary"
              disabled={busy}
              onClick={() => void act(`/contracts/${data.id}/band`, { band })}
            >
              {band}
            </Button>
          ))}
        </div>
      )}
      <ContractReview
        contract={data}
        open={review}
        onClose={() => setReview(false)}
        canFund={hirer && canManage}
      />
    </div>
  );
}

function parseDelivery(text) {
  try {
    return JSON.parse(text);
  } catch {
    return { text };
  }
}
