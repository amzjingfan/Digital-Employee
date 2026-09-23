// @vitest-environment jsdom

import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';

import { api } from '@/api/client';
import type { EnterpriseAuthUser } from '@/auth';
import TikTokHistoryPanel from '@/pages/tiktok/TikTokHistoryPanel';

vi.mock('@/api/client', () => ({ api: { get: vi.fn(), post: vi.fn() } }));
vi.mock('@/components/ui/app-toast', () => ({ notify: { error: vi.fn(), success: vi.fn() } }));

const history = {
  tenant_id: 'tenant_a',
  total_count: 1,
  reviewed_count: 0,
  eligible_reviewed_count: 0,
  eligible_total_count: 0,
  exit_ready: false,
  can_confirm: false,
  bd_options: [{ id: 'member', label: 'bd' }],
  metrics: [{ code: 'gmv', version: 1, label: 'GMV', value: null, unit: 'currency', reason: 'gmv_missing' }],
  facts: [{
    id: 'fact-1', tenant_id: 'tenant_a', domain: 'sample', business_key: 'sample-1',
    observed_at: '2026-09-21T00:00:00Z', source_label: 'sanitized-export',
    recorded_run_id: 'recorded-run-1', recorded_approval_ref: 'approval-1',
    source_kind: 'synthetic', assigned_bd_user_id: 'member',
    values: { status: 'approved' }, latest_verdict: null, latest_comparison_ref: null,
  }],
};

const member: EnterpriseAuthUser = {
  id: 'member', tenant_id: 'tenant_a', username: 'bd', role: 'member',
  business_role: 'tiktok_bd_specialist',
};

beforeEach(() => {
  vi.mocked(api.get).mockImplementation(async (path) => {
    if (path.startsWith('/api/enterprise/tiktok/history?')) return history;
    return { recent_runs: [], owner_options: [] };
  });
});
afterEach(() => { cleanup(); vi.clearAllMocks(); });

it('shows evidence and noncomputable metric without counting synthetic records', async () => {
  render(<TikTokHistoryPanel currentUser={member} />);
  await waitFor(() => expect(screen.getByText('sample-1')).toBeTruthy());
  expect(screen.getByText(/候选历史已核对 0 \/ 30/)).toBeTruthy();
  expect(screen.getByText('不可计算：gmv_missing')).toBeTruthy();
  expect(screen.queryByLabelText('导入历史 JSON')).toBeNull();
});

it('shows import controls only to tenant administrators', async () => {
  render(<TikTokHistoryPanel currentUser={{ ...member, role: 'admin' }} />);
  await waitFor(() => expect(screen.getByLabelText('导入历史 JSON')).toBeTruthy());
});

it('allows a non-admin business owner to see the confirmation control', async () => {
  vi.mocked(api.get).mockResolvedValue({ ...history, can_confirm: true });
  render(<TikTokHistoryPanel currentUser={{ ...member, business_role: 'member' }} />);
  await waitFor(() => expect(screen.getByLabelText('业务 Owner 确认编号')).toBeTruthy());
  expect(screen.queryByLabelText('导入历史 JSON')).toBeNull();
});
