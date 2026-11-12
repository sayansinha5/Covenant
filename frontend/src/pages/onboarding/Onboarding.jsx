import { useState } from 'react';
import { Building2, ScrollText, Wallet } from 'lucide-react';

import { useAuth } from '../../auth/context';
import { UserMenu } from '../../components/layout/UserMenu';
import { Alert } from '../../components/ui/Alert';
import { useToast } from '../../components/ui/toast-context';
import { api, problemOf } from '../../lib/api';
import { MandateStep } from './MandateStep';
import { OrganizationStep } from './OrganizationStep';
import { PayPalStep } from './PayPalStep';
import { StepIndicator } from './StepIndicator';

const STEPS = [
  {
    label: 'Organization',
    body: 'Who you are, and how you will use Covenant',
    icon: Building2,
  },
  {
    label: 'PayPal',
    body: 'The account that funds holds or receives payouts',
    icon: Wallet,
  },
  {
    label: 'Mandate',
    body: 'The spending rules your assistant must follow',
    icon: ScrollText,
  },
];

const HEADINGS = [
  {
    title: 'Your organization',
    body: 'Tell us who you are, and whether you hire work, provide it, or both. You can change this later in Settings.',
  },
  {
    title: 'Connect PayPal',
    body: 'PayPal moves the money. Covenant decides when.',
  },
  {
    title: 'Sign your mandate',
    body: 'These rules decide what can be spent. Code enforces them.',
  },
];

export function Onboarding() {
  const { user, switchAccessToken, reloadUser } = useAuth();
  const toast = useToast();
  const organization = user.membership?.organization ?? null;
  const [step, setStep] = useState(organization ? 1 : 0);
  const [finishError, setFinishError] = useState(null);

  async function finish(message) {
    setFinishError(null);
    try {
      await api.post('/orgs/current/onboarding/complete');
      if (message) toast(message);
      // Once the org is marked onboarded, the route guard moves the user into the app.
      await reloadUser();
    } catch (error) {
      setFinishError(problemOf(error).detail);
    }
  }

  async function handleCreated(created) {
    await switchAccessToken(created.access_token);
    setStep(1);
  }

  async function handlePayPalDone() {
    if (organization.can_hire) setStep(2);
    else await finish(null);
  }

  const steps = organization && !organization.can_hire ? STEPS.slice(0, 2) : STEPS;
  const heading = HEADINGS[step];
  return (
    <main className="grid min-h-screen bg-surface lg:h-screen lg:grid-cols-[20rem_1fr] lg:overflow-hidden">
      <aside className="relative flex flex-col overflow-hidden bg-brand px-6 py-8 text-surface">
        <span className="inline-flex items-center gap-2 text-lg font-semibold tracking-tight">
          <span aria-hidden="true" className="size-4 rounded-full bg-surface" />
          Covenant
        </span>
        <div className="relative z-10 mt-10">
          <StepIndicator steps={steps} current={step} />
        </div>
        <p className="relative z-10 mt-auto pt-10 text-xs text-surface/70">© 2026 Covenant</p>
        <svg
          aria-hidden="true"
          className="pointer-events-none absolute -right-8 bottom-0 h-56 w-56 text-surface/15"
          viewBox="0 0 200 200"
          fill="none"
        >
          <circle cx="120" cy="120" r="70" stroke="currentColor" strokeWidth="8" />
          <circle cx="150" cy="90" r="40" stroke="currentColor" strokeWidth="8" />
          <circle cx="70" cy="160" r="28" stroke="currentColor" strokeWidth="8" />
        </svg>
      </aside>

      <section className="relative flex min-h-[100dvh] flex-col overflow-hidden lg:h-full lg:min-h-0">
        <div className="flex shrink-0 justify-end px-6 pt-4 sm:px-10">
          <UserMenu />
        </div>
        <svg
          aria-hidden="true"
          className="pointer-events-none absolute top-8 -right-6 h-64 w-64 text-brand/10"
          viewBox="0 0 200 200"
          fill="none"
        >
          <circle cx="110" cy="70" r="60" stroke="currentColor" strokeWidth="8" />
          <circle cx="150" cy="130" r="36" stroke="currentColor" strokeWidth="8" />
        </svg>
        <div className="relative min-h-0 flex-1 overflow-y-auto px-6 pt-4 sm:px-10">
          <div className="max-w-2xl pb-8">
            <p className="text-sm text-ink-muted">
              Step {step + 1}/{steps.length}
            </p>
            <h1 className="mt-2 text-2xl font-semibold tracking-tight">{heading.title}</h1>
            {heading.body && <p className="mt-2 text-ink-muted">{heading.body}</p>}
            <div className="mt-6 border-t border-line pt-6">
              {step === 0 && <OrganizationStep onCreated={handleCreated} />}
              {step === 1 && organization && (
                <PayPalStep organization={organization} onDone={handlePayPalDone} />
              )}
              {step === 2 && organization && (
                <MandateStep
                  organization={organization}
                  onBack={() => setStep(1)}
                  onSigned={(mandate) => finish(`Mandate v${mandate.version} signed.`)}
                />
              )}
              {finishError && (
                <Alert tone="danger" className="mt-4">
                  {finishError}
                </Alert>
              )}
            </div>
          </div>
        </div>
        <div className="shrink-0 bg-surface px-6 py-4 sm:px-10">
          <div id="onboarding-actions" className="flex max-w-2xl items-center gap-3" />
        </div>
      </section>
    </main>
  );
}
