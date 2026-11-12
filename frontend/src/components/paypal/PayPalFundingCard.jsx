import { useEffect, useEffectEvent, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useSearchParams } from 'react-router-dom';

import { api, problemOf } from '../../lib/api';
import { FUNDING_ACCOUNT_KEY, useFundingAccount } from '../../lib/queries';
import { usePayPalConnect } from '../../lib/usePayPalConnect';
import { Alert } from '../ui/Alert';
import { Badge } from '../ui/Badge';
import { Button } from '../ui/Button';
import { Card } from '../ui/Card';
import { ConfirmDialog } from '../ui/ConfirmDialog';
import { Spinner } from '../ui/Spinner';

/** "Connect a PayPal account to fund escrow" (W2), used in onboarding and Settings. */
export function PayPalFundingCard({ returnPath, canDisconnect = false }) {
  const queryClient = useQueryClient();
  const account = useFundingAccount();
  const [params, setParams] = useSearchParams();
  const paypal = usePayPalConnect({
    returnPath,
    onConnected: () => queryClient.invalidateQueries({ queryKey: FUNDING_ACCOUNT_KEY }),
  });

  const applyRedirectOutcome = useEffectEvent((outcome) => {
    paypal.showRedirectOutcome(outcome);
    setParams((current) => {
      current.delete('paypal');
      return current;
    });
  });
  const outcome = params.get('paypal');
  useEffect(() => {
    if (outcome) applyRedirectOutcome(outcome);
  }, [outcome]);

  const [confirmRemove, setConfirmRemove] = useState(false);
  const [removing, setRemoving] = useState(false);
  const [removeError, setRemoveError] = useState('');
  const busy = paypal.status === 'starting' || paypal.status === 'waiting';
  const connected = account.data?.mode === 'vault' && account.data.connected;

  async function removeAccount() {
    setRemoving(true);
    setRemoveError('');
    try {
      await api.delete('/paypal/funding-account');
      await queryClient.invalidateQueries({ queryKey: FUNDING_ACCOUNT_KEY });
      setConfirmRemove(false);
    } catch (err) {
      setRemoveError(problemOf(err).detail);
    } finally {
      setRemoving(false);
    }
  }

  return (
    <Card className="flex flex-col gap-4 p-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold">Connect a PayPal account to fund escrow</h2>
          <p className="mt-1 text-ink-muted">
            Holds for agreed work come from this account. You're only charged for work that passes.
          </p>
          <p className="mt-1 text-sm text-ink-muted">Use a Personal PayPal account.</p>
        </div>
      </div>

      {account.isPending && <Spinner className="text-ink-muted" />}
      {account.isError && <Alert tone="danger">{problemOf(account.error).detail}</Alert>}
      {account.data && account.data.mode === 'approve_each' && (
        <p className="flex items-center gap-2 text-base">
          <Badge tone="settled">Ready</Badge>
          You'll approve each hold in a PayPal window when you fund a contract.
        </p>
      )}
      {connected && (
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="flex items-center gap-2 text-base">
            <Badge tone="settled">Connected</Badge>
            Connected: {account.data.payer_email ?? 'PayPal account'}
          </p>
          {canDisconnect && (
            <Button variant="secondary" onClick={() => setConfirmRemove(true)}>
              Remove
            </Button>
          )}
        </div>
      )}
      {account.data?.mode === 'vault' && !account.data.connected && (
        <div className="flex flex-col gap-3">
          <div className="flex items-center gap-3">
            <Button onClick={paypal.connect} loading={busy} loadingText="Waiting for PayPal…">
              Connect PayPal
            </Button>
            {paypal.status === 'waiting' && (
              <Button variant="ghost" size="sm" onClick={paypal.cancel}>
                Cancel
              </Button>
            )}
          </div>
          {paypal.status === 'blocked' && (
            <Alert tone="held">
              Your browser blocked the PayPal window.{' '}
              <button
                type="button"
                onClick={paypal.continueInThisTab}
                className="font-medium underline"
              >
                Continue to PayPal in this tab
              </button>
            </Alert>
          )}
          {(paypal.status === 'cancelled' || paypal.status === 'failed') && (
            <Alert tone={paypal.status === 'failed' ? 'danger' : 'info'}>{paypal.message}</Alert>
          )}
        </div>
      )}

      {confirmRemove && (
        <ConfirmDialog
          title="Remove PayPal account"
          busy={removing}
          onCancel={() => {
            if (!removing) setConfirmRemove(false);
          }}
          onConfirm={() => void removeAccount()}
        >
          <p>
            This disconnects {account.data?.payer_email ?? 'the connected PayPal account'}. You can
            connect a different account afterward. New holds wait until an account is connected.
          </p>
          {removeError && (
            <Alert tone="danger" className="mt-3">
              {removeError}
            </Alert>
          )}
        </ConfirmDialog>
      )}

      <details className="text-sm text-ink-muted">
        <summary className="cursor-pointer font-medium text-ink">Why do we need this?</summary>
        <p className="mt-2">
          PayPal stores your payment method. Covenant never sees card or bank details; it only asks
          PayPal to hold an amount when you agree a contract, then captures or releases it based on
          the verified result.
        </p>
      </details>
    </Card>
  );
}
