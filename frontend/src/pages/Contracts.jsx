import { Link } from 'react-router-dom';

import { Badge } from '../components/ui/Badge';
import { Card } from '../components/ui/Card';
import { Spinner } from '../components/ui/Spinner';
import { formatMoney } from '../lib/format';
import { useContracts } from '../lib/queries';
import { stateLabel, stateTone } from '../components/contracts/state';

export function Contracts() {
  const contracts = useContracts();
  if (contracts.isLoading) return <Spinner />;
  const items = contracts.data?.items ?? [];
  if (items.length === 0) {
    return (
      <Card className="p-6 text-ink-muted">
        No contracts yet. Ask your assistant, or{' '}
        <Link to="/find-workers" className="text-brand">
          find a worker
        </Link>
        .
      </Card>
    );
  }
  return (
    <Card className="overflow-hidden">
      <table className="w-full text-left text-base">
        <thead className="border-b border-line text-sm text-ink-muted">
          <tr>
            <th className="px-4 py-3 font-medium">Contract</th>
            <th className="px-4 py-3 font-medium">Worker</th>
            <th className="px-4 py-3 font-medium">Amount</th>
            <th className="px-4 py-3 font-medium">State</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr key={item.id} className="border-b border-line last:border-0">
              <td className="px-4 py-3">
                <Link to={`/contracts/${item.id}`} className="font-medium text-brand">
                  {item.number}
                </Link>
                <div className="text-sm text-ink-muted">{item.title}</div>
              </td>
              <td className="px-4 py-3">{item.worker_name}</td>
              <td className="px-4 py-3 tabular-nums">{formatMoney(item.amount, item.currency)}</td>
              <td className="px-4 py-3">
                <Badge tone={stateTone(item.state)}>{stateLabel(item.state)}</Badge>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  );
}
