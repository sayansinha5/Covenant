import { Card } from '../components/ui/Card';
import { Spinner } from '../components/ui/Spinner';
import { Badge } from '../components/ui/Badge';
import { formatDateTime, formatMoney } from '../lib/format';
import { useEarnings } from '../lib/queries';

export function Earnings() {
  const earnings = useEarnings();
  if (earnings.isLoading) return <Spinner />;
  const data = earnings.data;
  return (
    <div className="flex flex-col gap-4">
      <div className="grid grid-cols-2 gap-4">
        <Card className="p-5">
          <p className="text-sm text-ink-muted">Paid out</p>
          <p className="text-2xl font-semibold tabular-nums">{formatMoney(data.paid)}</p>
        </Card>
        <Card className="p-5">
          <p className="text-sm text-ink-muted">Pending</p>
          <p className="text-2xl font-semibold tabular-nums">{formatMoney(data.pending)}</p>
        </Card>
      </div>
      <Card className="overflow-hidden">
        <table className="w-full text-left">
          <thead className="border-b border-line text-sm text-ink-muted">
            <tr>
              <th className="px-4 py-3 font-medium">When</th>
              <th className="px-4 py-3 font-medium">Net</th>
              <th className="px-4 py-3 font-medium">Status</th>
            </tr>
          </thead>
          <tbody>
            {(data.payouts ?? []).map((row) => (
              <tr key={row.id} className="border-b border-line last:border-0">
                <td className="px-4 py-3">{formatDateTime(row.created_at)}</td>
                <td className="px-4 py-3 tabular-nums">{formatMoney(row.net, row.currency)}</td>
                <td className="px-4 py-3">
                  <Badge tone={row.status === 'success' ? 'settled' : 'held'}>{row.status}</Badge>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {(data.payouts ?? []).length === 0 && <p className="p-4 text-ink-muted">No payouts yet.</p>}
      </Card>
    </div>
  );
}
