import { useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';

import { useAuth } from '../auth/context';
import { MandateForm } from '../components/mandate/MandateForm';
import { SignMandateDialog } from '../components/mandate/SignMandateDialog';
import { Alert } from '../components/ui/Alert';
import { Badge } from '../components/ui/Badge';
import { Button } from '../components/ui/Button';
import { Card } from '../components/ui/Card';
import { Spinner } from '../components/ui/Spinner';
import { useToast } from '../components/ui/toast-context';
import { problemOf } from '../lib/api';
import { formatDateTime, formatMoney } from '../lib/format';
import { MANDATE_KEY, useMandate, useMandateVersions } from '../lib/queries';

function Term({ label, value }) {
  return (
    <div className="flex flex-col gap-1">
      <dt className="text-sm text-ink-muted">{label}</dt>
      <dd className="text-lg font-semibold tabular-nums">{value}</dd>
    </div>
  );
}

function labelsFor(values, workTypes) {
  return workTypes.filter((t) => values.includes(t.value)).map((t) => t.label);
}

function ActiveMandate({ mandate, workTypes }) {
  const blocked = workTypes.filter((t) => !mandate.allowed_work_types.includes(t.value));
  return (
    <div className="flex flex-col gap-5">
      <dl className="grid grid-cols-3 gap-4">
        <Term
          label="Monthly budget"
          value={formatMoney(mandate.monthly_budget, mandate.currency)}
        />
        <Term
          label="Maximum per task"
          value={formatMoney(mandate.per_task_cap, mandate.currency)}
        />
        <Term
          label="Ask me first above"
          value={formatMoney(mandate.approval_threshold, mandate.currency)}
        />
      </dl>
      <dl className="grid grid-cols-2 gap-4 text-base">
        <div>
          <dt className="text-sm text-ink-muted">Allowed work types</dt>
          <dd>{labelsFor(mandate.allowed_work_types, workTypes).join(', ')}</dd>
        </div>
        <div>
          <dt className="text-sm text-ink-muted">Blocked work types</dt>
          <dd>{blocked.length ? blocked.map((t) => t.label).join(', ') : 'None'}</dd>
        </div>
      </dl>
    </div>
  );
}

function VersionHistory({ workTypes }) {
  const versions = useMandateVersions();
  if (versions.isPending) return <Spinner className="text-ink-muted" />;
  if (versions.isError) return <Alert tone="danger">{problemOf(versions.error).detail}</Alert>;
  return (
    <Card as="section" className="overflow-hidden">
      <h2 className="border-b border-line px-5 py-3 text-lg font-semibold">History</h2>
      <table className="w-full text-sm">
        <thead className="text-left text-ink-muted">
          <tr className="border-b border-line">
            <th className="px-5 py-2 font-medium">Version</th>
            <th className="px-5 py-2 font-medium">Signed</th>
            <th className="px-5 py-2 font-medium">By</th>
            <th className="px-5 py-2 text-right font-medium">Budget</th>
            <th className="px-5 py-2 text-right font-medium">Per task</th>
            <th className="px-5 py-2 text-right font-medium">Approval above</th>
            <th className="px-5 py-2 font-medium">Work types</th>
          </tr>
        </thead>
        <tbody>
          {versions.data.map((v) => (
            <tr key={v.id} className="border-b border-line last:border-0">
              <td className="px-5 py-2 tabular-nums">
                v{v.version} {v.is_active && <Badge tone="settled">Active</Badge>}
              </td>
              <td className="px-5 py-2">{formatDateTime(v.signed_at)}</td>
              <td className="px-5 py-2">{v.signed_by_name}</td>
              <td className="px-5 py-2 text-right tabular-nums">{formatMoney(v.monthly_budget)}</td>
              <td className="px-5 py-2 text-right tabular-nums">{formatMoney(v.per_task_cap)}</td>
              <td className="px-5 py-2 text-right tabular-nums">
                {formatMoney(v.approval_threshold)}
              </td>
              <td className="px-5 py-2">{labelsFor(v.allowed_work_types, workTypes).join(', ')}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  );
}

/** S12: the active mandate, signing a new version (owners only) and the version history. */
export function Mandate() {
  const { user } = useAuth();
  const toast = useToast();
  const queryClient = useQueryClient();
  const mandate = useMandate();
  const [editing, setEditing] = useState(false);
  const [pending, setPending] = useState(null);
  const organization = user.membership.organization;
  const isOwner = user.membership.role === 'owner';

  if (mandate.isPending) return <Spinner className="text-ink-muted" />;
  if (mandate.isError) return <Alert tone="danger">{problemOf(mandate.error).detail}</Alert>;
  const { active, defaults, work_types: workTypes } = mandate.data;

  async function handleSigned(signed) {
    setPending(null);
    setEditing(false);
    await queryClient.invalidateQueries({ queryKey: MANDATE_KEY });
    toast(`Mandate v${signed.version} signed.`);
  }

  return (
    <div className="flex flex-col gap-6">
      <Card as="section" className="p-5">
        <div className="mb-5 flex items-start justify-between gap-4">
          <div>
            <h2 className="text-lg font-semibold">
              {active ? `Version ${active.version}` : 'No mandate signed'}
            </h2>
            <p className="text-sm text-ink-muted">
              {active
                ? `Signed ${formatDateTime(active.signed_at)} by ${active.signed_by_name}. ` +
                  'Contracts keep the version they were funded under.'
                : `${organization.assistant_name} can't fund anything until an owner signs one.`}
            </p>
          </div>
          {isOwner && !editing && (
            <Button variant={active ? 'secondary' : 'primary'} onClick={() => setEditing(true)}>
              {active ? 'Edit mandate' : 'Sign mandate'}
            </Button>
          )}
        </div>
        {editing ? (
          <MandateForm
            initial={active ?? defaults}
            workTypes={workTypes}
            submitLabel="Sign new version"
            onSubmit={setPending}
            onCancel={() => setEditing(false)}
          />
        ) : (
          active && <ActiveMandate mandate={active} workTypes={workTypes} />
        )}
      </Card>
      {active && <VersionHistory workTypes={workTypes} />}
      <SignMandateDialog
        terms={pending}
        assistantName={organization.assistant_name}
        onClose={() => setPending(null)}
        onSigned={handleSigned}
      />
    </div>
  );
}
