// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';

import { api } from '@/api/client';
import type { EnterpriseAuthUser } from '@/auth';
import TikTokCreatorPoolPanel from '@/pages/tiktok/TikTokCreatorPoolPanel';

vi.mock('@/api/client', () => ({ api: { get: vi.fn(), post: vi.fn() } }));
vi.mock('@/components/ui/app-toast', () => ({ notify: { error: vi.fn(), success: vi.fn() } }));

const bd: EnterpriseAuthUser = {
  id: 'bd-1', tenant_id: 'tenant-a', username: 'bd', role: 'member',
  business_role: 'tiktok_bd_specialist',
};
const publicEntry = {
  id: 'entry-1', creator_id: 'creator-1', identity_id: 'identity-1',
  creator_name: 'Creator A', public_handle: 'creator-a', market: 'US',
  source_ref: 'source:001', sla_rule_version: 'pilot-v1', follow_up_window_hours: 48,
  state: 'public', owner_user_id: null, follow_up_due_at: null, revision: 1,
};

beforeEach(() => {
  vi.mocked(api.get).mockResolvedValue({
    entries: [publicEntry], can_manage: false, can_claim: true,
  });
});
afterEach(() => { cleanup(); vi.clearAllMocks(); });

it('lets a BD claim a public entry but hides supervisor intake', async () => {
  render(<TikTokCreatorPoolPanel currentUser={bd} />);
  await waitFor(() => expect(screen.getByText('Creator A')).toBeTruthy());
  expect(screen.getByText(/pilot-v1/)).toBeTruthy();
  expect(screen.queryByLabelText('达人主档 ID')).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: '认领' }));
  await waitFor(() => expect(api.post).toHaveBeenCalledWith(
    '/api/enterprise/tiktok/creator-claims/entry-1', { expected_revision: 1 },
  ));
});

it('shows supervisor intake but not a BD claim control', async () => {
  vi.mocked(api.get).mockImplementation(async (path) => {
    if (path.startsWith('/api/v1/social/creators')) return [{
      id: 'creator-2', canonical_name: 'Creator B', status: 'active',
      identities: [{ id: 'identity-2', platform: 'tiktok', public_handle: 'creator-b', verified: true, status: 'active', latest_evidence: { id: 'social_evidence_2222222222222222' } }],
    }];
    return { entries: [publicEntry], can_manage: true, can_claim: false };
  });
  render(<TikTokCreatorPoolPanel currentUser={{ ...bd, business_role: 'operations_supervisor' }} />);
  await waitFor(() => expect(screen.getByRole('option', { name: 'Creator B · @creator-b' })).toBeTruthy());
  fireEvent.change(screen.getByLabelText('选择已核验达人'), { target: { value: 'identity-2' } });
  fireEvent.change(screen.getByLabelText('SLA 规则版本'), { target: { value: 'pilot-v1' } });
  fireEvent.change(screen.getByLabelText('跟进窗口小时数'), { target: { value: '48' } });
  fireEvent.click(screen.getByRole('button', { name: '加入公海池' }));
  await waitFor(() => expect(api.post).toHaveBeenCalledWith('/api/enterprise/tiktok/creator-pool', {
    creator_id: 'creator-2', identity_id: 'identity-2', source_ref: 'social_evidence_2222222222222222',
    sla_rule_version: 'pilot-v1', follow_up_window_hours: 48,
  }));
  expect(screen.queryByRole('button', { name: '认领' })).toBeNull();
});

it('refreshes the pool after a stale claim', async () => {
  vi.mocked(api.post).mockRejectedValueOnce(new Error('creator_pool_stale'));
  render(<TikTokCreatorPoolPanel currentUser={bd} />);
  await waitFor(() => expect(screen.getByRole('button', { name: '认领' })).toBeTruthy());
  fireEvent.click(screen.getByRole('button', { name: '认领' }));
  await waitFor(() => expect(api.get).toHaveBeenCalledTimes(2));
});

it('lets a supervisor transfer or release a claimed owner with the current revision', async () => {
  const claimed = { ...publicEntry, state: 'claimed', owner_user_id: bd.id, revision: 2 };
  vi.mocked(api.get).mockImplementation(async (path) => {
    if (path.startsWith('/api/v1/social/creators')) return [];
    return {
      entries: [claimed], can_manage: true, can_claim: false,
      assignable_bds: [{ id: bd.id, username: 'bd' }, { id: 'bd-2', username: 'replacement' }],
    };
  });
  render(<TikTokCreatorPoolPanel currentUser={{ ...bd, business_role: 'operations_supervisor' }} />);
  await waitFor(() => expect(screen.getByLabelText('转交给 Creator A')).toBeTruthy());
  fireEvent.change(screen.getByLabelText('转交给 Creator A'), { target: { value: 'bd-2' } });
  fireEvent.click(screen.getByRole('button', { name: '转交归属' }));
  await waitFor(() => expect(api.post).toHaveBeenCalledWith(
    '/api/enterprise/tiktok/creator-assignments/entry-1',
    { expected_revision: 2, target_user_id: 'bd-2', reason: 'staff_change' },
  ));
  fireEvent.click(screen.getByRole('button', { name: '释放到公海' }));
  await waitFor(() => expect(api.post).toHaveBeenCalledWith(
    '/api/enterprise/tiktok/creator-assignments/entry-1',
    { expected_revision: 2, target_user_id: null, reason: 'manual_release' },
  ));
});
