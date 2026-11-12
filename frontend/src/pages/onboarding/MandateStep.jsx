import { useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';

import { MandateForm } from '../../components/mandate/MandateForm';
import { SignMandateDialog } from '../../components/mandate/SignMandateDialog';
import { Alert } from '../../components/ui/Alert';
import { Button } from '../../components/ui/Button';
import { Card } from '../../components/ui/Card';
import { Spinner } from '../../components/ui/Spinner';
import { StepActions } from './StepActions';
import { problemOf } from '../../lib/api';
import { MANDATE_KEY, useMandate } from '../../lib/queries';

const FORM_ID = 'onboarding-mandate';

export function MandateStep({ organization, onSigned, onBack }) {
  const queryClient = useQueryClient();
  const mandate = useMandate();
  const [pending, setPending] = useState(null);

  if (mandate.isPending) return <Spinner className="text-ink-muted" />;
  if (mandate.isError) return <Alert tone="danger">{problemOf(mandate.error).detail}</Alert>;

  async function handleSigned(signed) {
    setPending(null);
    await queryClient.invalidateQueries({ queryKey: MANDATE_KEY });
    await onSigned(signed);
  }

  const { defaults, work_types: workTypes, active } = mandate.data;
  return (
    <>
      <Card className="p-5">
        <h2 className="text-lg font-semibold">Set {organization.assistant_name}'s spending rules</h2>
        <p className="mt-1 mb-5 text-ink-muted">
          Every hold is checked against these rules in code, whoever asks for it. You can sign a new
          version at any time.
        </p>
        <MandateForm
          formId={FORM_ID}
          hideActions
          initial={active ?? defaults}
          workTypes={workTypes}
          onSubmit={setPending}
        />
        <SignMandateDialog
          terms={pending}
          assistantName={organization.assistant_name}
          onClose={() => setPending(null)}
          onSigned={handleSigned}
        />
      </Card>
      <StepActions>
        {onBack && (
          <Button type="button" variant="secondary" onClick={onBack}>
            Back
          </Button>
        )}
        <Button type="submit" form={FORM_ID} className="ml-auto">
          Finish
        </Button>
      </StepActions>
    </>
  );
}
