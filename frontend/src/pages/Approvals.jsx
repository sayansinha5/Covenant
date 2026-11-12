import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';

import { useAuth } from '../auth/context';
import { Alert } from '../components/ui/Alert';
import { Button } from '../components/ui/Button';
import { Card } from '../components/ui/Card';
import { Spinner } from '../components/ui/Spinner';
import { api, problemOf } from '../lib/api';
import { formatDateTime } from '../lib/format';
import { APPROVALS_KEY, useApprovals } from '../lib/queries';

export function Approvals() {
  const approvals = useApprovals();
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [error, setError] = useState('');
  const canDecide = ['owner', 'admin'].includes(user.membership.role);
  if (approvals.isLoading) return <Spinner />;
  const items = approvals.data ?? [];

  async function decide(id, approve) {
    setError('');
    try {
      await api.post(`/approvals/${id}/${approve ? 'approve' : 'reject'}`);
      await queryClient.invalidateQueries({ queryKey: APPROVALS_KEY });
    } catch (err) {
      setError(problemOf(err).detail);
    }
  }

  return (
    <div className="flex flex-col gap-3">
      {error && <Alert tone="danger">{error}</Alert>}
      {items.length === 0 && <Card className="p-6 text-ink-muted">No approval requests.</Card>}
      {items.map((item) => (
        <Card key={item.id} className="flex items-center justify-between gap-4 p-4">
          <div>
            <Link to={`/contracts/${item.contract_id}`} className="font-medium text-brand">
              {item.reason}
            </Link>
            <p className="text-sm text-ink-muted">
              {item.status} · until {formatDateTime(item.expires_at)}
            </p>
          </div>
          {canDecide && item.status === 'pending' && (
            <div className="flex gap-2">
              <Button onClick={() => void decide(item.id, true)}>Approve</Button>
              <Button variant="secondary" onClick={() => void decide(item.id, false)}>
                Reject
              </Button>
            </div>
          )}
        </Card>
      ))}
    </div>
  );
}
