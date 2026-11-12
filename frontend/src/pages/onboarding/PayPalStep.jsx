import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';

import { Alert } from '../../components/ui/Alert';
import { Button } from '../../components/ui/Button';
import { Card } from '../../components/ui/Card';
import { StepActions } from './StepActions';
import { Field, TextInput } from '../../components/ui/Field';
import { PayPalFundingCard } from '../../components/paypal/PayPalFundingCard';
import { api, problemOf } from '../../lib/api';
import { applyServerErrors } from '../../lib/forms';
import { useFundingAccount } from '../../lib/queries';

const payoutSchema = z.object({
  payout_email: z
    .string()
    .trim()
    .max(254)
    .regex(/^[^@\s]+@[^@\s]+\.[^@\s.]+$/, 'Enter the email of a PayPal account'),
});

const FORM_ID = 'onboarding-paypal';

export function PayPalStep({ organization, onDone, onBack }) {
  const funding = useFundingAccount();
  const [formError, setFormError] = useState(null);
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm({
    resolver: organization.can_provide ? zodResolver(payoutSchema) : undefined,
    defaultValues: { payout_email: organization.payout_email ?? '' },
  });

  const fundingReady = !organization.can_hire || Boolean(funding.data?.connected);

  async function onSubmit(values) {
    setFormError(null);
    try {
      if (organization.can_provide) {
        await api.patch('/orgs/current', { payout_email: values.payout_email });
      }
      await onDone();
    } catch (error) {
      const problem = problemOf(error);
      if (!applyServerErrors(problem, setError, ['payout_email'])) setFormError(problem.detail);
    }
  }

  return (
    <div className="flex flex-col gap-4">
      {organization.can_hire && <PayPalFundingCard returnPath="/onboarding" />}
      <form id={FORM_ID} noValidate onSubmit={handleSubmit(onSubmit)} className="flex flex-col gap-4">
        {organization.can_provide && (
          <Card className="p-5">
            <Field
              id="payout_email"
              label="PayPal email for payouts"
              hint="Use a Business PayPal account. Payouts for your work are sent to this email."
              error={errors.payout_email?.message}
            >
              {(aria) => (
                <TextInput
                  type="email"
                  autoComplete="email"
                  {...aria}
                  {...register('payout_email')}
                />
              )}
            </Field>
          </Card>
        )}
        {formError && <Alert tone="danger">{formError}</Alert>}
        <StepActions>
          {onBack && (
            <Button type="button" variant="secondary" onClick={onBack} disabled={isSubmitting}>
              Back
            </Button>
          )}
          <Button
            type="submit"
            form={FORM_ID}
            className="ml-auto"
            disabled={!fundingReady}
            loading={isSubmitting}
            loadingText="Saving…"
          >
            {organization.can_hire ? 'Next' : 'Finish'}
          </Button>
        </StepActions>
      </form>
    </div>
  );
}
