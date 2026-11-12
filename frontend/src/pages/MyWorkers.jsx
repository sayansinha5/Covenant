import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';

import { Alert } from '../components/ui/Alert';
import { Badge } from '../components/ui/Badge';
import { Button } from '../components/ui/Button';
import { Card } from '../components/ui/Card';
import { Field, TextInput } from '../components/ui/Field';
import { Modal } from '../components/ui/Modal';
import { Spinner } from '../components/ui/Spinner';
import { useToast } from '../components/ui/toast-context';
import { labelOf, workerTone } from '../lib/admin';
import { api, problemOf } from '../lib/api';
import { cn } from '../lib/cn';
import { formatMoney } from '../lib/format';
import { MY_WORKERS_KEY, useMyWorkers, useVerification } from '../lib/queries';

const CATEGORIES = [
  ['translation', 'Translation'],
  ['catalog_data', 'Catalogue data'],
  ['copywriting', 'Copywriting'],
  ['design', 'Design'],
];
const STEP_LABELS = {
  agent_card: 'Fetching Agent Card',
  skills: 'Checking skills',
  test_job: 'Running test job',
  checks: 'Checking the result',
};

function Status({ worker }) {
  const labels = {
    pending: 'Pending verification',
    verified: 'Verified',
    failed: 'Failed verification',
    suspended: 'Suspended',
    unhealthy: 'Unhealthy',
  };
  return (
    <Badge tone={workerTone(worker.status)}>
      {labels[worker.status] ?? labelOf(worker.status)}
    </Badge>
  );
}

function AddWorker({ open, onClose }) {
  const [mode, setMode] = useState(null);
  const [form, setForm] = useState({
    base_url: '',
    display_name: '',
    description: '',
    price: '',
    categories: ['translation'],
  });
  const [workerId, setWorkerId] = useState(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [watching, setWatching] = useState(false);
  const verification = useVerification(workerId, watching);
  const queryClient = useQueryClient();
  const toast = useToast();

  function toggle(category) {
    setForm((current) => {
      const has = current.categories.includes(category);
      const categories = has
        ? current.categories.filter((item) => item !== category)
        : [...current.categories, category];
      return { ...current, categories };
    });
  }

  async function submit(event) {
    event.preventDefault();
    if (form.categories.length === 0) {
      setError('Pick at least one category.');
      return;
    }
    setSaving(true);
    setError(null);
    const path = mode === 'agent' ? '/workers/agent' : '/workers/human';
    const body =
      mode === 'agent'
        ? { base_url: form.base_url, price: form.price, categories: form.categories }
        : {
            display_name: form.display_name,
            description: form.description,
            price: form.price,
            categories: form.categories,
          };
    try {
      const { data } = await api.post(path, body);
      await queryClient.invalidateQueries({ queryKey: MY_WORKERS_KEY });
      if (mode === 'agent') {
        setWorkerId(data.id);
        setWatching(true);
      } else {
        toast(`${data.display_name} is verified.`);
        onClose();
      }
    } catch (failure) {
      setError(problemOf(failure).detail);
    } finally {
      setSaving(false);
    }
  }

  const done = verification.data && verification.data.status !== 'pending';
  return (
    <Modal
      open={open}
      title="Add worker"
      onClose={onClose}
      busy={saving}
      width="lg"
      footer={
        mode && !workerId ? (
          <>
            <Button variant="secondary" onClick={() => setMode(null)} disabled={saving}>
              Back
            </Button>
            <Button type="submit" form="add-worker" loading={saving} loadingText="Saving…">
              {mode === 'agent' ? 'Verify agent' : 'Add me'}
            </Button>
          </>
        ) : (
          <Button variant="secondary" onClick={onClose}>
            Close
          </Button>
        )
      }
    >
      {!mode && (
        <div className="grid gap-3 sm:grid-cols-2">
          <button type="button" onClick={() => setMode('agent')} className="text-left">
            <Card className="h-full p-4">
              <h3 className="font-semibold">Connect an AI agent</h3>
              <p className="mt-1 text-sm text-ink-muted">
                Covenant reads its agent card and runs a test job.
              </p>
            </Card>
          </button>
          <button type="button" onClick={() => setMode('human')} className="text-left">
            <Card className="h-full p-4">
              <h3 className="font-semibold">I'll do the work myself</h3>
              <p className="mt-1 text-sm text-ink-muted">
                You're verified immediately. Reputation comes from the work.
              </p>
            </Card>
          </button>
        </div>
      )}
      {mode && !workerId && (
        <form id="add-worker" onSubmit={submit} className="flex flex-col gap-4">
          {mode === 'agent' ? (
            <Field
              id="agent-url"
              label="Agent URL"
              hint="Covenant reads /.well-known/agent-card.json"
            >
              {(aria) => (
                <TextInput
                  required
                  value={form.base_url}
                  onChange={(e) => setForm({ ...form, base_url: e.target.value })}
                  placeholder="http://127.0.0.1:9101"
                  {...aria}
                />
              )}
            </Field>
          ) : (
            <>
              <Field id="human-name" label="Display name">
                {(aria) => (
                  <TextInput
                    required
                    value={form.display_name}
                    onChange={(e) => setForm({ ...form, display_name: e.target.value })}
                    {...aria}
                  />
                )}
              </Field>
              <Field id="human-bio" label="Short bio">
                {(aria) => (
                  <TextInput
                    required
                    value={form.description}
                    onChange={(e) => setForm({ ...form, description: e.target.value })}
                    {...aria}
                  />
                )}
              </Field>
            </>
          )}
          <Field id="worker-price" label="Price per job (USD)">
            {(aria) => (
              <TextInput
                required
                inputMode="decimal"
                pattern="\d+\.\d{2}"
                placeholder="40.00"
                value={form.price}
                onChange={(e) => setForm({ ...form, price: e.target.value })}
                {...aria}
              />
            )}
          </Field>
          <fieldset className="flex flex-col gap-2">
            <legend className="text-sm font-medium">Categories</legend>
            {CATEGORIES.map(([value, label]) => (
              <label key={value} className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={form.categories.includes(value)}
                  onChange={() => toggle(value)}
                />
                {label}
              </label>
            ))}
          </fieldset>
          {error && <Alert tone="danger">{error}</Alert>}
        </form>
      )}
      {workerId && (
        <ol className="flex flex-col gap-2 text-sm">
          {(verification.data?.steps ?? []).map((step) => (
            <li key={step.step}>
              {STEP_LABELS[step.step] ?? step.step} {step.result === 'ok' ? '✓' : '✗'}
              {step.result === 'failed' && <span className="text-danger"> {step.detail}</span>}
            </li>
          ))}
          {!done && (
            <li className="flex items-center gap-2 text-ink-muted">
              <Spinner /> Working…
            </li>
          )}
          {done && (
            <li className="font-medium">
              {verification.data.status === 'verified' ? 'Passed' : 'Failed'}
            </li>
          )}
        </ol>
      )}
    </Modal>
  );
}

/** S13: the organization's workers and the add-worker flow. */
export function MyWorkers() {
  const workers = useMyWorkers();
  const [adding, setAdding] = useState(false);
  const [error, setError] = useState(null);
  const queryClient = useQueryClient();

  async function retry(id) {
    setError(null);
    try {
      await api.post(`/workers/${id}/verify`);
      await queryClient.invalidateQueries({ queryKey: MY_WORKERS_KEY });
    } catch (err) {
      setError(problemOf(err).detail);
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between gap-3">
        <Link to="/fleet" className="text-sm text-brand">
          See which of these are running on the fleet
        </Link>
        <Button onClick={() => setAdding(true)}>Add worker</Button>
      </div>
      {workers.isPending && <Spinner className="text-ink-muted" />}
      {workers.isError && <Alert tone="danger">{problemOf(workers.error).detail}</Alert>}
      {error && <Alert tone="danger">{error}</Alert>}
      {workers.data && (
        <Card className="overflow-hidden">
          {workers.data.length === 0 ? (
            <p className="px-5 py-4 text-ink-muted">No workers yet.</p>
          ) : (
            <table className="w-full text-sm">
              <thead className="text-left text-ink-muted">
                <tr className="border-b border-line">
                  {['Name', 'Kind', 'Status', 'Categories', 'Price', 'Reputation', 'Jobs'].map(
                    (heading) => (
                      <th
                        key={heading}
                        className={cn('px-5 py-2 font-medium', heading === 'Price' && 'text-right')}
                      >
                        {heading}
                      </th>
                    ),
                  )}
                </tr>
              </thead>
              <tbody>
                {workers.data.map((worker) => (
                  <tr key={worker.id} className="border-b border-line last:border-0">
                    <td className="px-5 py-2 font-medium">{worker.display_name}</td>
                    <td className="px-5 py-2">{labelOf(worker.kind)}</td>
                    <td className="px-5 py-2">
                      <Status worker={worker} />
                      {worker.kind === 'agent' && worker.status === 'failed' && (
                        <button
                          type="button"
                          className="ml-2 text-brand hover:underline"
                          onClick={() => retry(worker.id)}
                        >
                          Try again
                        </button>
                      )}
                    </td>
                    <td className="px-5 py-2">{worker.categories.map(labelOf).join(', ')}</td>
                    <td className="px-5 py-2 text-right tabular-nums">
                      {formatMoney(worker.price, worker.currency)}
                    </td>
                    <td className="px-5 py-2 tabular-nums">{worker.reputation}</td>
                    <td className="px-5 py-2 tabular-nums">{worker.jobs_completed}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>
      )}
      {adding && (
        <AddWorker
          open
          onClose={() => {
            setAdding(false);
            queryClient.invalidateQueries({ queryKey: MY_WORKERS_KEY });
          }}
        />
      )}
    </div>
  );
}
