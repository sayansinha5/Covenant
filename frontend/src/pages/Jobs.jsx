import { useState } from 'react';
import { Link } from 'react-router-dom';

import { Badge } from '../components/ui/Badge';
import { Card } from '../components/ui/Card';
import { Spinner } from '../components/ui/Spinner';
import { stateLabel, stateTone } from '../components/contracts/state';
import { formatMoney } from '../lib/format';
import { useContracts } from '../lib/queries';

const TABS = [
  { id: 'offers', label: 'Offers', states: ['sent_to_worker'] },
  { id: 'progress', label: 'In progress', states: ['in_progress'] },
  { id: 'delivered', label: 'Delivered', states: ['verifying', 'verdict_issued', 'under_appeal'] },
  {
    id: 'closed',
    label: 'Closed',
    states: ['settled', 'partially_settled', 'refunded', 'cancelled', 'expired', 'needs_attention'],
  },
];

export function Jobs() {
  const contracts = useContracts('provider');
  const [tab, setTab] = useState('offers');
  if (contracts.isLoading) return <Spinner />;
  const current = TABS.find((item) => item.id === tab);
  const items = (contracts.data?.items ?? []).filter((item) => current.states.includes(item.state));
  return (
    <div className="flex flex-col gap-4">
      <div className="flex gap-2">
        {TABS.map((item) => (
          <button
            key={item.id}
            type="button"
            className={`rounded-md px-3 py-1 transition-colors duration-200 ${tab === item.id ? 'bg-brand-subtle font-medium text-ink' : 'text-ink-muted hover:bg-wash hover:text-ink'}`}
            onClick={() => setTab(item.id)}
          >
            {item.label}
          </button>
        ))}
      </div>
      {items.length === 0 && <Card className="p-6 text-ink-muted">Nothing in this tab.</Card>}
      {items.map((item) => (
        <Card key={item.id} className="flex items-center justify-between p-4">
          <div>
            <Link to={`/contracts/${item.id}`} className="font-medium text-brand">
              {item.title}
            </Link>
            <p className="text-sm text-ink-muted">{formatMoney(item.amount, item.currency)}</p>
          </div>
          <Badge tone={stateTone(item.state)}>{stateLabel(item.state)}</Badge>
        </Card>
      ))}
    </div>
  );
}
