import { useState } from 'react';
import { Eye, EyeOff } from 'lucide-react';

import { cn } from '../../lib/cn';

const CONTROL =
  'h-9 w-full rounded-md border border-line bg-surface px-3 text-base text-ink ' +
  'placeholder:text-ink-muted focus:border-brand focus:outline-none ' +
  'aria-invalid:border-danger disabled:bg-wash disabled:text-ink-muted';

/** Label, control, then either the error or the hint. The control gets the matching aria props. */
export function Field({ id, label, error, hint, children }) {
  const describedBy = error ? `${id}-error` : hint ? `${id}-hint` : undefined;
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-sm font-medium text-ink">
        {label}
      </label>
      {children({ id, 'aria-invalid': error ? true : undefined, 'aria-describedby': describedBy })}
      {error ? (
        <p id={`${id}-error`} className="text-sm text-danger">
          {error}
        </p>
      ) : (
        hint && (
          <p id={`${id}-hint`} className="text-sm text-ink-muted">
            {hint}
          </p>
        )
      )}
    </div>
  );
}

export function TextInput({ className, ...props }) {
  return <input className={cn(CONTROL, className)} {...props} />;
}

export function PasswordInput({ className, ...props }) {
  const [visible, setVisible] = useState(false);
  const Icon = visible ? EyeOff : Eye;
  return (
    <div className="relative">
      <input
        type={visible ? 'text' : 'password'}
        className={cn(CONTROL, 'pr-10', className)}
        {...props}
      />
      <button
        type="button"
        onClick={() => setVisible((v) => !v)}
        aria-label={visible ? 'Hide password' : 'Show password'}
        aria-pressed={visible}
        className="absolute inset-y-0 right-0 flex w-9 items-center justify-center text-ink-muted hover:text-ink"
      >
        <Icon size={16} strokeWidth={1.5} aria-hidden="true" />
      </button>
    </div>
  );
}

export function Select({ className, options, placeholder, ...props }) {
  return (
    <select className={cn(CONTROL, 'pr-8', className)} {...props}>
      {placeholder && (
        <option value="" disabled>
          {placeholder}
        </option>
      )}
      {options.map((option) => (
        <option key={option.value} value={option.value}>
          {option.label}
        </option>
      ))}
    </select>
  );
}

export function Checkbox({ id, label, className, ...props }) {
  return (
    <label
      htmlFor={id}
      className={cn('flex cursor-pointer items-start space-x-2.5 text-base text-ink', className)}
    >
      <input id={id} type="checkbox" className="mt-0.5 size-4 shrink-0 accent-brand" {...props} />
      <span>{label}</span>
    </label>
  );
}
