import { useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';

import { useAuth } from '../auth/context';
import { PayPalFundingCard } from '../components/paypal/PayPalFundingCard';
import { Alert } from '../components/ui/Alert';
import { Button } from '../components/ui/Button';
import { Card } from '../components/ui/Card';
import { ConfirmDialog } from '../components/ui/ConfirmDialog';
import { Field, TextInput } from '../components/ui/Field';
import { api, problemOf } from '../lib/api';
import { API_KEYS_KEY, useApiKeys } from '../lib/queries';

export function Settings() {
  const { user, reloadUser } = useAuth();
  const org = user.membership.organization;
  const keys = useApiKeys();
  const queryClient = useQueryClient();
  const [name, setName] = useState('');
  const [created, setCreated] = useState('');
  const [payout, setPayout] = useState(org.payout_email ?? '');
  const [confirmPayout, setConfirmPayout] = useState(false);
  const [removingPayout, setRemovingPayout] = useState(false);
  const [payoutError, setPayoutError] = useState('');
  const [error, setError] = useState('');
  const canManage = ['owner', 'admin'].includes(user.membership.role);

  async function savePayout(event) {
    event.preventDefault();
    setError('');
    try {
      await api.patch('/orgs/current', { payout_email: payout });
      await reloadUser();
    } catch (err) {
      setError(problemOf(err).detail);
    }
  }

  async function removePayout() {
    setRemovingPayout(true);
    setPayoutError('');
    try {
      await api.patch('/orgs/current', { payout_email: null });
      setPayout('');
      setConfirmPayout(false);
      await reloadUser();
    } catch (err) {
      setPayoutError(problemOf(err).detail);
    } finally {
      setRemovingPayout(false);
    }
  }

  async function createKey(event) {
    event.preventDefault();
    setError('');
    try {
      const response = await api.post('/api-keys', { name });
      setCreated(response.data.key);
      setName('');
      await queryClient.invalidateQueries({ queryKey: API_KEYS_KEY });
    } catch (err) {
      setError(problemOf(err).detail);
    }
  }

  async function revoke(id) {
    await api.delete(`/api-keys/${id}`);
    await queryClient.invalidateQueries({ queryKey: API_KEYS_KEY });
  }

  return (
    <div className="flex max-w-2xl flex-col gap-4">
      {error && <Alert tone="danger">{error}</Alert>}
      {org.can_hire && <PayPalFundingCard returnPath="/settings" canDisconnect={canManage} />}
      <Card className="flex flex-col gap-3 p-5">
        <h2 className="font-semibold">Payout email</h2>
        <form className="flex flex-col gap-3" onSubmit={(event) => void savePayout(event)}>
          <Field
            id="payout-email"
            label="PayPal email"
            hint="Use a Business PayPal account. Payouts for your work are sent to this email."
          >
            {(aria) => (
              <TextInput
                type="email"
                autoComplete="email"
                value={payout}
                onChange={(event) => setPayout(event.target.value)}
                disabled={!canManage}
                {...aria}
              />
            )}
          </Field>
          {canManage && (
            <div className="flex gap-2">
              <Button type="submit" variant="secondary">
                Save
              </Button>
              {org.payout_email && (
                <Button type="button" variant="danger" onClick={() => setConfirmPayout(true)}>
                  Remove
                </Button>
              )}
            </div>
          )}
        </form>
      </Card>
      {confirmPayout && (
        <ConfirmDialog
          title="Remove payout email"
          busy={removingPayout}
          onCancel={() => {
            if (!removingPayout) setConfirmPayout(false);
          }}
          onConfirm={() => void removePayout()}
        >
          <p>
            Payouts will no longer go to {org.payout_email}. You can save a different PayPal email
            afterward.
          </p>
          {payoutError && (
            <Alert tone="danger" className="mt-3">
              {payoutError}
            </Alert>
          )}
        </ConfirmDialog>
      )}
      <Card className="flex flex-col gap-3 p-5">
        <h2 className="font-semibold">API keys</h2>
        <p className="text-sm text-ink-muted">
          A key lets an outside agent use your organization. It can propose and fund contracts. The
          assistant inside Covenant cannot.
        </p>
        {created && (
          <Alert tone="info">
            Copy this key now. It won't be shown again.
            <div className="mt-1 font-mono">{created}</div>
          </Alert>
        )}
        <ul className="flex flex-col gap-2">
          {(keys.data ?? []).map((key) => (
            <li key={key.id} className="flex items-center justify-between">
              <span>
                {key.name} · {key.prefix}…{key.revoked_at ? ' · revoked' : ''}
              </span>
              {canManage && !key.revoked_at && (
                <Button variant="ghost" onClick={() => void revoke(key.id)}>
                  Revoke
                </Button>
              )}
            </li>
          ))}
        </ul>
        {canManage && (
          <form className="flex gap-2" onSubmit={(event) => void createKey(event)}>
            <input
              className="h-10 flex-1 rounded-md border border-line px-3"
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="Key name"
            />
            <Button type="submit" disabled={!name.trim()}>
              Create key
            </Button>
          </form>
        )}
      </Card>
    </div>
  );
}
