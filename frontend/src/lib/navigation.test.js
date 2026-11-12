import { describe, expect, it } from 'vitest';

import { visibleNavGroups } from './navigation';

function userWith(org, extra = {}) {
  return {
    is_platform_admin: false,
    membership: { role: 'owner', organization: { can_hire: false, can_provide: false, ...org } },
    ...extra,
  };
}

const labels = (user) =>
  visibleNavGroups(user).map((g) => [g.id, g.items.map((i) => i.label).join(',')]);

describe('visibleNavGroups', () => {
  it('shows hirer groups and the mandate only to hirers', () => {
    expect(labels(userWith({ can_hire: true }))).toEqual([
      ['hire', 'Overview,Assistant,Contracts,Find Workers,Catalog,Approvals'],
      ['money', 'Ledger,Schedule,Mandate'],
      ['trust', 'Fleet'],
      ['settings', 'Settings'],
    ]);
  });

  it('shows provider groups without the mandate', () => {
    expect(labels(userWith({ can_provide: true }))).toEqual([
      ['provide', 'My workers,Jobs,Earnings'],
      ['money', 'Ledger,Schedule'],
      ['trust', 'Fleet'],
      ['settings', 'Settings'],
    ]);
  });

  it('adds Admin for platform admins', () => {
    const ids = visibleNavGroups(userWith({ can_hire: true }, { is_platform_admin: true })).map(
      (g) => g.id,
    );
    expect(ids).toContain('admin');
  });

  it('shows nothing before an organization exists', () => {
    expect(visibleNavGroups({ is_platform_admin: false, membership: null })).toEqual([]);
  });
});
