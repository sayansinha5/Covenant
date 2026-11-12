import { useForm, useWatch } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';

import { mandateSchema } from '../../lib/mandate';
import { normalizeAmount } from '../../lib/money';
import { Button } from '../ui/Button';
import { Field, TextInput } from '../ui/Field';

const AMOUNT_FIELDS = [
  { name: 'monthly_budget', label: 'Monthly budget (USD)' },
  { name: 'per_task_cap', label: 'Maximum per task (USD)' },
  {
    name: 'approval_threshold',
    label: 'Ask me first above (USD)',
    hint: 'Anything above this needs an owner or admin to approve.',
  },
];

/** Mandate terms (S12). Submitting hands normalized terms to `onSubmit`; signing happens there. */
export function MandateForm({
  initial,
  workTypes,
  submitLabel,
  onSubmit,
  onCancel,
  formId,
  hideActions = false,
}) {
  const {
    register,
    control,
    handleSubmit,
    formState: { errors },
  } = useForm({ resolver: zodResolver(mandateSchema), defaultValues: initial });
  const allowed = useWatch({ control, name: 'allowed_work_types' }) ?? [];
  const blocked = workTypes.filter((type) => !allowed.includes(type.value));

  function submit(values) {
    onSubmit({
      ...values,
      monthly_budget: normalizeAmount(values.monthly_budget),
      per_task_cap: normalizeAmount(values.per_task_cap),
      approval_threshold: normalizeAmount(values.approval_threshold),
    });
  }

  return (
    <form id={formId} noValidate onSubmit={handleSubmit(submit)} className="flex flex-col gap-5">
      <div className="grid grid-cols-3 gap-4">
        {AMOUNT_FIELDS.map(({ name, label, hint }) => (
          <Field key={name} id={name} label={label} hint={hint} error={errors[name]?.message}>
            {(aria) => (
              <TextInput
                inputMode="decimal"
                className="tabular-nums"
                {...aria}
                {...register(name)}
              />
            )}
          </Field>
        ))}
      </div>

      <fieldset className="flex flex-col gap-2">
        <legend className="mb-1.5 text-sm font-medium text-ink">Allowed work types</legend>
        <div className="grid grid-cols-2 gap-2">
          {workTypes.map((type) => (
            <label key={type.value} className="flex items-center gap-2 text-base">
              <input
                type="checkbox"
                value={type.value}
                className="size-4 accent-brand"
                {...register('allowed_work_types')}
              />
              {type.label}
            </label>
          ))}
        </div>
        {errors.allowed_work_types && (
          <p className="text-sm text-danger">{errors.allowed_work_types.message}</p>
        )}
        <p className="text-sm text-ink-muted">
          Blocked: {blocked.length ? blocked.map((t) => t.label).join(', ') : 'nothing'}
        </p>
      </fieldset>

      {!hideActions && (
        <div className="flex justify-end gap-2">
          {onCancel && (
            <Button variant="secondary" onClick={onCancel}>
              Cancel
            </Button>
          )}
          <Button type="submit">{submitLabel}</Button>
        </div>
      )}
    </form>
  );
}
