import { Link } from 'react-router-dom';

import { SiteFooter } from '../components/layout/SiteFooter';
import { Wordmark } from '../components/ui/Wordmark';

export function Terms() {
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
          <h1 className="text-3xl font-semibold tracking-tight">Terms & conditions</h1>
          <div className="mt-6 flex max-w-xl flex-col gap-4 text-ink-muted">
            <p>
              This demo runs against the PayPal sandbox. You review a contract before any money is
              held.
            </p>
            <p>
              The assistant can draft, and a verifier can score. Neither can capture or release the
              funds. That decision stays in code.
            </p>
          </div>
        </article>
      </main>
      <SiteFooter />
    </div>
  );
}
