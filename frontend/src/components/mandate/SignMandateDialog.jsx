import { useState } from 'react';

import { api, problemOf } from '../../lib/api';
import { mandateSentence } from '../../lib/mandate';
import { Alert } from '../ui/Alert';
import { Button } from '../ui/Button';
import { Field, PasswordInput } from '../ui/Field';
import { Modal } from '../ui/Modal';

/** Confirms the terms in one sentence and signs them with the owner's password. */
export function SignMandateDialog({ terms, assistantName, onSigned, onClose }) {
  const [password, setPassword] = useState('');
  const [signing, setSigning] = useState(false);
  const [error, setError] = useState(null);

  function reset() {
    setPassword('');
    setError(null);
    setSigning(false);
  }

  function close() {
    reset();
    onClose();
  }

  async function sign(event) {
    event.preventDefault();
    setSigning(true);
    setError(null);
    try {
      const { data } = await api.post('/mandate', { ...terms, password });
      reset();
      await onSigned(data);
    } catch (failure) {
      const problem = problemOf(failure);
      setError({
        field: problem.code === 'PASSWORD_INCORRECT',
        message: problem.errors.length
          ? problem.errors.map((e) => e.message).join(' ')
          : problem.detail,
      });
      setSigning(false);
    }
  }

  return (
    <Modal
      open={Boolean(terms)}
      title="Sign mandate"
      onClose={close}
      busy={signing}
      footer={
        <>
          <Button variant="secondary" onClick={close} disabled={signing}>
            Back
          </Button>
          <Button type="submit" form="sign-mandate" loading={signing} loadingText="Signing…">
            Sign
          </Button>
        </>
      }
    >
      {terms && (
        <form id="sign-mandate" onSubmit={sign} className="flex flex-col gap-4">
          <p className="text-base text-ink">{mandateSentence(assistantName, terms)}</p>
          <Field
            id="mandate-password"
            label="Confirm with your password"
            error={error?.field ? error.message : null}
          >
            {(aria) => (
              <PasswordInput
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                {...aria}
              />
            )}
          </Field>
          {error && !error.field && <Alert tone="danger">{error.message}</Alert>}
        </form>
      )}
    </Modal>
  );
}
