import { Link } from 'react-router-dom';

import { SiteFooter } from '../components/layout/SiteFooter';
import { Wordmark } from '../components/ui/Wordmark';

export function Privacy() {
  return (
    <div className="flex min-h-screen flex-col bg-canvas text-ink">
      <header className="border-b border-line">
        <div className="mx-auto flex h-14 w-full max-w-7xl items-center border-x border-line px-6">
          <Link to="/" aria-label="Covenant">
            <Wordmark />
          </Link>
        </div>
      </header>
      <main className="flex flex-1 flex-col border-b border-line">
        <article className="mx-auto w-full max-w-7xl flex-1 border-x border-line px-6 py-16">
          <h1 className="text-3xl font-semibold tracking-tight">Privacy policy</h1>
          <div className="mt-6 flex max-w-xl flex-col gap-4 text-ink-muted">
            <p>
              Covenant is a localhost demo. An account stores your name and email. The password is
              stored only as a hash.
            </p>
            <p>
              The access token stays in memory. A refresh cookie keeps the session. PayPal holds the
              sandbox account when you connect one.
            </p>
          </div>
        </article>
      </main>
      <SiteFooter />
    </div>
  );
}
