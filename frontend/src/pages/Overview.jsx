import { Link } from 'react-router-dom';
import { ArrowRight } from 'lucide-react';

import { useAuth } from '../auth/context';
import { stateLabel, stateTone } from '../components/contracts/state';
import { Badge } from '../components/ui/Badge';
import { Card } from '../components/ui/Card';
import { Spinner } from '../components/ui/Spinner';
import { cn } from '../lib/cn';
import { formatDateTime, formatMoney } from '../lib/format';
import { useApprovals, useContracts, useOverview } from '../lib/queries';

const GROUPS = [
  {
    id: 'needs',
    label: 'Needs you',
    color: 'var(--color-held)',
    bar: 'bg-held',
    states: [
      'awaiting_approval',
      'awaiting_agreement',
      'verdict_issued',
      'under_appeal',
      'needs_attention',
    ],
  },
  {
    id: 'progress',
    label: 'In progress',
    color: 'var(--color-brand)',
    bar: 'bg-brand',
    states: [
      'draft',
      'funding',
      'funded',
      'sent_to_worker',
      'in_progress',
      'verifying',
      'settling',
    ],
  },
  {
    id: 'settled',
    label: 'Settled',
    color: 'var(--color-settled)',
    bar: 'bg-settled',
    states: ['settled', 'partially_settled'],
  },
  {
    id: 'closed',
    label: 'Closed',
    color: 'var(--color-released)',
    bar: 'bg-released',
    states: ['cancelled', 'expired', 'refunded'],
  },
];

export function Overview() {
  const { user } = useAuth();
  const org = user.membership.organization;
  const overview = useOverview();
  const contracts = useContracts();
  const approvals = useApprovals({ enabled: org.can_hire });
  const stats = overview.data ?? {
    by_state: {},
    currently_held: '0.00',
    captured_this_month: '0.00',
  };
  const groups = groupCounts(stats.by_state);
  const total = groups.reduce((sum, group) => sum + group.count, 0);
  const moving = groups
    .filter((group) => group.id === 'needs' || group.id === 'progress')
    .reduce((sum, group) => sum + group.count, 0);
  const pending = (approvals.data ?? []).filter((item) => item.status === 'pending');
  const recent = [...(contracts.data?.items ?? [])]
    .sort((a, b) => new Date(b.updated_at) - new Date(a.updated_at))
    .slice(0, 5);

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-sm text-ink-muted">{org.name}</p>
          <h2 className="mt-1 text-2xl font-semibold tracking-tight">Where the work stands</h2>
        </div>
        {org.can_hire && (
          <Link
            to="/assistant"
            className="inline-flex items-center gap-1.5 text-sm font-medium text-brand hover:text-brand-hover"
          >
            Open assistant
            <ArrowRight size={16} strokeWidth={1.5} aria-hidden="true" />
          </Link>
        )}
      </header>

      {overview.isLoading ? (
        <Spinner />
      ) : (
        <>
          <div className="grid gap-4 sm:grid-cols-3">
            <Stat label="Held right now" value={formatMoney(stats.currently_held)} tone="held" />
            <Stat
              label="Captured this month"
              value={formatMoney(stats.captured_this_month)}
              tone="settled"
            />
            <Stat
              label="Still moving"
              value={String(moving)}
              tone="brand"
              hint="Waiting or in progress"
            />
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            <Card className="p-5">
              <h3 className="font-semibold tracking-tight">What's going on</h3>
              <p className="mt-1 text-sm text-ink-muted">Contracts by where they sit.</p>
              <div className="mt-5 flex flex-col items-center gap-6 sm:flex-row sm:items-center">
                <Donut total={total} groups={groups} />
                <ul className="flex w-full flex-col gap-3">
                  {groups.map((group) => (
                    <li key={group.id} className="flex items-center gap-3">
                      <span className={cn('size-2.5 shrink-0 rounded-full', group.bar)} />
                      <span className="min-w-0 flex-1 text-sm">{group.label}</span>
                      <span className="text-sm font-medium tabular-nums">{group.count}</span>
                    </li>
                  ))}
                </ul>
              </div>
            </Card>

            <Card className="p-5">
              <h3 className="font-semibold tracking-tight">Money</h3>
              <p className="mt-1 text-sm text-ink-muted">
                Held against what was captured this month.
              </p>
              <MoneyBars held={stats.currently_held} captured={stats.captured_this_month} />
            </Card>
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            {org.can_hire && (
              <Card className="flex flex-col p-5">
                <div className="flex items-center justify-between gap-3">
                  <h3 className="font-semibold tracking-tight">To approve</h3>
                  <Link
                    to="/approvals"
                    className="text-sm font-medium text-brand hover:text-brand-hover"
                  >
                    All approvals
                  </Link>
                </div>
                {approvals.isLoading ? (
                  <Spinner className="mt-6" />
                ) : pending.length === 0 ? (
                  <p className="mt-4 text-sm text-ink-muted">Nothing is waiting on you.</p>
                ) : (
                  <ul className="mt-4 flex flex-col divide-y divide-line">
                    {pending.slice(0, 5).map((item) => (
                      <li key={item.id} className="py-3 first:pt-0 last:pb-0">
                        <Link
                          to={`/contracts/${item.contract_id}`}
                          className="font-medium text-brand hover:text-brand-hover"
                        >
                          {item.reason}
                        </Link>
                        <p className="mt-0.5 text-sm text-ink-muted">
                          Waiting until {formatDateTime(item.expires_at)}
                        </p>
                      </li>
                    ))}
                  </ul>
                )}
                {pending.length > 5 && (
                  <p className="mt-3 text-sm text-ink-muted">Showing 5 of {pending.length}.</p>
                )}
              </Card>
            )}

            <Card className="flex flex-col p-5">
              <div className="flex items-center justify-between gap-3">
                <h3 className="font-semibold tracking-tight">Latest contracts</h3>
                <Link
                  to="/contracts"
                  className="text-sm font-medium text-brand hover:text-brand-hover"
                >
                  All contracts
                </Link>
              </div>
              {contracts.isLoading ? (
                <Spinner className="mt-6" />
              ) : recent.length === 0 ? (
                <p className="mt-4 text-sm text-ink-muted">No contracts yet.</p>
              ) : (
                <ul className="mt-4 flex flex-col divide-y divide-line">
                  {recent.map((item) => (
                    <li
                      key={item.id}
                      className="flex items-center justify-between gap-3 py-3 first:pt-0 last:pb-0"
                    >
                      <div className="min-w-0">
                        <Link
                          to={`/contracts/${item.id}`}
                          className="block truncate font-medium text-brand hover:text-brand-hover"
                        >
                          {item.title || item.number}
                        </Link>
                        <p className="truncate text-sm text-ink-muted">
                          {item.number} · {item.worker_name}
                        </p>
                      </div>
                      <div className="flex shrink-0 flex-col items-end gap-1">
                        <span className="text-sm tabular-nums">
                          {formatMoney(item.amount, item.currency)}
                        </span>
                        <Badge tone={stateTone(item.state)}>
                          {titleCase(stateLabel(item.state))}
                        </Badge>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
          </div>
        </>
      )}
    </div>
  );
}

function Stat({ label, value, hint, tone }) {
  return (
    <Card className="p-5">
      <p className="text-xs font-medium tracking-[0.12em] text-ink-muted uppercase">{label}</p>
      <p
        className={cn(
          'mt-3 text-3xl font-semibold tracking-tight tabular-nums',
          tone === 'held' && 'text-held',
          tone === 'settled' && 'text-settled',
          tone === 'brand' && 'text-brand',
        )}
      >
        {value}
      </p>
      {hint && <p className="mt-1 text-sm text-ink-muted">{hint}</p>}
    </Card>
  );
}

function Donut({ total, groups }) {
  const r = 46;
  const c = 2 * Math.PI * r;
  const gap = groups.filter((group) => group.count > 0).length > 1 ? 4 : 0;
  let cursor = 0;
  const arcs =
    total === 0
      ? []
      : groups
          .filter((group) => group.count > 0)
          .map((group) => {
            const length = Math.max((group.count / total) * c - gap, 1);
            const arc = { ...group, length, rest: c - length, offset: cursor };
            cursor += length + gap;
            return arc;
          });

  return (
    <svg
      viewBox="0 0 120 120"
      className="size-36 shrink-0"
      role="img"
      aria-label={`${total} contracts`}
    >
      <circle cx="60" cy="60" r={r} fill="none" stroke="var(--color-wash)" strokeWidth="14" />
      {arcs.map((arc) => (
        <circle
          key={arc.id}
          cx="60"
          cy="60"
          r={r}
          fill="none"
          stroke={arc.color}
          strokeWidth="14"
          strokeDasharray={`${arc.length} ${arc.rest}`}
          strokeDashoffset={-arc.offset}
          transform="rotate(-90 60 60)"
        />
      ))}
      <text
        x="60"
        y="56"
        textAnchor="middle"
        fill="var(--color-ink)"
        fontSize="22"
        fontWeight="600"
      >
        {total}
      </text>
      <text x="60" y="72" textAnchor="middle" fill="var(--color-ink-muted)" fontSize="10">
        contracts
      </text>
    </svg>
  );
}

function MoneyBars({ held, captured }) {
  const rows = [
    { label: 'Held right now', amount: held, value: Number(held) || 0, bar: 'bg-held' },
    {
      label: 'Captured this month',
      amount: captured,
      value: Number(captured) || 0,
      bar: 'bg-settled',
    },
  ];
  const max = Math.max(...rows.map((row) => row.value), 1);
  const empty = rows.every((row) => row.value === 0);
  return (
    <div className="mt-6 flex flex-col gap-5">
      {rows.map((row) => (
        <div key={row.label}>
          <div className="flex items-baseline justify-between gap-3">
            <span className="text-sm">{row.label}</span>
            <span className="text-sm font-medium tabular-nums">{formatMoney(row.amount)}</span>
          </div>
          <div className="mt-2 h-2.5 overflow-hidden rounded-full bg-wash">
            <div
              className={cn('h-full rounded-full', row.bar)}
              style={{ width: empty ? '0%' : `${Math.max((row.value / max) * 100, 4)}%` }}
            />
          </div>
        </div>
      ))}
      {empty && <p className="text-sm text-ink-muted">No money is held or captured yet.</p>}
    </div>
  );
}

function groupCounts(byState) {
  const known = new Set(GROUPS.flatMap((group) => group.states));
  return GROUPS.map((group) => {
    const extra =
      group.id === 'progress' ? Object.entries(byState).filter(([state]) => !known.has(state)) : [];
    const count =
      group.states.reduce((sum, state) => sum + (byState[state] ?? 0), 0) +
      extra.reduce((sum, [, count]) => sum + count, 0);
    return { ...group, count };
  });
}

function titleCase(label) {
  return label ? label.charAt(0).toUpperCase() + label.slice(1) : '';
}
