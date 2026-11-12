import { useState } from 'react';

import { Alert } from '../../components/ui/Alert';
import { Button } from '../../components/ui/Button';
import { Field, TextInput } from '../../components/ui/Field';
import { Modal } from '../../components/ui/Modal';
import { api, problemOf } from '../../lib/api';

const ACTIONS = {
  suspend: { title: 'Suspend', verb: 'Suspend', busy: 'Suspending…', variant: 'danger' },
  reinstate: { title: 'Reinstate', verb: 'Reinstate', busy: 'Reinstating…', variant: 'primary' },
};

/** Suspend or reinstate one worker; the reason is required and kept in the audit log. */
export function ModerationDialog({ worker, action, onDone, onClose }) {
  const [reason, setReason] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const copy = ACTIONS[action] ?? ACTIONS.suspend;

  function close() {
    setReason('');
    setError(null);
    onClose();
  }

  async function submit(event) {
    event.preventDefault();
    setSaving(true);
    setError(null);
    try {
      const { data } = await api.post(`/admin/workers/${worker.id}/${action}`, { reason });
      setReason('');
      await onDone(data);
    } catch (failure) {
      const problem = problemOf(failure);
      setError(
        problem.errors.length ? problem.errors.map((e) => e.message).join(' ') : problem.detail,
      );
    } finally {
      setSaving(false);
    }
  }

  return (
    <Modal
      open={Boolean(worker)}
      title={worker ? `${copy.title} ${worker.display_name}` : ''}
      onClose={close}
      busy={saving}
      footer={
        <>
          <Button variant="secondary" onClick={close} disabled={saving}>
            Back
          </Button>
          <Button
            type="submit"
            form="moderate-worker"
            variant={copy.variant}
            loading={saving}
            loadingText={copy.busy}
          >
            {copy.verb}
          </Button>
        </>
      }
    >
      {worker && (
        <form id="moderate-worker" onSubmit={submit} className="flex flex-col gap-4">
          <p className="text-base text-ink">
            {action === 'suspend'
              ? `${worker.display_name} (${worker.org_name}) disappears from Find Workers and can't be hired.`
              : `${worker.display_name} (${worker.org_name}) is listed again if it passed verification.`}
          </p>
          <Field
            id="moderation-reason"
            label="Reason"
            hint="At least 3 characters. Recorded in the audit log."
          >
            {(aria) => (
              <TextInput
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                minLength={3}
                maxLength={255}
                required
                {...aria}
              />
            )}
          </Field>
          {error && <Alert tone="danger">{error}</Alert>}
        </form>
      )}
    </Modal>
  );
}
