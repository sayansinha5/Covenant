import { useMemo, useState } from 'react';
import { useForm, useWatch } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';

import { Alert } from '../../components/ui/Alert';
import { Button } from '../../components/ui/Button';
import { Field, Select, TextInput } from '../../components/ui/Field';
import { StepActions } from './StepActions';
import { api, problemOf } from '../../lib/api';
import { cn } from '../../lib/cn';
import { applyServerErrors } from '../../lib/forms';
import { INDUSTRIES, countryOptions } from '../../lib/options';

const schema = z
  .object({
    name: z.string().trim().min(1, 'Enter the organization name').max(120),
    industry: z.string().min(1, 'Choose an industry'),
    country: z.string().min(1, 'Choose a country'),
    can_hire: z.boolean(),
    can_provide: z.boolean(),
    assistant_name: z.string().trim().max(40, 'Use at most 40 characters'),
  })
  .refine((v) => v.can_hire || v.can_provide, {
    path: ['can_hire'],
    message: 'Choose at least one: Hire workers or Provide work.',
  })
  .refine((v) => !v.can_hire || v.assistant_name.length > 0, {
    path: ['assistant_name'],
    message: 'Name your assistant',
  });

const SERVER_FIELDS = ['name', 'industry', 'country', 'assistant_name'];

const CAPABILITIES = [
  {
    name: 'can_hire',
    title: 'Hire workers',
    body: 'Get work done by agents and freelancers, paid through escrow',
  },
  {
    name: 'can_provide',
    title: 'Provide work',
    body: 'Earn by offering an AI agent or your own skills',
  },
];

function CapabilityCard({ title, body, checked, inputProps }) {
  return (
    <label
      className={cn(
        'flex cursor-pointer gap-3 rounded-lg border p-4 transition-colors',
        checked ? 'border-brand bg-brand-subtle' : 'border-line bg-surface hover:bg-wash',
      )}
    >
      <input type="checkbox" className="mt-0.5 size-4 accent-brand" {...inputProps} />
      <span className="flex flex-col gap-1">
        <span className="font-medium text-ink">{title}</span>
        <span className="text-sm text-ink-muted">{body}</span>
      </span>
    </label>
  );
}

const FORM_ID = 'onboarding-organization';

export function OrganizationStep({ onCreated, onBack }) {
  const [formError, setFormError] = useState(null);
  const countries = useMemo(() => countryOptions(), []);
  const {
    register,
    control,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm({
    resolver: zodResolver(schema),
    defaultValues: {
      name: '',
      industry: '',
      country: '',
      can_hire: false,
      can_provide: false,
      assistant_name: 'Mira',
    },
  });
  const [canHire, canProvide] = useWatch({ control, name: ['can_hire', 'can_provide'] });
  const checked = { can_hire: canHire, can_provide: canProvide };

  async function onSubmit(values) {
    setFormError(null);
    const payload = { ...values, assistant_name: values.can_hire ? values.assistant_name : null };
    try {
      const { data } = await api.post('/orgs', payload);
      await onCreated(data);
    } catch (error) {
      const problem = problemOf(error);
      if (!applyServerErrors(problem, setError, SERVER_FIELDS)) setFormError(problem.detail);
    }
  }

  return (
    <form id={FORM_ID} noValidate onSubmit={handleSubmit(onSubmit)} className="flex flex-col gap-5">
      <Field id="name" label="Organization name" error={errors.name?.message}>
        {(aria) => (
          <TextInput autoComplete="organization" autoFocus {...aria} {...register('name')} />
        )}
      </Field>
      <div className="grid grid-cols-2 gap-4">
        <Field id="industry" label="Industry" error={errors.industry?.message}>
          {(aria) => (
            <Select
              options={INDUSTRIES}
              placeholder="Choose…"
              {...aria}
              {...register('industry')}
            />
          )}
        </Field>
        <Field id="country" label="Country" error={errors.country?.message}>
          {(aria) => (
            <Select options={countries} placeholder="Choose…" {...aria} {...register('country')} />
          )}
        </Field>
      </div>

      <fieldset className="flex flex-col gap-2">
        <legend className="mb-1.5 text-sm font-medium text-ink">
          What will you use Covenant for?
        </legend>
        <div className="grid grid-cols-2 gap-3">
          {CAPABILITIES.map((capability) => (
            <CapabilityCard
              key={capability.name}
              title={capability.title}
              body={capability.body}
              checked={checked[capability.name]}
              inputProps={register(capability.name)}
            />
          ))}
        </div>
        {errors.can_hire && <p className="text-sm text-danger">{errors.can_hire.message}</p>}
      </fieldset>

      {canHire && (
        <Field
          id="assistant_name"
          label="Name your assistant"
          hint="Your assistant finds workers, drafts contracts and asks before spending above your limit."
          error={errors.assistant_name?.message}
        >
          {(aria) => <TextInput className="max-w-xs" {...aria} {...register('assistant_name')} />}
        </Field>
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
          loading={isSubmitting}
          loadingText="Saving…"
        >
          Next
        </Button>
      </StepActions>
    </form>
  );
}
