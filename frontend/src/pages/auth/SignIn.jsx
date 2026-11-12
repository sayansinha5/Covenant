import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { User } from 'lucide-react';
import { Link } from 'react-router-dom';
import { z } from 'zod';

import { useAuth } from '../../auth/context';
import { Alert } from '../../components/ui/Alert';
import { Button } from '../../components/ui/Button';
import { Field, PasswordInput, TextInput } from '../../components/ui/Field';
import { api, problemOf } from '../../lib/api';
import { AuthCard } from './AuthCard';

// Seeded local accounts. Passwords match the sample logins in the README.
const DEMO_ACCOUNTS = [
  {
    fullName: 'Ada Tester',
    email: 'ada+s5check@example.com',
    password: 'correct horse battery 9',
  },
  {
    fullName: 'Riya Sen',
    email: 'riya+482917@kantha.example',
    password: 'kantha stoles 2026',
  },
  {
    fullName: 'Anika Desai',
    email: 'anika.desai@example.com',
    password: 'correct horse battery 9',
  },
  {
    fullName: 'Kabir Shah',
    email: 'kabir@studio.example',
    password: 'studio looms 2026',
  },
  {
    fullName: 'Arjun Nair',
    email: 'arjun@design.example',
    password: 'kantha motifs 2026',
  },
  {
    fullName: 'Covenant Admin',
    email: 'admin@covenant.local',
    password: 'ChangeMe-Admin-2026',
  },
];

const schema = z.object({
  email: z.string().trim().min(1, 'Enter your email'),
  password: z.string().min(1, 'Enter your password'),
});

const INVALID_CREDENTIALS = 'Email or password is incorrect.';

export function SignIn() {
  const { startSession } = useAuth();
  const [formError, setFormError] = useState(null);
  const {
    register,
    handleSubmit,
    setValue,
    formState: { errors, isSubmitting },
  } = useForm({ resolver: zodResolver(schema), defaultValues: { email: '', password: '' } });

  function fillAccount(account) {
    setFormError(null);
    setValue('email', account.email, { shouldValidate: true, shouldDirty: true });
    setValue('password', account.password, { shouldValidate: true, shouldDirty: true });
  }

  async function onSubmit(values) {
    setFormError(null);
    try {
      const { data } = await api.post('/auth/login', values);
      startSession(data);
    } catch (error) {
      const problem = problemOf(error);
      // Field-level validation errors would hint at which part was wrong; keep it generic.
      setFormError(
        problem.code === 'VALIDATION_ERROR' || problem.code === 'INVALID_CREDENTIALS'
          ? INVALID_CREDENTIALS
          : problem.detail,
      );
    }
  }

  return (
    <AuthCard
      title="Sign in"
      lead=""
      alternate={{ to: '/register', label: 'Create an account' }}
    >
      <form noValidate onSubmit={handleSubmit(onSubmit)} className="flex flex-col gap-4 max-w-md mx-auto">
        {formError && <Alert tone="danger">{formError}</Alert>}
        <Field id="email" label="Email" error={errors.email?.message}>
          {(aria) => (
            <TextInput
              type="email"
              autoComplete="email"
              autoFocus
              {...aria}
              {...register('email')}
            />
          )}
        </Field>
        <Field id="password" label="Password" error={errors.password?.message}>
          {(aria) => (
            <PasswordInput autoComplete="current-password" {...aria} {...register('password')} />
          )}
        </Field>
        <Button type="submit" loading={isSubmitting} loadingText="Signing in…" className="mt-1 w-full">
          Sign in
        </Button>
      </form>
        <div className="relative max-w-md mx-auto my-6">
          <div className="absolute inset-x-0 top-1/2 border-t border-line" aria-hidden="true" />
          <p className="relative mx-auto w-fit bg-canvas px-3 text-xs font-medium tracking-[0.14em] text-ink-muted">
            DEMO ACCOUNTS
          </p>
        </div>
        <ul className="max-w-4xl mx-auto grid grid-cols-3 gap-3">
          {DEMO_ACCOUNTS.map((account) => {
            return (
              <li key={account.email}>
                <button
                  type="button"
                  onClick={() => fillAccount(account)}
                  className="flex w-full items-center gap-3 rounded-md border border-line px-3 py-2 text-left transition-colors duration-200 hover:bg-wash"
                >
                  <span className="grid size-9 shrink-0 place-items-center rounded-full bg-brand-subtle text-brand">
                    <User size={16} strokeWidth={2} aria-hidden="true" />
                  </span>
                  <span className="min-w-0">
                    <span className="block truncate font-medium text-sm">{account.fullName}</span>
                    <span className="mt-0.5 block truncate text-xs text-ink-muted">{account.email}</span>
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
    </AuthCard>
  );
}
