import { PanelLeftClose, PanelLeftOpen } from 'lucide-react';
import { NavLink } from 'react-router-dom';

import { useAuth } from '../../auth/context';
import { cn } from '../../lib/cn';
import { visibleNavGroups } from '../../lib/navigation';
import { useApprovals } from '../../lib/queries';
import { Wordmark } from '../ui/Wordmark';

const ICON_STROKE = 2;

export function Sidebar({ collapsed, onToggle }) {
  const { user } = useAuth();
  const groups = visibleNavGroups(user);
  const canHire = Boolean(user.membership?.organization?.can_hire);
  const approvals = useApprovals({ enabled: canHire });
  const pendingApprovals = (approvals.data ?? []).filter(
    (item) => item.status === 'pending',
  ).length;
  const settings = groups.find((group) => group.id === 'settings');
  const main = groups.filter((group) => group.id !== 'settings');
  const Icon = collapsed ? PanelLeftOpen : PanelLeftClose;

  return (
    <aside
      className={cn(
        'fixed inset-y-0 left-0 z-30 flex flex-col overflow-hidden border-r border-line bg-surface',
        'transition-[width] duration-300 ease-fluid',
        collapsed ? 'w-16' : 'w-60',
      )}
    >
      <div
        className={cn(
          'flex h-14 shrink-0 items-center border-b border-line',
          collapsed ? 'justify-center' : 'px-5',
        )}
      >
        <Wordmark compact={collapsed} />
      </div>
      <nav aria-label="Main" className="flex min-h-0 flex-1 flex-col">
        <div
          className={cn(
            'flex min-h-0 flex-1 flex-col overflow-y-auto px-3 py-3',
            collapsed ? 'gap-0' : 'gap-4',
          )}
        >
          {main.map((group, index) => (
            <div key={group.id} className="flex flex-col">
              {collapsed && group.label && index > 0 && (
                <div aria-hidden="true" className="mx-auto my-1.5 h-px w-6 bg-line" />
              )}
              <div className="flex flex-col gap-0.5">
                {group.label && (
                  <h2
                    className={cn(
                      'px-3 pb-1 text-xs font-medium tracking-[0.14em] text-ink-muted uppercase',
                      collapsed && 'sr-only',
                    )}
                  >
                    {group.label}
                  </h2>
                )}
                {group.items.map((item) => (
                  <NavItem
                    key={item.to}
                    item={item}
                    collapsed={collapsed}
                    count={item.to === '/approvals' ? pendingApprovals : 0}
                  />
                ))}
              </div>
            </div>
          ))}
        </div>
        {settings && (
          <div className="flex shrink-0 flex-col px-3 py-3">
            {settings.items.map((item) => (
              <NavItem key={item.to} item={item} collapsed={collapsed} />
            ))}
          </div>
        )}
      </nav>
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={!collapsed}
        aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        className={cn(
          'fixed z-40 grid place-items-center rounded-md text-ink-muted',
          'bg-surface transition-[left,top,color,background-color] duration-300 ease-fluid hover:text-ink',
          collapsed
            ? 'top-14 left-16 size-7 -translate-x-1/2 -translate-y-1/2 border border-line shadow-sm hover:bg-wash'
            : 'top-3 left-[200px] size-8 hover:bg-wash',
        )}
      >
        <Icon size={16} strokeWidth={ICON_STROKE} aria-hidden="true" />
      </button>
    </aside>
  );
}

function NavItem({ item, collapsed, count = 0 }) {
  const { label, to, icon: ItemIcon, end } = item;
  const waiting = count > 0 ? `${label}, ${count} waiting` : label;
  return (
    <NavLink
      to={to}
      end={end}
      title={collapsed ? waiting : undefined}
      aria-label={count > 0 ? waiting : undefined}
      className={({ isActive }) =>
        cn(
          'flex h-9 items-center rounded-md text-base whitespace-nowrap',
          'transition-colors duration-200 ease-fluid',
          collapsed ? 'size-9 shrink-0 self-center justify-center px-0' : 'h-9 gap-2.5 px-3',
          isActive
            ? 'bg-brand-subtle font-medium text-ink'
            : 'text-ink-muted hover:bg-wash hover:text-ink',
        )
      }
    >
      {({ isActive }) => (
        <>
          <span className="relative shrink-0">
            <ItemIcon
              size={16}
              strokeWidth={ICON_STROKE}
              aria-hidden="true"
              className={cn('transition-colors duration-200', isActive && 'text-brand')}
            />
            {collapsed && count > 0 && (
              <span className="absolute -top-2 -right-2 grid min-w-4 place-items-center rounded-full bg-brand px-1 text-[10px] leading-4 font-medium text-surface tabular-nums">
                {count > 9 ? '9+' : count}
              </span>
            )}
          </span>
          <span className={cn('truncate', collapsed && 'sr-only')}>{label}</span>
          {!collapsed && count > 0 && (
            <span className="ml-auto grid min-w-5 place-items-center rounded-full bg-brand px-1.5 text-xs font-medium text-surface tabular-nums">
              {count}
            </span>
          )}
        </>
      )}
    </NavLink>
  );
}
