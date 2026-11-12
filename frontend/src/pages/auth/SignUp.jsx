import { useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { useForm, useWatch } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { Check, Circle } from 'lucide-react';
import { Link } from 'react-router-dom';
import { z } from 'zod';

import { useAuth } from '../../auth/context';
import { Alert } from '../../components/ui/Alert';
import { Button } from '../../components/ui/Button';
import { Field, PasswordInput, TextInput } from '../../components/ui/Field';
import { api, problemOf } from '../../lib/api';
import { cn } from '../../lib/cn';
import { applyServerErrors } from '../../lib/forms';
import { PASSWORD_MAX_LENGTH, PASSWORD_RULES, passwordMeetsRules } from '../../lib/password';
import { AuthCard } from './AuthCard';

const schema = z.object({
  full_name: z.string().trim().min(1, 'Enter your name').max(120, 'Use at most 120 characters'),
  email: z
    .string()
    .trim()
    .min(1, 'Enter your work email')
    .max(254, 'Use at most 254 characters')
    .regex(/^[^@\s]+@[^@\s]+\.[^@\s.]+$/, 'Enter a valid email address'),
  password: z
    .string()
    .max(PASSWORD_MAX_LENGTH, `Use at most ${PASSWORD_MAX_LENGTH} characters`)
    .refine(passwordMeetsRules, 'Use at least 12 characters, with a letter and a number'),
});

const SERVER_FIELDS = ['full_name', 'email', 'password'];

function PasswordBubble({ value, anchorRef }) {
  const bubbleRef = useRef(null);

  useLayoutEffect(() => {
    const anchor = anchorRef.current;
    const bubble = bubbleRef.current;
    if (!anchor || !bubble) return undefined;
    const scroller = anchor.closest('[data-auth-scroll]');

    function place() {
      const rect = anchor.getBoundingClientRect();
      const port = scroller?.getBoundingClientRect();
      const visible = !port || (rect.bottom > port.top + 4 && rect.top < port.bottom - 4);
      const wide = window.matchMedia('(min-width: 1024px)').matches;
      bubble.style.visibility = visible ? 'visible' : 'hidden';
      if (!visible) return;
      if (wide) {
        bubble.style.top = `${rect.top + rect.height / 2}px`;
        bubble.style.left = `${rect.right + 12}px`;
        bubble.style.transform = 'translateY(-50%)';
        return;
      }
      bubble.style.top = `${rect.top - 10}px`;
      bubble.style.left = `${rect.right}px`;
      bubble.style.transform = 'translate(-100%, -100%)';
    }

    place();
    scroller?.addEventListener('scroll', place, { passive: true });
    window.addEventListener('resize', place);
    const observer = new ResizeObserver(place);
    observer.observe(anchor);
    return () => {
      scroller?.removeEventListener('scroll', place);
      window.removeEventListener('resize', place);
      observer.disconnect();
    };
  }, [anchorRef]);

  return createPortal(
    <div
      ref={bubbleRef}
      id="password-rules"
      role="tooltip"
      style={{ visibility: 'hidden' }}
      className="fixed z-30 w-56 rounded-lg border border-line bg-surface p-3 shadow-sm"
    >
      <span
        aria-hidden="true"
        className="absolute -bottom-2 right-4 border-x-[6px] border-t-[7px] border-x-transparent border-t-line lg:hidden"
      />
      <span
        aria-hidden="true"
        className="absolute -bottom-[5px] right-4 border-x-[6px] border-t-[7px] border-x-transparent border-t-surface lg:hidden"
      />
      <span
        aria-hidden="true"
        className="absolute top-1/2 -left-2 hidden -translate-y-1/2 border-y-[6px] border-r-[7px] border-y-transparent border-r-line lg:block"
      />
      <span
        aria-hidden="true"
        className="absolute top-1/2 -left-[5px] hidden -translate-y-1/2 border-y-[6px] border-r-[7px] border-y-transparent border-r-surface lg:block"
      />
      <p className="text-sm font-medium">Password needs</p>
      <ul className="mt-2 flex flex-col gap-1.5" aria-label="Password rules">
        {PASSWORD_RULES.map((rule) => {
          const met = rule.test(value ?? '');
          const Icon = met ? Check : Circle;
          return (
            <li
              key={rule.id}
              className={cn('flex items-center gap-2 text-sm', met ? 'text-settled' : 'text-ink-muted')}
            >
              <Icon size={14} strokeWidth={1.5} aria-hidden="true" />
              {rule.label}
              <span className="sr-only">{met ? '(done)' : '(not yet)'}</span>
            </li>
          );
        })}
      </ul>
    </div>,
    document.body,
  );
}

export function SignUp() {
  const { startSession } = useAuth();
  const [formError, setFormError] = useState(null);
  const {
    register,
    control,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm({
    resolver: zodResolver(schema),
    defaultValues: {
      full_name: '',
      email: '',
      password: '',
    },
  });
  const password = useWatch({ control, name: 'password' });
  const [rulesOpen, setRulesOpen] = useState(false);
  const passwordAnchor = useRef(null);

  async function onSubmit(values) {
    setFormError(null);
    const { full_name, email, password } = values;
    try {
      const { data } = await api.post('/auth/signup', {
        full_name,
        email,
        password,
        accept_sandbox: true,
      });
      startSession(data);
    } catch (error) {
      const problem = problemOf(error);
      if (!applyServerErrors(problem, setError, SERVER_FIELDS, { EMAIL_TAKEN: 'email' })) {
        setFormError(problem.detail);
      }
    }
  }

  return (
    <AuthCard
      title="Create account"
      lead=""
      alternate={{ to: '/login', label: 'Login' }}
    >
      <form noValidate onSubmit={handleSubmit(onSubmit)} className="flex flex-col gap-4 max-w-md mx-auto">
        {formError && <Alert tone="danger">{formError}</Alert>}
        <Field id="full_name" label="Full name" error={errors.full_name?.message}>
          {(aria) => (
            <TextInput autoComplete="name" autoFocus {...aria} {...register('full_name')} />
          )}
        </Field>
        <Field id="email" label="Work email" error={errors.email?.message}>
          {(aria) => (
            <TextInput type="email" autoComplete="email" {...aria} {...register('email')} />
          )}
        </Field>
        <Field id="password" label="Password" error={errors.password?.message}>
          {(aria) => (
            <div
              ref={passwordAnchor}
              className="relative"
              onFocus={() => setRulesOpen(true)}
              onBlur={(event) => {
                if (!event.currentTarget.contains(event.relatedTarget)) setRulesOpen(false);
              }}
            >
              <PasswordInput
                autoComplete="new-password"
                {...aria}
                {...register('password')}
                aria-describedby={
                  [aria['aria-describedby'], rulesOpen ? 'password-rules' : undefined]
                    .filter(Boolean)
                    .join(' ') || undefined
                }
              />
              {rulesOpen && <PasswordBubble value={password} anchorRef={passwordAnchor} />}
            </div>
          )}
        </Field>
        <p className="text-sm text-ink-muted border-y border-dashed border-gray-300 py-4">
          By creating an account, you agree to the{' '}
          <Link to="/terms" className="font-medium text-brand hover:underline">
            Terms & Conditions
          </Link>{' '}
          and{' '}
          <Link to="/privacy" className="font-medium text-brand hover:underline">
            Privacy Policy
          </Link>
          .
        </p>
        <Button
          type="submit"
          loading={isSubmitting}
          loadingText="Creating account…"
          className="mt-1 w-full"
        >
          Create account
        </Button>
      </form>
    </AuthCard>
  );
}
