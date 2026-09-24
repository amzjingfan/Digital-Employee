// @vitest-environment jsdom

import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
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

it('lets a supervisor assign fulfillment and maintenance independently', async () => {
  const claimed = { ...publicEntry, state: 'claimed', owner_user_id: bd.id, revision: 2,
    fulfillment_user_id: null, maintenance_user_id: null };
  vi.mocked(api.get).mockImplementation(async (path) => path.startsWith('/api/v1/social/creators') ? [] : {
    entries: [claimed], can_manage: true, can_claim: false, assignable_bds: [],
    assignable_users: [{ id: 'ops-1', username: 'operator' }, { id: bd.id, username: 'bd' }],
  });
  render(<TikTokCreatorPoolPanel currentUser={{ ...bd, business_role: 'operations_supervisor' }} />);
  await waitFor(() => expect(screen.getByLabelText('履约负责人 Creator A')).toBeTruthy());
  fireEvent.change(screen.getByLabelText('履约负责人 Creator A'), { target: { value: 'ops-1' } });
  fireEvent.change(screen.getByLabelText('维护负责人 Creator A'), { target: { value: bd.id } });
  fireEvent.click(screen.getByRole('button', { name: '保存分责' }));
  await waitFor(() => expect(api.post).toHaveBeenCalledWith(
    '/api/enterprise/tiktok/creator-responsibilities/entry-1',
    { expected_revision: 2, fulfillment_user_id: 'ops-1', maintenance_user_id: bd.id },
  ));
});

it('can clear a responsibility and hides these controls from BD', async () => {
  const claimed = { ...publicEntry, state: 'claimed', owner_user_id: bd.id, revision: 3,
    fulfillment_user_id: 'ops-1', maintenance_user_id: bd.id };
  vi.mocked(api.get).mockImplementation(async (path) => path.startsWith('/api/v1/social/creators') ? [] : {
    entries: [claimed], can_manage: true, can_claim: false, assignable_bds: [],
    assignable_users: [{ id: 'ops-1', username: 'operator' }, { id: bd.id, username: 'bd' }],
  });
  const view = render(<TikTokCreatorPoolPanel currentUser={{ ...bd, business_role: 'operations_supervisor' }} />);
  await waitFor(() => expect(screen.getByLabelText('履约负责人 Creator A')).toBeTruthy());
  fireEvent.change(screen.getByLabelText('履约负责人 Creator A'), { target: { value: '' } });
  fireEvent.click(screen.getByRole('button', { name: '保存分责' }));
  await waitFor(() => expect(api.post).toHaveBeenCalledWith(
    '/api/enterprise/tiktok/creator-responsibilities/entry-1',
    { expected_revision: 3, fulfillment_user_id: null, maintenance_user_id: bd.id },
  ));
  view.unmount();
  vi.mocked(api.get).mockResolvedValue({
    entries: [claimed], can_manage: false, can_claim: true, assignable_bds: [], assignable_users: [],
  });
  render(<TikTokCreatorPoolPanel currentUser={bd} />);
  await waitFor(() => expect(screen.getByText('Creator A')).toBeTruthy());
  expect(screen.queryByLabelText('履约负责人 Creator A')).toBeNull();
  expect(screen.queryByRole('button', { name: '预检分佣草案' })).toBeNull();
});

it('shows commission preflight blocks without claiming financial approval', async () => {
  const claimed = { ...publicEntry, state: 'claimed', owner_user_id: bd.id, revision: 2,
    fulfillment_user_id: 'ops-1', maintenance_user_id: bd.id };
  vi.mocked(api.get).mockImplementation(async (path) => path.startsWith('/api/v1/social/creators') ? [] : {
    entries: [claimed], can_manage: true, can_claim: false, assignable_bds: [], assignable_users: [],
  });
  vi.mocked(api.post).mockResolvedValueOnce({
    check_codes: ['rule_unapproved'], can_submit_financial_review: false,
  });
  render(<TikTokCreatorPoolPanel currentUser={{ ...bd, business_role: 'operations_supervisor' }} />);
  await waitFor(() => expect(screen.getByLabelText('分佣规则版本 Creator A')).toBeTruthy());
  fireEvent.change(screen.getByLabelText('分佣规则版本 Creator A'), { target: { value: 'proposal-v1' } });
  fireEvent.change(screen.getByLabelText('规则失效时间 Creator A'), { target: { value: '2027-09-24T09:00' } });
  fireEvent.change(screen.getByLabelText('订单引用 Creator A'), { target: { value: `order:${'a'.repeat(32)}` } });
  fireEvent.change(screen.getByLabelText('计算证据 Creator A'), { target: { value: `evidence:${'b'.repeat(32)}` } });
  fireEvent.change(screen.getByLabelText('开发比例 Creator A'), { target: { value: '6000' } });
  fireEvent.change(screen.getByLabelText('履约比例 Creator A'), { target: { value: '2000' } });
  fireEvent.change(screen.getByLabelText('维护比例 Creator A'), { target: { value: '2000' } });
  fireEvent.click(screen.getByRole('button', { name: '预检分佣草案' }));
  await waitFor(() => expect(api.post).toHaveBeenCalledWith(
    '/api/enterprise/tiktok/commission-drafts/entry-1/preflight',
    expect.objectContaining({
      rule_version: 'proposal-v1',
      scopes: [{ order_refs: [`order:${'a'.repeat(32)}`], development_bps: 6000,
        fulfillment_bps: 2000, maintenance_bps: 2000,
        calculation_evidence_ref: `evidence:${'b'.repeat(32)}` }],
    }),
  ));
  expect(screen.getByText(/规则尚未批准/)).toBeTruthy();
  expect(screen.queryByRole('button', { name: '提交财务审核' })).toBeNull();
});

it('saves an unapproved proposal and shows saved order overlap to the supervisor', async () => {
  const claimed = { ...publicEntry, state: 'claimed', owner_user_id: bd.id, revision: 3,
    fulfillment_user_id: 'ops-1', maintenance_user_id: bd.id };
  const saved = {
    id: 'draft-1', rule_version: 'proposal-v1', order_refs: [`order:${'a'.repeat(32)}`],
    development_bps: 6000, fulfillment_bps: 2000, maintenance_bps: 2000,
    check_codes: ['rule_unapproved', 'saved_order_overlap'], can_submit_financial_review: false,
    created_at: '2026-09-24T09:00:00Z',
  };
  vi.mocked(api.get).mockImplementation(async (path) => {
    if (path.startsWith('/api/v1/social/creators')) return [];
    if (path === '/api/enterprise/tiktok/commission-drafts/entry-1') return [saved];
    return { entries: [claimed], can_manage: true, can_claim: false,
      assignable_bds: [], assignable_users: [] };
  });
  vi.mocked(api.post).mockImplementation(async (path) => path.endsWith('/preflight')
    ? { check_codes: ['rule_unapproved'], can_submit_financial_review: false } : saved);
  render(<TikTokCreatorPoolPanel currentUser={{ ...bd, business_role: 'operations_supervisor' }} />);
  await waitFor(() => expect(screen.getByLabelText('分佣规则版本 Creator A')).toBeTruthy());
  fireEvent.change(screen.getByLabelText('分佣规则版本 Creator A'), { target: { value: 'proposal-v1' } });
  fireEvent.change(screen.getByLabelText('规则失效时间 Creator A'), { target: { value: '2027-09-24T09:00' } });
  fireEvent.change(screen.getByLabelText('订单引用 Creator A'), { target: { value: `order:${'a'.repeat(32)}` } });
  fireEvent.change(screen.getByLabelText('计算证据 Creator A'), { target: { value: `evidence:${'b'.repeat(32)}` } });
  fireEvent.change(screen.getByLabelText('开发比例 Creator A'), { target: { value: '6000' } });
  fireEvent.change(screen.getByLabelText('履约比例 Creator A'), { target: { value: '2000' } });
  fireEvent.change(screen.getByLabelText('维护比例 Creator A'), { target: { value: '2000' } });
  fireEvent.click(screen.getByRole('button', { name: '预检分佣草案' }));
  await waitFor(() => expect(screen.getByRole('button', { name: '保存未批准草案' })).toBeTruthy());
  fireEvent.click(screen.getByRole('button', { name: '保存未批准草案' }));
  await waitFor(() => expect(api.post).toHaveBeenCalledWith(
    '/api/enterprise/tiktok/commission-drafts/entry-1',
    expect.objectContaining({ expected_pool_revision: 3,
      idempotency_key: expect.stringMatching(/^[0-9a-f]{32}$/) }),
  ));
  await waitFor(() => expect(screen.getByText(/已保存草案之间存在订单范围重叠/)).toBeTruthy());
  expect(screen.queryByRole('button', { name: '提交财务审核' })).toBeNull();
});

it('does not show a stale preflight response after inputs change', async () => {
  const claimed = { ...publicEntry, state: 'claimed', owner_user_id: bd.id, revision: 2,
    fulfillment_user_id: 'ops-1', maintenance_user_id: bd.id };
  vi.mocked(api.get).mockImplementation(async (path) => path.startsWith('/api/v1/social/creators') ? [] : {
    entries: [claimed], can_manage: true, can_claim: false, assignable_bds: [], assignable_users: [],
  });
  let finish!: (value: unknown) => void;
  vi.mocked(api.post).mockImplementationOnce(() => new Promise((resolve) => { finish = resolve; }));
  render(<TikTokCreatorPoolPanel currentUser={{ ...bd, business_role: 'operations_supervisor' }} />);
  await waitFor(() => expect(screen.getByLabelText('分佣规则版本 Creator A')).toBeTruthy());
  fireEvent.change(screen.getByLabelText('分佣规则版本 Creator A'), { target: { value: 'proposal-v1' } });
  fireEvent.change(screen.getByLabelText('规则失效时间 Creator A'), { target: { value: '2027-09-24T09:00' } });
  fireEvent.change(screen.getByLabelText('订单引用 Creator A'), { target: { value: `order:${'a'.repeat(32)}` } });
  fireEvent.change(screen.getByLabelText('计算证据 Creator A'), { target: { value: `evidence:${'b'.repeat(32)}` } });
  fireEvent.change(screen.getByLabelText('开发比例 Creator A'), { target: { value: '6000' } });
  fireEvent.change(screen.getByLabelText('履约比例 Creator A'), { target: { value: '2000' } });
  fireEvent.change(screen.getByLabelText('维护比例 Creator A'), { target: { value: '2000' } });
  fireEvent.click(screen.getByRole('button', { name: '预检分佣草案' }));
  await waitFor(() => expect(api.post).toHaveBeenCalled());
  fireEvent.change(screen.getByLabelText('开发比例 Creator A'), { target: { value: '5000' } });
  await act(async () => { finish({ check_codes: ['rule_unapproved'], can_submit_financial_review: false }); });
  expect(screen.queryByText(/规则尚未批准/)).toBeNull();
});
