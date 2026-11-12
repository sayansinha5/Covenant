import { Link } from 'react-router-dom';

import { useAuth } from '../auth/context';
import { Alert } from '../components/ui/Alert';
import { Badge } from '../components/ui/Badge';
import { Card } from '../components/ui/Card';
import { Spinner } from '../components/ui/Spinner';
import { labelOf } from '../lib/admin';
import { problemOf } from '../lib/api';
import { useFleet } from '../lib/queries';

const FLEET_LABEL = {
  running: 'Governed and running',
  published: 'Published, not running',
  absent: 'Not on the fleet',
};

const FLEET_TONE = {
  running: 'settled',
  published: 'held',
  absent: 'released',
};

function statusTone(status) {
  if (status === 'running') return 'settled';
  if (status === 'error') return 'danger';
  if (status === 'pending' || status === 'deploying') return 'held';
  return 'released';
}

function Series({ values }) {
  if (!values?.length) return <span className="text-xs text-ink-muted">No recent requests</span>;
  const peak = Math.max(...values, 1);
  return (
    <span className="flex h-8 items-end gap-0.5" aria-hidden="true">
      {values.map((value, index) => (
        <span
          key={`${index}-${value}`}
          className="w-1.5 rounded-sm bg-brand"
          style={{ height: `${Math.max(12, (value / peak) * 100)}%` }}
        />
      ))}
    </span>
  );
}

export function Fleet() {
  const fleet = useFleet();
  const { user } = useAuth();
  const canHire = user?.membership?.organization?.can_hire;

  if (fleet.isLoading) return <Spinner />;
  if (fleet.isError) return <Alert tone="danger">{problemOf(fleet.error).detail}</Alert>;

  const data = fleet.data;
  return (
    <div className="flex flex-col gap-4">
      <p className="max-w-2xl text-sm text-ink-muted">
        Before money is held for an agent, check that a deployment with the same name is running and
        what the account has already spent. A worker named Lipi lines up with a deployment named
        lipi.
      </p>
      {data.detail && <Alert tone={data.configured ? 'danger' : 'info'}>{data.detail}</Alert>}
      {data.account && (
        <p className="text-sm">
          Account <span className="font-medium">{data.account}</span>
        </p>
      )}
      {data.meters.length > 0 && (
        <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {data.meters.map((meter) => (
            <li key={meter.name}>
              <Card className="p-4">
                <p className="text-xs text-ink-muted">{labelOf(meter.name)}</p>
                <p className="mt-1 text-lg font-semibold tabular-nums">
                  {meter.usage.toLocaleString('en-US')}
                  {meter.quota != null && (
                    <span className="text-sm font-normal text-ink-muted">
                      {' '}
                      / {meter.quota.toLocaleString('en-US')}
                    </span>
                  )}
                </p>
              </Card>
            </li>
          ))}
        </ul>
      )}
      {(data.deployments.length > 0 || (data.configured && !data.detail)) && (
        <section className="flex flex-col gap-2">
          <h2 className="text-base font-semibold">Deployments</h2>
          {data.deployments.length === 0 ? (
            <Card className="p-4 text-sm text-ink-muted">No deployments on this account.</Card>
          ) : (
            <ul className="grid gap-3 md:grid-cols-2">
              {data.deployments.map((deployment) => (
                <li key={deployment.id}>
                  <Card className="flex h-full flex-col gap-2 p-4">
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <p className="font-medium">{deployment.display_name || deployment.name}</p>
                        <p className="text-xs text-ink-muted">
                          {deployment.environment || 'default environment'}
                        </p>
                      </div>
                      <Badge tone={statusTone(deployment.status)}>
                        {labelOf(deployment.status)}
                      </Badge>
                    </div>
                    <Series values={deployment.requests_recent} />
                    {deployment.matched_worker_name && (
                      <p className="text-sm">
                        Matches{' '}
                        {canHire ? (
                          <Link
                            to={`/find-workers?worker=${deployment.matched_worker_id}`}
                            className="text-brand"
                          >
                            {deployment.matched_worker_name}
                          </Link>
                        ) : (
                          <Link to="/workers" className="text-brand">
                            {deployment.matched_worker_name}
                          </Link>
                        )}
                      </p>
                    )}
                    {deployment.url && (
                      <a
                        href={deployment.url}
                        target="_blank"
                        rel="noreferrer"
                        className="text-sm text-brand"
                      >
                        Open deployment
                      </a>
                    )}
                  </Card>
                </li>
              ))}
            </ul>
          )}
        </section>
      )}
      {data.workers.length > 0 && (
        <section className="flex flex-col gap-2">
          <h2 className="text-base font-semibold">Your workers</h2>
          <Card className="overflow-hidden">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-line text-ink-muted">
                <tr>
                  <th className="px-4 py-3 font-medium">Worker</th>
                  <th className="px-4 py-3 font-medium">Here</th>
                  <th className="px-4 py-3 font-medium">On the fleet</th>
                </tr>
              </thead>
              <tbody>
                {data.workers.map((worker) => (
                  <tr key={worker.id} className="border-b border-line last:border-0">
                    <td className="px-4 py-3 font-medium">{worker.name}</td>
                    <td className="px-4 py-3">{labelOf(worker.status)}</td>
                    <td className="px-4 py-3">
                      <Badge tone={FLEET_TONE[worker.fleet_status]}>
                        {FLEET_LABEL[worker.fleet_status]}
                      </Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        </section>
      )}
      <p className="text-xs text-ink-muted">Agent fleet · Astropods</p>
    </div>
  );
}
