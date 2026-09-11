// @vitest-environment jsdom

import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { api } from '@/api/client';
import IdentityRolesPage from '@/pages/IdentityRolesPage';

vi.mock('@/api/client', () => ({ api: { get: vi.fn(), post: vi.fn() } }));

describe('IdentityRolesPage', () => {
  beforeEach(() => {
    vi.mocked(api.get).mockResolvedValue({
      group_claim: 'groups',
      require_mapped_group: true,
      casdoor_management: {
        enabled: true,
        configured: true,
        sync_interval_seconds: 900,
      },
      roles: [{
        key: 'designer',
        label: '美工设计',
        casdoor_groups: ['九头蛇/staffdeck-jiutoushe-designer'],
        description: '维护商品视觉素材和设计知识资产。',
      }],
      accounts: [{
        id: 'user-1',
        username: 'designer-one',
        display_name: '设计一组',
        account_role: 'member',
        business_role: 'designer',
        business_role_label: '美工设计',
        authorization_source: 'oidc_groups',
        identity_groups: ['九头蛇/staffdeck-jiutoushe-designer'],
        role_synced_at: '2026-08-31T08:00:00Z',
      }],
    });
  });

  it('renders group mappings and effective account roles', async () => {
    render(<IdentityRolesPage />);
    await waitFor(() => expect(screen.getByText('设计一组')).toBeTruthy());
    expect(screen.getAllByText('美工设计').length).toBeGreaterThan(0);
    expect(screen.getAllByText('九头蛇/staffdeck-jiutoushe-designer').length).toBeGreaterThan(0);
    expect(screen.getByText('拒绝登录')).toBeTruthy();
    expect(screen.getByText('已启用 · 凭据完整')).toBeTruthy();
  });
});
