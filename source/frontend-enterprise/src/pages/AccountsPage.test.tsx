import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import { AccountRoleBadge, AccountStatusBadge } from './AccountsPage';

describe('AccountRoleBadge', () => {
  it('uses the blue status treatment for administrators', () => {
    const rendered = renderToStaticMarkup(createElement(AccountRoleBadge, { role: 'admin' }));

    expect(rendered).toContain('管理员');
    expect(rendered).toContain('bg-[#e8f0ff]');
    expect(rendered).toContain('text-[#1a71ff]');
    expect(rendered).not.toContain('bg-[#f2f3f7]');
  });

  it('uses the neutral status treatment for members', () => {
    const rendered = renderToStaticMarkup(createElement(AccountRoleBadge, { role: 'member' }));

    expect(rendered).toContain('普通成员');
    expect(rendered).toContain('bg-[#f2f3f7]');
    expect(rendered).toContain('text-[#858b9c]');
    expect(rendered).not.toContain('bg-[#e8f0ff]');
  });
});

describe('AccountStatusBadge', () => {
  it('distinguishes active and suspended accounts', () => {
    const active = renderToStaticMarkup(createElement(AccountStatusBadge, { status: 'active' }));
    const suspended = renderToStaticMarkup(createElement(AccountStatusBadge, { status: 'suspended' }));

    expect(active).toContain('已启用');
    expect(suspended).toContain('已停用');
    expect(active).not.toEqual(suspended);
  });
});
