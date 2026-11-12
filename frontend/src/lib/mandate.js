import { z } from 'zod';

import { formatMoneyShort } from './format';
import { AMOUNT_PATTERN, toCents } from './money';

const amount = (label) =>
  z
    .string()
    .trim()
    .regex(AMOUNT_PATTERN, `Enter ${label} like 40 or 40.00`)
    .refine(
      (value) => !AMOUNT_PATTERN.test(value) || toCents(value) > 0n,
      `${label[0].toUpperCase()}${label.slice(1)} must be more than $0`,
    );

/** Mirrors the server's mandate rules so mistakes show next to the field before signing. */
export const mandateSchema = z
  .object({
    monthly_budget: amount('the monthly budget'),
    per_task_cap: amount('the maximum per task'),
    approval_threshold: amount('the approval threshold'),
    allowed_work_types: z.array(z.string()).min(1, 'Choose at least one work type'),
  })
  .superRefine((v, ctx) => {
    const amounts = [v.monthly_budget, v.per_task_cap, v.approval_threshold];
    if (!amounts.every((a) => AMOUNT_PATTERN.test(a) && toCents(a) > 0n)) return;
    if (toCents(v.per_task_cap) > toCents(v.monthly_budget)) {
      ctx.addIssue({
        code: 'custom',
        path: ['per_task_cap'],
        message: "Maximum per task can't be more than the monthly budget",
      });
    }
    if (toCents(v.approval_threshold) > toCents(v.per_task_cap)) {
      ctx.addIssue({
        code: 'custom',
        path: ['approval_threshold'],
        message: "The approval threshold can't be more than the maximum per task",
      });
    }
  });

const WORK_TYPE_PHRASES = {
  translation: 'translation',
  catalog_data: 'catalogue data',
  copywriting: 'copywriting',
  design: 'design',
};

function joinWithAnd(items) {
  if (items.length <= 1) return items.join('');
  return `${items.slice(0, -1).join(', ')} and ${items.at(-1)}`;
}

/** The one-sentence summary shown before signing (W3). */
export function mandateSentence(assistantName, terms) {
  const types = joinWithAnd(terms.allowed_work_types.map((t) => WORK_TYPE_PHRASES[t] ?? t));
  return (
    `${assistantName} may spend up to ${formatMoneyShort(terms.monthly_budget)} per month, ` +
    `${formatMoneyShort(terms.per_task_cap)} per task, and will ask you before anything above ` +
    `${formatMoneyShort(terms.approval_threshold)}, only on ${types}.`
  );
}
