import { Link } from 'react-router-dom';

import { Wordmark } from '../../components/ui/Wordmark';
import { cn } from '../../lib/cn';

const POINTS = [
  {
    kicker: 'Held first',
    title: 'PayPal authorizes the amount before the work starts',
    body: 'A retry after a timeout uses the same request, so it cannot open a second hold.',
  },
  {
    kicker: 'You fund it',
    title: 'The assistant can draft. It cannot pay.',
    body: 'You read the contract, then you fund the hold. Nothing moves before that.',
  },
  {
    kicker: 'Settled in code',
    title: 'A score does not choose the money',
    body: 'The Arbiter checks the delivery. Code captures the full amount, the passing share, or releases the hold.',
  },
];

const OUTCOMES = [
  { detail: '90%+', title: 'Pass', body: 'Full capture' },
  { detail: '50%+', title: 'Partial', body: 'Passing share' },
  { detail: 'Below', title: 'Fail', body: 'Hold released' },
];

const MOBILE = [
  'PayPal holds the funds before the work starts.',
  'You review the contract before anything is funded.',
  'Code captures, splits, or releases the hold.',
];

export function AuthCard({ title, lead, alternate, children, footer }) {
  return (
    <div className="h-screen overflow-hidden bg-canvas text-ink lg:grid lg:grid-cols-2">
      <div className="flex h-screen flex-col">
        <header className="flex h-14 shrink-0 items-center justify-between border-b border-line bg-canvas px-6">
          <Link to="/" aria-label="Covenant">
            <Wordmark />
          </Link>
          <Link to={alternate.to} className={TEXT_LINK}>
            {alternate.label}
          </Link>
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto overscroll-y-contain" data-auth-scroll>
          <div className="mx-auto flex min-h-full w-full flex-col justify-center px-6 py-10">
            <div className="rise-in">
              <h1 className="text-2xl font-bold tracking-tight max-w-md mx-auto text-left">{title}</h1>
              <p className="mt-2 text-ink-muted">{lead}</p>
              <div className="mt-8">{children}</div>
              <p className="mt-6 text-sm text-ink-muted">{footer}</p>
            </div>

            <div className="mt-10 border-t border-line pt-6 lg:hidden">
              <p className="text-xs font-semibold tracking-[0.16em] text-ink-muted uppercase">
                Why Covenant
              </p>
              <ul className="mt-3 flex flex-col gap-2">
                {MOBILE.map((item) => (
                  <li key={item} className="text-sm text-ink-muted">
                    {item}
                  </li>
                ))}
              </ul>
              <p className="mt-3 text-sm text-ink-muted">PayPal sandbox. No live money moves.</p>
            </div>
          </div>
        </div>
      </div>

      <aside className="relative hidden h-screen overflow-hidden border-l border-line bg-canvas lg:block">
        <div
          className="pointer-events-none absolute inset-x-0 top-0 -bottom-48 [mask-image:linear-gradient(to_bottom,#000_58%,transparent)]"
          aria-hidden="true"
        >
          <span className="absolute top-2 left-[22%] size-40 rounded-full bg-accent/35 blur-3xl" />
          <span className="absolute top-8 right-[14%] size-36 rounded-full bg-settled/30 blur-3xl" />
          <span className="absolute top-1/3 left-[6%] size-44 rounded-full bg-brand/25 blur-3xl" />
          <span className="absolute bottom-24 left-[16%] size-40 rounded-full bg-held/30 blur-3xl" />
          <span className="absolute right-[18%] bottom-10 size-44 rounded-full bg-info/25 blur-3xl" />
        </div>
        <div className="relative z-10 h-full overflow-y-auto overscroll-y-contain">
          <div className="flex min-h-full flex-col justify-center px-12 py-16 xl:px-16">
            <div className="mx-auto w-full max-w-lg">
              <h2 className="mt-3 text-3xl font-bold tracking-tight">
                Hold the money <br /> until the work checks out.
              </h2>
              <p className="mt-4 text-ink-muted">
                The same hold covers an outside agent and a person.
              </p>
              <p className="mt-1 text-ink-muted">You agree to the contract first.</p>
              <ul className="mt-8 border-y border-line">
                {POINTS.map((point) => (
                  <li
                    key={point.kicker}
                    className="border-b border-line py-4 transition-colors duration-200 last:border-b-0 hover:bg-canvas/80"
                  >
                    <p className="text-xs font-semibold tracking-[0.16em] text-brand uppercase">
                      {point.kicker}
                    </p>
                    <p className="mt-1 font-medium tracking-tight">{point.title}</p>
                    <p className="mt-1 text-sm text-ink-muted">{point.body}</p>
                  </li>
                ))}
              </ul>
              <div className="mt-8">
                <p className="text-xs font-semibold tracking-[0.16em] text-ink-muted uppercase">
                  A usual contract
                </p>
                <ul className="mt-3 grid grid-cols-3 border border-line bg-canvas">
                  {OUTCOMES.map((item, index) => (
                    <li
                      key={item.title}
                      className={cn(
                        'px-4 py-4',
                        index < OUTCOMES.length - 1 && 'border-r border-line',
                      )}
                    >
                      <p className="text-xs font-semibold tracking-[0.16em] text-brand uppercase">
                        {item.detail}
                      </p>
                      <p className="mt-2 font-medium">{item.title}</p>
                      <p className="mt-1 text-sm text-ink-muted">{item.body}</p>
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          </div>
        </div>
      </aside>
    </div>
  );
}

const TEXT_LINK =
  'inline-flex h-9 items-center justify-center rounded-md px-3 font-medium text-ink-muted transition-colors duration-200 hover:bg-wash hover:text-ink';
