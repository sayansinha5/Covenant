import { useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';

import { Alert } from '../../components/ui/Alert';
import { Badge } from '../../components/ui/Badge';
import { Button } from '../../components/ui/Button';
import { Card } from '../../components/ui/Card';
import { Spinner } from '../../components/ui/Spinner';
import { useToast } from '../../components/ui/toast-context';
import { isRunActive, labelOf, resultTone, webhookStatus, workerTone } from '../../lib/admin';
import { api, problemOf } from '../../lib/api';
import { cn } from '../../lib/cn';
import { formatDateTime, formatMoney } from '../../lib/format';
import {
  ADMIN_WORKERS_KEY,
  LAST_RECONCILIATION_KEY,
  useAdminWorkers,
  useLastReconciliation,
  useWebhookEvents,
} from '../../lib/queries';
import { ModerationDialog } from './ModerationDialog';

const TABS = [
  { id: 'workers', label: 'Workers' },
  { id: 'webhooks', label: 'Webhook events' },
  { id: 'reconciliation', label: 'Reconciliation' },
];

const CELL = 'px-5 py-2';
const HEAD = `${CELL} font-medium`;

function ContractLink({ id, number }) {
  if (!id) return <span className="text-ink-muted">None</span>;
  return (
    <Link to={`/contracts/${id}`} className="text-brand hover:underline">
      {number ?? 'Contract'}
    </Link>
  );
}

function Pager({ data, page, onPage }) {
  const pages = Math.max(1, Math.ceil(data.total / data.page_size));
  if (pages === 1) return null;
  return (
    <div className="flex items-center justify-end gap-3 border-t border-line px-5 py-3 text-sm">
      <span className="text-ink-muted tabular-nums">
        Page {page} of {pages}
      </span>
      <Button variant="secondary" size="sm" disabled={page <= 1} onClick={() => onPage(page - 1)}>
        Previous
      </Button>
      <Button
        variant="secondary"
        size="sm"
        disabled={page >= pages}
        onClick={() => onPage(page + 1)}
      >
        Next
      </Button>
    </div>
  );
}

function Loaded({ query, children }) {
  if (query.isPending) return <Spinner className="text-ink-muted" />;
  if (query.isError) return <Alert tone="danger">{problemOf(query.error).detail}</Alert>;
  return children(query.data);
}

function WorkersTab() {
  const [page, setPage] = useState(1);
  const [moderating, setModerating] = useState(null);
  const workers = useAdminWorkers(page);
  const queryClient = useQueryClient();
  const toast = useToast();

  async function handleDone(worker) {
    setModerating(null);
    await queryClient.invalidateQueries({ queryKey: ADMIN_WORKERS_KEY });
    toast(`${worker.display_name} is now ${labelOf(worker.status).toLowerCase()}.`);
  }

  return (
    <Loaded query={workers}>
      {(data) => (
        <Card as="section" className="overflow-hidden">
          {data.items.length === 0 ? (
            <p className="px-5 py-4 text-ink-muted">No workers registered yet.</p>
          ) : (
            <table className="w-full text-sm">
              <thead className="text-left text-ink-muted">
                <tr className="border-b border-line">
                  <th className={HEAD}>Worker</th>
                  <th className={HEAD}>Provider</th>
                  <th className={HEAD}>Kind</th>
                  <th className={cn(HEAD, 'text-right')}>Price</th>
                  <th className={cn(HEAD, 'text-right')}>Reputation</th>
                  <th className={HEAD}>Status</th>
                  <th className={HEAD}>
                    <span className="sr-only">Actions</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((w) => (
                  <tr key={w.id} className="border-b border-line align-top last:border-0">
                    <td className={CELL}>
                      <div className="font-medium">{w.display_name}</div>
                      {w.base_url && <div className="text-ink-muted">{w.base_url}</div>}
                    </td>
                    <td className={CELL}>{w.org_name}</td>
                    <td className={CELL}>{labelOf(w.kind)}</td>
                    <td className={cn(CELL, 'text-right tabular-nums')}>
                      {formatMoney(w.price, w.currency)}
                    </td>
                    <td className={cn(CELL, 'text-right tabular-nums')}>{w.reputation}</td>
                    <td className={CELL}>
                      <Badge tone={workerTone(w.status)}>{labelOf(w.status)}</Badge>
                      {w.suspended_reason && (
                        <div className="mt-1 text-ink-muted">{w.suspended_reason}</div>
                      )}
                    </td>
                    <td className={cn(CELL, 'text-right')}>
                      {w.status === 'suspended' ? (
                        <Button
                          variant="secondary"
                          size="sm"
                          onClick={() => setModerating({ worker: w, action: 'reinstate' })}
                        >
                          Reinstate
                        </Button>
                      ) : (
                        <Button
                          variant="secondary"
                          size="sm"
                          onClick={() => setModerating({ worker: w, action: 'suspend' })}
                        >
                          Suspend
                        </Button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <Pager data={data} page={page} onPage={setPage} />
          <ModerationDialog
            worker={moderating?.worker}
            action={moderating?.action}
            onDone={handleDone}
            onClose={() => setModerating(null)}
          />
        </Card>
      )}
    </Loaded>
  );
}

function WebhooksTab() {
  const [page, setPage] = useState(1);
  const events = useWebhookEvents(page);
  return (
    <Loaded query={events}>
      {(data) => (
        <Card as="section" className="overflow-hidden">
          {data.items.length === 0 ? (
            <p className="px-5 py-4 text-ink-muted">No webhook deliveries received yet.</p>
          ) : (
            <table className="w-full text-sm">
              <thead className="text-left text-ink-muted">
                <tr className="border-b border-line">
                  <th className={HEAD}>Received</th>
                  <th className={HEAD}>Event</th>
                  <th className={HEAD}>Verified</th>
                  <th className={HEAD}>Status</th>
                  <th className={HEAD}>Outcome</th>
                  <th className={HEAD}>Contract</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((e) => {
                  const status = webhookStatus(e);
                  return (
                    <tr key={e.id} className="border-b border-line align-top last:border-0">
                      <td className={cn(CELL, 'whitespace-nowrap')}>
                        {formatDateTime(e.received_at)}
                      </td>
                      <td className={CELL}>
                        <div className="font-medium">{e.event_type}</div>
                        <div className="text-ink-muted">
                          {e.paypal_event_id ?? e.claimed_event_id}
                        </div>
                      </td>
                      <td className={CELL}>{e.verified ? 'Yes' : 'No'}</td>
                      <td className={CELL}>
                        <Badge tone={status.tone}>{status.label}</Badge>
                      </td>
                      <td className={cn(CELL, 'text-ink-muted')}>{e.error ?? e.outcome}</td>
                      <td className={CELL}>
                        <ContractLink id={e.contract_id} number={e.contract_number} />
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
          <Pager data={data} page={page} onPage={setPage} />
        </Card>
      )}
    </Loaded>
  );
}

function Count({ label, value }) {
  return (
    <div className="flex flex-col gap-1">
      <dt className="text-sm text-ink-muted">{label}</dt>
      <dd className="text-lg font-semibold tabular-nums">{value}</dd>
    </div>
  );
}

function RunSummary({ run }) {
  const when = run.finished_at ?? run.started_at ?? run.created_at;
  return (
    <div className="flex flex-col gap-5">
      <p className="text-sm text-ink-muted">
        {labelOf(run.status)}, {run.trigger === 'admin' ? 'started by an admin' : 'scheduled'},{' '}
        {formatDateTime(when)}.
      </p>
      <dl className="grid grid-cols-5 gap-4">
        <Count label="Checked" value={run.checked} />
        <Count label="In sync" value={run.in_sync} />
        <Count label="Fixed" value={run.fixed} />
        <Count label="Needs attention" value={run.needs_attention} />
        <Count label="Errors" value={run.errors} />
      </dl>
      {run.findings.length > 0 && (
        <ul className="flex flex-col divide-y divide-line rounded-md border border-line text-sm">
          {run.findings.map((f, index) => (
            <li key={`${f.subject}-${index}`} className="flex items-start gap-3 px-4 py-2">
              <Badge tone={resultTone(f.result)}>{labelOf(f.result)}</Badge>
              <span className="flex-1">{f.message}</span>
              {f.contract_id && <ContractLink id={f.contract_id} number={f.contract_number} />}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function ReconciliationTab() {
  const last = useLastReconciliation();
  const queryClient = useQueryClient();
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState(null);
  const running = isRunActive(last.data);

  async function start() {
    setStarting(true);
    setError(null);
    try {
      const { data } = await api.post('/admin/reconcile');
      queryClient.setQueryData(LAST_RECONCILIATION_KEY, data);
    } catch (failure) {
      setError(problemOf(failure).detail);
    } finally {
      setStarting(false);
    }
  }

  return (
    <Card as="section" className="flex flex-col gap-5 p-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold">Last run</h2>
          <p className="text-sm text-ink-muted">
            Compares open holds and payouts with PayPal every 5 minutes and applies safe fixes.
          </p>
        </div>
        <Button onClick={start} loading={starting || running} loadingText="Running…">
          Run reconciliation now
        </Button>
      </div>
      {error && <Alert tone="danger">{error}</Alert>}
      <Loaded query={last}>
        {(run) => (run ? <RunSummary run={run} /> : <p className="text-ink-muted">No run yet.</p>)}
      </Loaded>
    </Card>
  );
}

const PANELS = { workers: WorkersTab, webhooks: WebhooksTab, reconciliation: ReconciliationTab };

/** S17: worker moderation, the webhook log and reconciliation, for platform admins only. */
export function Admin() {
  const [tab, setTab] = useState('workers');
  const Panel = PANELS[tab];
  return (
    <div className="flex flex-col gap-6">
      <div role="tablist" aria-label="Admin sections" className="flex gap-1 border-b border-line">
        {TABS.map((t) => (
          <button
            key={t.id}
            id={`admin-tab-${t.id}`}
            type="button"
            role="tab"
            aria-selected={tab === t.id}
            aria-controls="admin-panel"
            onClick={() => setTab(t.id)}
            className={cn(
              '-mb-px border-b-2 px-4 py-2 text-sm font-medium',
              tab === t.id
                ? 'border-brand text-ink'
                : 'border-transparent text-ink-muted hover:text-ink',
            )}
          >
            {t.label}
          </button>
        ))}
      </div>
      <div id="admin-panel" role="tabpanel" aria-labelledby={`admin-tab-${tab}`}>
        <Panel />
      </div>
    </div>
  );
}
