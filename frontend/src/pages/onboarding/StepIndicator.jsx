import { Check } from 'lucide-react';

import { cn } from '../../lib/cn';

export function StepIndicator({ steps, current }) {
  return (
    <ol className="flex flex-col" aria-label="Setup progress">
      {steps.map((step, index) => {
        const done = index < current;
        const active = index === current;
        const last = index === steps.length - 1;
        const Icon = step.icon;
        return (
          <li key={step.label} className="flex gap-3">
            <div className="flex flex-col items-center">
              <span
                aria-current={active ? 'step' : undefined}
                className={cn(
                  'grid size-9 shrink-0 place-items-center rounded-full',
                  active && 'bg-surface text-brand',
                  done && 'bg-surface/20 text-surface',
                  !active && !done && 'bg-surface/10 text-surface/80',
                )}
              >
                {done ? (
                  <Check size={16} strokeWidth={2} aria-hidden="true" />
                ) : (
                  <Icon size={16} strokeWidth={2} aria-hidden="true" />
                )}
              </span>
              {!last && <span aria-hidden="true" className="my-1 w-px flex-1 bg-surface/30" />}
            </div>
            <div className={cn('min-w-0 pt-1.5', !last && 'pb-6')}>
              <p className={cn('font-medium', active ? 'text-surface' : 'text-surface/80')}>
                {step.label}
              </p>
              <p className="mt-0.5 text-sm text-surface/70">{step.body}</p>
            </div>
          </li>
        );
      })}
    </ol>
  );
}
