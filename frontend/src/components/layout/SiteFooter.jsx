import { Link } from 'react-router-dom';

import { cn } from '../../lib/cn';
import { Wordmark } from '../ui/Wordmark';

const COLS = 'md:grid-cols-[minmax(0,1fr)_12rem_12rem]';

const RESOURCES = [
  { label: 'Features', to: '/#features' },
  { label: 'Use cases', to: '/#use-cases' },
];

const COMPANY = [
  { label: 'About', to: '/about' },
  { label: 'Guides', to: '/guides' },
  { label: 'Careers', to: '/careers' },
];

const HEADS = ['Resources', 'Company'];

export function SiteFooter() {
  return (
    <footer>
      <Blank />
      <section className="border-b border-line">
        <div className={cn('mx-auto hidden w-full max-w-7xl border-x border-line md:grid', COLS)}>
          <div className="row-span-2 border-r border-line px-6 py-8">
            <Wordmark />
          </div>
          {HEADS.map((label) => (
            <h2
              key={label}
              className={cn(
                HEADING,
                'border-b border-line px-6 py-5',
                label !== 'Company' && 'border-r',
              )}
            >
              {label}
            </h2>
          ))}
          <LinkColumn items={RESOURCES} />
          <LinkColumn items={COMPANY} edge />
        </div>

        <div className="md:hidden">
          <Frame>
            <Wordmark />
          </Frame>
          <div className="border-b border-line">
            <div className="mx-auto grid w-full max-w-7xl grid-cols-2 border-x border-line">
              {HEADS.map((label, index) => (
                <h2
                  key={label}
                  className={cn(
                    HEADING,
                    'px-4 py-5',
                    index < HEADS.length - 1 && 'border-r border-line',
                  )}
                >
                  {label}
                </h2>
              ))}
            </div>
          </div>
          {RESOURCES.map((item) => (
            <Frame key={item.to} className="py-0">
              <FooterLink item={item} />
            </Frame>
          ))}
          {COMPANY.map((item) => (
            <Frame key={item.to} className="py-0">
              <FooterLink item={item} />
            </Frame>
          ))}
        </div>
      </section>

      <Blank />

      <section className="border-b border-line">
        <div className={cn('mx-auto hidden w-full max-w-7xl border-x border-line md:grid', COLS)}>
          <p className="border-r border-line px-6 py-4 text-sm text-ink-muted">© 2026 Covenant</p>
          <div className="border-r border-line">
            <FooterLink item={{ label: 'Privacy policy', to: '/privacy' }} className="h-12" />
          </div>
          <FooterLink item={{ label: 'Terms & conditions', to: '/terms' }} className="h-12" />
        </div>
        <div className="md:hidden">
          <Frame>
            <p className="text-sm text-ink-muted">© 2026 Covenant</p>
          </Frame>
          <Frame>
            <FooterLink item={{ label: 'Privacy policy', to: '/privacy' }} />
          </Frame>
          <Frame className="border-b-0">
            <FooterLink item={{ label: 'Terms & conditions', to: '/terms' }} />
          </Frame>
        </div>
      </section>

      <div aria-hidden="true">
        <div className="@container pt-20 mx-auto w-full max-w-7xl overflow-hidden border-x border-line">
          <p className="text-center text-[21.5cqw] leading-none font-semibold whitespace-nowrap text-gray-100 [mask-image:linear-gradient(to_bottom,#000_42%,transparent)]">
            Covenant
          </p>
        </div>
      </div>
    </footer>
  );
}

function Blank() {
  return (
    <section className="border-b border-line" aria-hidden="true">
      <div className="mx-auto h-16 w-full max-w-7xl border-x border-line" />
    </section>
  );
}

function LinkColumn({ items, edge = false }) {
  return (
    <div className={cn('flex flex-col', !edge && 'border-r border-line')}>
      {items.map((item) => (
        <FooterLink key={item.to} item={item} className="h-12 border-b border-line" />
      ))}
      <div className="flex-1" />
    </div>
  );
}

function FooterLink({ item, className }) {
  const hash = item.to.startsWith('/#') ? item.to.slice(2) : '';
  return (
    <Link
      to={item.to}
      onClick={() => {
        if (!hash) return;
        const target = document.getElementById(hash);
        if (!target) return;
        const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
        target.scrollIntoView({ behavior: reduce ? 'auto' : 'smooth' });
      }}
      className={cn('flex items-center px-6 text-sm text-ink-muted hover:text-ink', className)}
    >
      {item.label}
    </Link>
  );
}

function Frame({ className, children }) {
  return (
    <div className={cn('border-b border-line', className)}>
      <div className="mx-auto w-full max-w-7xl border-x border-line px-6 py-5">{children}</div>
    </div>
  );
}

const HEADING = 'text-xs font-semibold tracking-[0.16em] text-ink-muted uppercase';
