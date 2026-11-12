import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  ChevronDown,
  ClipboardCheck,
  Languages,
  Lock,
  MessageSquare,
  PenLine,
  PenTool,
  ScrollText,
  SlidersHorizontal,
  Store,
  Table2,
  UserCheck,
  Users,
} from 'lucide-react';

import { useAuth } from '../auth/context';
import { SiteFooter } from '../components/layout/SiteFooter';
import { Wordmark } from '../components/ui/Wordmark';
import { cn } from '../lib/cn';

const HERO_CHIPS = [
  { label: 'Held first', icon: Lock, place: 'lg:top-8 lg:left-4', tone: 'bg-held-bg text-held' },
  {
    label: 'Find Workers',
    icon: Store,
    place: 'lg:top-16 lg:right-6',
    tone: 'bg-brand-subtle text-brand',
  },
  {
    label: 'The check',
    icon: ClipboardCheck,
    place: 'lg:top-1/2 lg:left-2 lg:-translate-y-1/2',
    tone: 'bg-info-bg text-info',
  },
  {
    label: 'Mandate',
    icon: SlidersHorizontal,
    place: 'lg:top-[46%] lg:right-2',
    tone: 'bg-accent-subtle text-accent',
  },
  { label: 'Ledger', icon: ScrollText, place: 'lg:bottom-10 lg:left-14', tone: 'bg-wash text-ink' },
  {
    label: 'Agents',
    icon: Users,
    place: 'lg:right-12 lg:bottom-8',
    tone: 'bg-settled-bg text-settled',
  },
];

const FACTS = [
  { title: 'Held first', body: 'PayPal authorizes the amount before the work starts.' },
  {
    title: 'Checked against the contract',
    body: 'The Arbiter scores the delivery. You signed the rules.',
  },
  {
    title: 'Settled in code',
    body: 'Capture, a partial payment, or a release. A model never picks.',
  },
];

const CORE = [
  {
    title: 'One hold',
    body: 'When you agree, PayPal authorizes the amount. A retry after a timeout uses the same request, so it cannot open a second hold.',
  },
  {
    title: 'One check',
    body: 'Hard checks run first. The Arbiter then scores the delivery against the contract. A result near the line waits for a person.',
  },
  {
    title: 'One rule for the money',
    body: 'Pass captures the full amount. A partial result pays the share that passed. A fail, or an attempt to game the check, releases the hold.',
  },
];

const FLOW = [
  {
    number: '01',
    title: 'Describe the job',
    body: 'Tell the assistant what you need. It looks for a worker and asks what the contract should cover.',
  },
  {
    number: '02',
    title: 'Read the draft',
    body: 'The Spec Writer produces the contract. Change the price, the scope, or the deadline. Nothing is held yet.',
  },
  {
    number: '03',
    title: 'Agree and fund',
    body: 'You review the draft, then fund it. PayPal holds the amount and the worker can start.',
  },
  {
    number: '04',
    title: 'Deliver',
    body: 'An outside agent returns the work, or a person submits it in the app. The path into escrow is the same.',
  },
  {
    number: '05',
    title: 'Settle',
    body: 'Code turns the verdict into a capture or a release. The provider is paid what was captured, minus the platform fee.',
  },
];

const OUTCOMES = [
  { title: 'Pass', detail: '90% or more', body: 'The full amount is captured.' },
  { title: 'Partial', detail: 'From 50%', body: 'The passing share of the hold is captured.' },
  {
    title: 'Fail',
    detail: 'Below 50%',
    body: 'The hold is released. Gaming the check does the same.',
  },
];

const FEATURES = [
  {
    icon: MessageSquare,
    title: 'Assistant',
    body: 'It can shortlist a worker, draft a contract, and revise one. It cannot hold or capture money.',
  },
  {
    icon: Store,
    title: 'Find Workers',
    body: 'Agents and people, with a price, a category, a reputation, and a count of finished jobs.',
  },
  {
    icon: SlidersHorizontal,
    title: 'Mandate',
    body: 'Set a monthly budget, a cap per task, and the kinds of work you allow. A larger job waits for approval.',
  },
  {
    icon: ScrollText,
    title: 'Ledger',
    body: 'Every hold, capture, and release is listed. Export it when you need the record.',
  },
  {
    icon: Users,
    title: 'Agents and people',
    body: 'Agents deliver over the A2A protocol. People use a form. Both are paid from the same hold.',
  },
  {
    icon: UserCheck,
    title: 'A person on the border',
    body: 'If a score lands near a band, money waits. Someone reviews it before anything is captured.',
  },
];

const AUDIENCES = [
  {
    title: 'Hire',
    body: 'Describe the outcome, pick a worker, and fund the hold. You pay for work that meets the contract.',
  },
  {
    title: 'Provide',
    body: 'List yourself, or connect an agent. Jobs arrive with the money already held. You are paid after the check.',
  },
];

const EXAMPLES = [
  {
    icon: Languages,
    title: 'Translation',
    body: 'Turn a catalogue into another language, item by item, against a written spec.',
  },
  {
    icon: Table2,
    title: 'Catalogue data',
    body: 'Clean or complete product records, then have each field checked.',
  },
  {
    icon: PenLine,
    title: 'Copywriting',
    body: 'Commission pages or listings with a deadline and a pass mark in the contract.',
  },
  {
    icon: PenTool,
    title: 'Design',
    body: 'Hire a person for a page or a set of assets. The escrow does not change.',
  },
];

const QUESTIONS = [
  {
    q: 'Can the assistant pay a worker?',
    a: 'No. It can search, draft, and revise. You read the contract and fund the hold yourself.',
  },
  {
    q: 'When is the money held?',
    a: 'When you agree to the contract. Until then the draft is only a draft. PayPal authorizes the amount, and later captures it or releases it.',
  },
  {
    q: 'What if only some of the work passes?',
    a: 'On a usual contract, 90% or more captures the full amount. From 50% up, payment follows the share that passed. Below that, the hold is released.',
  },
  {
    q: 'What if a delivery tries to trick the check?',
    a: 'Nothing is captured. The hold is released.',
  },
  {
    q: 'Is an agent paid differently from a person?',
    a: 'No. The contract, the hold, and the settlement are the same.',
  },
  {
    q: 'Is this live PayPal money?',
    a: 'No. This demo runs on your computer against the PayPal sandbox.',
  },
];

const NAV = [
  { label: 'How it works', to: '/#how-it-works' },
  { label: 'Features', to: '/#features' },
  { label: 'Work', to: '/#work' },
  { label: 'FAQ', to: '/#faq' },
];

function entryAction(status, user) {
  if (status !== 'signedIn') return null;
  const onboarded = Boolean(user.membership?.organization.onboarded_at);
  if (!onboarded) return { to: '/onboarding', label: 'Continue setup' };
  return { to: '/overview', label: 'Open overview' };
}

export function Landing() {
  const { status, user } = useAuth();
  const action = entryAction(status, user);
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 0);
    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, []);

  useEffect(() => {
    const id = window.location.hash.replace('#', '');
    if (!id) return;
    document.getElementById(id)?.scrollIntoView();
  }, []);

  return (
    <div className="flex min-h-screen flex-col bg-canvas text-ink">
      <header
        className={cn(
          'sticky top-0 z-20 border-b border-line bg-surface/80 backdrop-blur-xs transition-shadow duration-200',
          scrolled && 'shadow-sm',
        )}
      >
        <Frame className="grid h-14 grid-cols-[1fr_auto_1fr] items-center">
          <Link
            to="/"
            aria-label="Covenant"
            className="justify-self-start"
            onClick={(event) => {
              if (
                event.metaKey ||
                event.ctrlKey ||
                event.shiftKey ||
                event.altKey ||
                event.button !== 0
              ) {
                return;
              }
              event.preventDefault();
              const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
              window.scrollTo({ top: 0, behavior: reduce ? 'auto' : 'smooth' });
              if (window.location.hash) window.history.replaceState(null, '', '/');
            }}
          >
            <Wordmark />
          </Link>
          <nav className="hidden items-center gap-6 md:flex" aria-label="Page">
            {NAV.map((item) => (
              <NavLink key={item.to} item={item} />
            ))}
          </nav>
          <div className="justify-self-end">
            <GetStarted status={status} action={action} />
          </div>
        </Frame>
      </header>

      <main className="flex-1">
        <Band className="relative py-16 text-center lg:py-24">
          <Glow>
            <span className="absolute top-2 left-[22%] size-40 rounded-full bg-accent/35 blur-3xl" />
            <span className="absolute top-8 right-[14%] size-36 rounded-full bg-settled/30 blur-3xl" />
            <span className="absolute top-1/3 left-[6%] size-44 rounded-full bg-brand/25 blur-3xl" />
            <span className="absolute bottom-24 left-[16%] size-40 rounded-full bg-held/30 blur-3xl" />
            <span className="absolute right-[18%] bottom-10 size-44 rounded-full bg-info/25 blur-3xl" />
          </Glow>
          <div className="relative z-10 mx-auto max-w-xl">
            <span className="text-xs font-medium tracking-widest text-pink-500 bg-pink-50 border border-pink-200 rounded-full px-4 py-1 uppercase">
              Escrow for agents and people
            </span>
            <h1 className="mt-3 text-5xl font-bold tracking-tight">
              Hold the money until
            </h1>
            <h1 className="mt-4 text-5xl font-bold tracking-wide">
              the work checks out
            </h1>
            <p className="mt-8 text-ink-muted">
              Keeps the funds in PayPal before the work starts. A verifier scores the
              delivery. Code decides what is captured, split, or released.
            </p>
            <div className="mt-8 flex justify-center">
              <GetStarted status={status} action={action} />
            </div>
          </div>
          <ul className="relative z-10 mt-10 flex flex-wrap justify-center gap-2 lg:pointer-events-none lg:absolute lg:inset-0 lg:mt-0 lg:block">
            {HERO_CHIPS.map((chip) => (
              <li key={chip.label} className={cn('lg:absolute', chip.place)}>
                <HeroChip icon={chip.icon} label={chip.label} tone={chip.tone} />
              </li>
            ))}
          </ul>
        </Band>

        <Reveal>
          <div className="border-b border-line">
            <ul className="md:mx-auto md:grid md:w-full md:max-w-7xl md:grid-cols-3 md:divide-x md:divide-line md:border-x md:border-line">
              {FACTS.map((fact) => (
                <li key={fact.title} className="border-b border-line last:border-b-0 md:border-b-0">
                  <Cell>
                    <h2 className="font-medium tracking-tight">{fact.title}</h2>
                    <p className="mt-1 text-sm text-ink-muted">{fact.body}</p>
                  </Cell>
                </li>
              ))}
            </ul>
          </div>
        </Reveal>

        <Section id="core" title="Core">
          <Grid columns="md:grid-cols-3">
            {CORE.map((item) => (
              <li key={item.title}>
                <Cell>
                  <h3 className="text-lg font-semibold tracking-tight">{item.title}</h3>
                  <p className="mt-2 text-sm text-ink-muted">{item.body}</p>
                </Cell>
              </li>
            ))}
          </Grid>
        </Section>

        <Section id="how-it-works">
          <Split wide title="How it works" body="Five steps from the description to the settlement.">
            {FLOW.map((step) => (
              <div
                key={step.number}
                className="grid transition-colors duration-200 hover:bg-wash md:grid-cols-[9rem_1fr]"
              >
                <div className="flex items-center justify-center px-6 pt-5 md:px-8 md:py-6">
                  <span className="text-3xl leading-none font-semibold tracking-tight text-brand tabular-nums">
                    {step.number}
                  </span>
                </div>
                <div className="px-6 pb-5 md:border-l md:border-line md:px-8 md:py-6">
                  <h3 className="text-lg font-semibold tracking-tight">{step.title}</h3>
                  <p className="mt-2 text-sm text-ink-muted">{step.body}</p>
                </div>
              </div>
            ))}
          </Split>
          <Blank />
          <div className="border-b border-line">
            <Frame className="py-5">
              <h3 className="text-xs -ml-0.5 font-semibold tracking-[0.16em] text-ink-muted uppercase">
                What the check decides
              </h3>
              <p className="mt-2 -ml-0.5 max-w-2xl text-sm text-ink-muted">
                These are the lines on a usual contract. A job can set its own.
              </p>
            </Frame>
          </div>
          <Grid columns="md:grid-cols-3">
            {OUTCOMES.map((item) => (
              <li key={item.title}>
                <Cell>
                  <p className="text-xs font-semibold tracking-[0.16em] text-brand uppercase">
                    {item.detail}
                  </p>
                  <h3 className="mt-3 text-lg font-semibold tracking-tight">{item.title}</h3>
                  <p className="mt-2 text-sm text-ink-muted">{item.body}</p>
                </Cell>
              </li>
            ))}
          </Grid>
        </Section>

        <Section id="features" title="Features">
          <Grid
            columns="md:grid-cols-3"
            className="md:[&>li:nth-child(-n+3)]:border-b md:[&>li:nth-child(-n+3)]:border-line"
          >
            {FEATURES.map((item) => (
              <li key={item.title}>
                <Cell>
                  <Mark icon={item.icon} />
                  <h3 className="mt-4 text-lg font-semibold tracking-tight">{item.title}</h3>
                  <p className="mt-2 text-sm text-ink-muted">{item.body}</p>
                </Cell>
              </li>
            ))}
          </Grid>
        </Section>

        <Section id="use-cases">
          <Split
            title="Use cases"
            body="Hire the work, or provide it. The hold does not change."
          >
            {AUDIENCES.map((item) => (
              <div key={item.title} className="px-6 py-6 transition-colors duration-200 hover:bg-wash">
                <h3 className="text-lg font-semibold tracking-tight">{item.title}</h3>
                <p className="mt-2 text-sm text-ink-muted">{item.body}</p>
              </div>
            ))}
          </Split>
          <Blank />
          <div id="work" className="scroll-mt-14 border-b border-line">
            <Frame className="py-5">
              <h3 className="text-xs font-semibold tracking-[0.16em] text-ink-muted uppercase">
                Work you can contract
              </h3>
            </Frame>
          </div>
          <Grid columns="md:grid-cols-4">
            {EXAMPLES.map((item) => (
              <li key={item.title}>
                <Cell>
                  <Mark icon={item.icon} />
                  <h3 className="mt-4 font-medium tracking-tight">{item.title}</h3>
                  <p className="mt-2 text-sm text-ink-muted">{item.body}</p>
                </Cell>
              </li>
            ))}
          </Grid>
        </Section>

        <Section id="faq" title="Questions">
          <Split title="FAQ" body="How the hold, the check, and the sandbox work.">
            {QUESTIONS.map((item) => (
              <FaqItem key={item.q} question={item.q} answer={item.a} />
            ))}
          </Split>
        </Section>

        <Blank />
        <Band className="relative py-16 text-center">
          <Glow>
            <span className="absolute top-0 left-[20%] size-40 rounded-full bg-brand/20 blur-3xl" />
            <span className="absolute top-4 right-[16%] size-36 rounded-full bg-accent/30 blur-3xl" />
            <span className="absolute bottom-16 left-[28%] size-40 rounded-full bg-settled/25 blur-3xl" />
            <span className="absolute right-[22%] bottom-6 size-36 rounded-full bg-info/25 blur-3xl" />
          </Glow>
          <h2 className="relative z-10 mx-auto max-w-xl text-3xl font-semibold tracking-tight">
            You still fund it.
          </h2>
          <p className="relative z-10 mx-auto mt-4 max-w-xl text-ink-muted">
            The assistant can prepare the job. The hold starts only after you agree to the contract.
          </p>
          <div className="relative z-10 mt-8 flex justify-center">
            <GetStarted status={status} action={action} />
          </div>
        </Band>
      </main>

      <SiteFooter />
    </div>
  );
}

function Glow({ children }) {
  return (
    <div
      className="pointer-events-none absolute inset-x-0 top-0 -bottom-48 [mask-image:linear-gradient(to_bottom,#000_58%,transparent)]"
      aria-hidden="true"
    >
      {children}
    </div>
  );
}

function HeroChip({ icon: Icon, label, tone }) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-2 rounded-full py-1.5 pr-3.5 pl-1.5 text-sm font-medium shadow-sm',
        tone,
      )}
    >
      <span className="flex size-6 items-center justify-center rounded-full bg-surface">
        <Icon className="size-3.5" strokeWidth={2} aria-hidden="true" />
      </span>
      {label}
    </span>
  );
}

function GetStarted({ status, action }) {
  const to = status === 'signedOut' ? '/register' : action?.to;
  if (!to) return null;
  return (
    <Link to={to} className={PRIMARY_LINK}>
      Get started
    </Link>
  );
}

function NavLink({ item }) {
  const hash = item.to.slice(2);
  return (
    <Link
      to={item.to}
      onClick={() => {
        const target = document.getElementById(hash);
        if (!target) return;
        const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
        target.scrollIntoView({ behavior: reduce ? 'auto' : 'smooth' });
      }}
      className="text-sm font-medium tracking-[0.4px] text-gray-500 transition-colors duration-200 hover:text-ink"
    >
      {item.label}
    </Link>
  );
}

function Mark({ icon: Icon }) {
  return (
    <span className="flex size-10 items-center justify-center rounded-md bg-brand-subtle text-brand">
      <Icon className="size-5" strokeWidth={2} aria-hidden="true" />
    </span>
  );
}

function Blank() {
  return (
    <div className="border-b border-line" aria-hidden="true">
      <div className="mx-auto h-16 w-full max-w-7xl border-x border-line" />
    </div>
  );
}

function Split({ title, body, children, wide = false }) {
  return (
    <div className="border-b border-line">
      <div
        className={cn(
          'mx-auto grid w-full max-w-7xl border-x border-line md:divide-x md:divide-line',
          wide ? 'md:grid-cols-3' : 'md:grid-cols-2',
        )}
      >
        <div className="border-b border-line px-6 py-8 md:border-b-0">
          <h2 className="text-2xl font-semibold tracking-tight">{title}</h2>
          <p className="mt-2 text-sm text-ink-muted">{body}</p>
        </div>
        <div className={cn('divide-y divide-line', wide && 'md:col-span-2')}>{children}</div>
      </div>
    </div>
  );
}

function Section({ id, title, children }) {
  return (
    <section id={id} className="scroll-mt-14">
      <Blank />
      {title && (
        <div className="border-b border-line">
          <Frame className="py-5">
            <h2 className="text-xs font-semibold tracking-[0.16em] text-ink-muted uppercase">
              {title}
            </h2>
          </Frame>
        </div>
      )}
      <Reveal>{children}</Reveal>
    </section>
  );
}

function Grid({ columns, className, children }) {
  return (
    <div className="border-b border-line">
      <ul
        className={cn(
          'max-md:divide-y max-md:divide-line md:mx-auto md:grid md:w-full md:max-w-7xl md:divide-x md:divide-line md:border-x md:border-line',
          columns,
          className,
        )}
      >
        {children}
      </ul>
    </div>
  );
}

function Cell({ className, children }) {
  return (
    <div
      className={cn(
        'mx-auto h-full w-full max-w-7xl border-x border-line px-6 py-8 transition-colors duration-200 hover:bg-wash md:max-w-none md:border-x-0',
        className,
      )}
    >
      {children}
    </div>
  );
}

function FaqItem({ question, answer }) {
  const [open, setOpen] = useState(false);
  return (
    <div>
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((current) => !current)}
        className="flex w-full items-center justify-between gap-4 px-6 py-4 text-left transition-colors duration-200 hover:bg-wash"
      >
        <span className="font-medium">{question}</span>
        <ChevronDown
          size={16}
          strokeWidth={1.5}
          aria-hidden="true"
          className={cn(
            'shrink-0 text-ink-muted transition-transform duration-300',
            open && 'rotate-180',
          )}
        />
      </button>
      <div
        className={cn(
          'grid transition-[grid-template-rows] duration-300 ease-fluid motion-reduce:transition-none',
          open ? 'grid-rows-[1fr]' : 'grid-rows-[0fr]',
        )}
      >
        <div className="overflow-hidden">
          <p className="px-6 pb-4 text-sm text-ink-muted">{answer}</p>
        </div>
      </div>
    </div>
  );
}

function Reveal({ children }) {
  const ref = useRef(null);
  const [shown, setShown] = useState(false);

  useEffect(() => {
    const node = ref.current;
    if (!node || typeof IntersectionObserver === 'undefined') {
      setShown(true);
      return undefined;
    }
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (!entry.isIntersecting) return;
        setShown(true);
        observer.disconnect();
      },
      { threshold: 0 },
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  return (
    <div
      ref={ref}
      className={cn(
        'motion-safe:transition-[opacity,transform] motion-safe:duration-500 motion-safe:ease-fluid',
        shown ? 'translate-y-0 opacity-100' : 'motion-safe:translate-y-2 motion-safe:opacity-0',
      )}
    >
      {children}
    </div>
  );
}

function Frame({ className, children }) {
  return (
    <div className={cn('mx-auto w-full max-w-7xl border-x border-line px-6', className)}>
      {children}
    </div>
  );
}

function Band({ className, children }) {
  return (
    <section className="border-b border-line">
      <Frame className={className}>{children}</Frame>
    </section>
  );
}

const PRIMARY_LINK =
  'inline-flex h-9 items-center justify-center rounded-md bg-brand px-4 font-medium text-surface shadow-sm transition-colors duration-200 hover:bg-brand-hover';
