import { useState } from 'react';
import { Outlet, useMatches } from 'react-router-dom';

import { cn } from '../../lib/cn';
import { Notifications } from './Notifications';
import { Sidebar } from './Sidebar';
import { UserMenu } from './UserMenu';
import { WorkSearch } from './WorkSearch';

const SIDEBAR_KEY = 'covenant.sidebar';

function readCollapsed() {
  try {
    return localStorage.getItem(SIDEBAR_KEY) === 'collapsed';
  } catch {
    return false;
  }
}

export function AppLayout() {
  const matches = useMatches();
  const title = matches
    .map((match) => match.handle?.title)
    .filter(Boolean)
    .at(-1);
  const bleed = matches.some((match) => match.handle?.bleed);
  const [collapsed, setCollapsed] = useState(readCollapsed);

  function toggleSidebar() {
    setCollapsed((current) => {
      const next = !current;
      try {
        localStorage.setItem(SIDEBAR_KEY, next ? 'collapsed' : 'expanded');
      } catch {
        /* Private mode can refuse storage; the rail still toggles for this visit. */
      }
      return next;
    });
  }

  return (
    <div className="min-h-screen bg-canvas">
      <Sidebar collapsed={collapsed} onToggle={toggleSidebar} />
      <div
        className={cn(
          'min-h-screen transition-[padding-left] duration-300 ease-fluid',
          collapsed ? 'pl-16' : 'pl-60',
        )}
      >
        <header
          className={cn(
            'fixed top-0 right-0 z-20 flex h-14 items-center justify-between border-b border-line bg-surface px-6',
            'transition-[left] duration-300 ease-fluid',
            collapsed ? 'left-16' : 'left-60',
          )}
        >
          <h1 className="text-lg font-semibold tracking-tight">{title}</h1>
          <div className="flex min-w-0 items-center gap-3">
            <WorkSearch />
            <Notifications />
            <UserMenu />
          </div>
        </header>
        {bleed ? (
          <main
            className={cn(
              'fixed top-14 right-0 bottom-0 transition-[left] duration-300 ease-fluid',
              collapsed ? 'left-16' : 'left-60',
            )}
          >
            <Outlet />
          </main>
        ) : (
          <main className="mx-auto w-full max-w-[1280px] px-6 pt-20 pb-10">
            <Outlet />
          </main>
        )}
      </div>
    </div>
  );
}
