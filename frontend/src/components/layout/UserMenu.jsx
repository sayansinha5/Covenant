import { useEffect, useRef, useState } from 'react';
import { ChevronDown, LogOut } from 'lucide-react';

import { useAuth } from '../../auth/context';

export function UserMenu() {
  const { user, signOut } = useAuth();
  const [open, setOpen] = useState(false);
  const container = useRef(null);

  useEffect(() => {
    if (!open) return undefined;
    function close(event) {
      if (
        event.type === 'keydown'
          ? event.key === 'Escape'
          : !container.current?.contains(event.target)
      ) {
        setOpen(false);
      }
    }
    document.addEventListener('mousedown', close);
    document.addEventListener('keydown', close);
    return () => {
      document.removeEventListener('mousedown', close);
      document.removeEventListener('keydown', close);
    };
  }, [open]);

  const initials = user.full_name
    .split(' ')
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join('');

  return (
    <div ref={container} className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="menu"
        aria-expanded={open}
        className="flex items-center gap-2 rounded-md py-1 pr-2 pl-1 text-left transition-colors duration-200 hover:bg-wash"
      >
        <span
          aria-hidden="true"
          className="grid size-8 place-items-center rounded-full bg-wash text-xs font-semibold text-ink"
        >
          {initials}
        </span>
        <span className="flex flex-col leading-tight">
          <span className="text-sm font-medium text-ink">{user.full_name}</span>
          <span className="text-xs text-ink-muted">{user.membership?.organization.name}</span>
        </span>
        <ChevronDown size={16} strokeWidth={1.5} aria-hidden="true" className="text-ink-muted" />
      </button>
      {open && (
        <div
          role="menu"
          className="absolute right-0 z-20 mt-1 w-56 rounded-lg border border-line bg-surface py-1 shadow-sm"
        >
          <p className="truncate px-3 py-2 text-sm text-ink-muted">{user.email}</p>
          <button
            type="button"
            role="menuitem"
            onClick={() => {
              setOpen(false);
              signOut();
            }}
            className="flex w-full items-center gap-2 px-3 py-2 text-left text-base text-ink hover:bg-wash"
          >
            <LogOut size={16} strokeWidth={1.5} aria-hidden="true" />
            Sign out
          </button>
        </div>
      )}
    </div>
  );
}
