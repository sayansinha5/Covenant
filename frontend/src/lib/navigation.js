import {
  BookOpen,
  Boxes,
  Briefcase,
  CalendarRange,
  FileText,
  LayoutDashboard,
  MessageSquare,
  Radar,
  ScrollText,
  Settings,
  ShieldCheck,
  ShoppingBag,
  SquareCheckBig,
  Users,
  Wallet,
} from 'lucide-react';

/** Sidebar groups (spec 4.3). `when` decides visibility from the signed-in user. */
export const NAV_GROUPS = [
  {
    id: 'hire',
    label: 'Hire',
    when: (org) => org.can_hire,
    items: [
      { label: 'Overview', to: '/overview', icon: LayoutDashboard, end: true },
      { label: 'Assistant', to: '/assistant', icon: MessageSquare },
      { label: 'Contracts', to: '/contracts', icon: FileText },
      { label: 'Find Workers', to: '/find-workers', icon: Users },
      { label: 'Catalog', to: '/catalog', icon: ShoppingBag },
      { label: 'Approvals', to: '/approvals', icon: SquareCheckBig },
    ],
  },
  {
    id: 'provide',
    label: 'Provide',
    when: (org) => org.can_provide,
    items: [
      { label: 'My workers', to: '/workers', icon: Boxes },
      { label: 'Jobs', to: '/jobs', icon: Briefcase },
      { label: 'Earnings', to: '/earnings', icon: Wallet },
    ],
  },
  {
    id: 'money',
    label: 'Money',
    when: () => true,
    items: [
      { label: 'Ledger', to: '/ledger', icon: BookOpen },
      { label: 'Schedule', to: '/schedule', icon: CalendarRange },
      { label: 'Mandate', to: '/mandate', icon: ScrollText, when: (org) => org.can_hire },
    ],
  },
  {
    id: 'trust',
    label: 'Trust',
    when: () => true,
    items: [{ label: 'Fleet', to: '/fleet', icon: Radar }],
  },
  {
    id: 'settings',
    label: null,
    when: () => true,
    items: [{ label: 'Settings', to: '/settings', icon: Settings }],
  },
  {
    id: 'admin',
    label: 'Admin',
    when: (_org, user) => user.is_platform_admin,
    items: [{ label: 'Admin', to: '/admin', icon: ShieldCheck }],
  },
];

export function visibleNavGroups(user) {
  const org = user.membership?.organization;
  if (!org) return [];
  return NAV_GROUPS.filter((group) => group.when(org, user))
    .map((group) => ({
      ...group,
      items: group.items.filter((item) => !item.when || item.when(org, user)),
    }))
    .filter((group) => group.items.length > 0);
}
