// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { EnterpriseAuthUser } from '@/auth';
import { I18nProvider } from '@/i18n';
import { api } from '@/api/client';

import TikTokBusinessUnitPage from './TikTokBusinessUnitPage';

vi.mock('@/api/client', () => ({ api: { get: vi.fn(), post: vi.fn() } }));
vi.mock('@/components/AppHeader', () => ({ default: () => <div data-testid="app-header" /> }));

const admin: EnterpriseAuthUser = {
  id: 'admin',
  tenant_id: 'tenant_demo',
  username: 'admin',
  role: 'admin',
};

describe('TikTokBusinessUnitPage', () => {
  afterEach(cleanup);

  beforeEach(() => {
    vi.mocked(api.get).mockResolvedValue({
      root: { id: 'root', code: 'tiktok', name: 'TikTok 事业部', revision: 1, status: 'active', unit_type: 'business_unit' },
      departments: [],
      roles: [],
      resources: [],
      authorizations: [],
      task_counts: { pending: 1 },
      ready: false,
      evaluated_at: '2026-09-04T00:00:00Z',
      gates: [{ key: 'agent_releases', label: 'TikTok AgentRelease', status: 'waiting', detail: '已发布 0/5，等待业务负责人审核发布' }],
      items: Array.from({ length: 5 }, (_, index) => ({ slug: `agent-${index}`, name: `TikTok Agent ${index}`, business_role: 'tiktok_content_specialist', ready: false, error: '等待审核' })),
    });
    vi.mocked(api.post).mockResolvedValue({
      created_count: 12,
      skill_ids: Array.from({ length: 12 }, (_, index) => `skill-${index}`),
      agent_ids: ['agent-1'],
      knowledge_base_ids: ['kb-1'],
      tool_ids: ['tool-1'],
    });
  });

  it('exposes six PRD tabs and shows the seeded asset summary', async () => {
    render(<I18nProvider><TikTokBusinessUnitPage currentUser={admin} onLogout={vi.fn()} /></I18nProvider>);

    await waitFor(() => expect(screen.getByText('概览')).toBeTruthy());
    expect(screen.getByText('员工')).toBeTruthy();
    expect(screen.getByText('资产与授权')).toBeTruthy();
    expect(screen.getByText('任务中心')).toBeTruthy();
    expect(screen.getByText('SOP / Skill')).toBeTruthy();
    expect(screen.getByText('风险与 KPI')).toBeTruthy();
    expect(screen.getByText('生产就绪检查')).toBeTruthy();

    fireEvent.click(screen.getByRole('button', { name: '初始化生产资产' }));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/api/enterprise/tiktok/bootstrap-assets'));
    fireEvent.click(screen.getByRole('button', { name: 'SOP / Skill' }));
    expect(screen.getByText(/Skill 已绑定/)).toBeTruthy();
    expect(screen.getByText(/种子资产在业务负责人复核后才能发布/)).toBeTruthy();
  });

  it('records a task-linked shadow comparison and displays quality gates', async () => {
    vi.mocked(api.get).mockImplementation(async (url) => {
      if (url.includes('/shadow/status')) {
        return {
          id: 'shadow-1', status: 'running', started_at: '2026-09-01T00:00:00Z', ends_at: '2026-09-15T00:00:00Z', last_heartbeat_at: '2026-09-08T00:00:00Z', observation_count: 2, error_count: 0, baseline: { writes_enabled: false },
          quality: { reviewed_count: 2, adopted_count: 2, needs_revision_count: 0, rejected_count: 0, guardrail_issue_count: 0, adoption_rate: 1, covered_sop_ids: ['TT-SOP-002'], missing_sop_ids: ['TT-SOP-003', 'TT-SOP-004', 'TT-SOP-007', 'TT-SOP-009'], minimum_reviewed_count: 30, passed: false },
        };
      }
      if (url.includes('/overview')) return { root: null, departments: [], roles: [], resources: [], authorizations: [], task_counts: {} };
      if (url.includes('/production-readiness')) return { ready: false, evaluated_at: '2026-09-08T00:00:00Z', gates: [] };
      return { tenant_id: 'tenant_demo', ready: false, evaluated_at: '2026-09-08T00:00:00Z', items: [] };
    });

    render(<I18nProvider><TikTokBusinessUnitPage currentUser={admin} onLogout={vi.fn()} /></I18nProvider>);
    await waitFor(() => expect(screen.getByText('风险与 KPI')).toBeTruthy());
    fireEvent.click(screen.getByRole('button', { name: '风险与 KPI' }));
    expect(screen.getByText(/人工对照 2\/30/)).toBeTruthy();
    expect(screen.getByText(/待覆盖 TT-SOP-003/)).toBeTruthy();

    fireEvent.change(screen.getByLabelText('TikTok 任务 ID'), { target: { value: 'task-tiktok-1' } });
    fireEvent.change(screen.getByLabelText('脱敏人工对照摘要'), { target: { value: '人工结果一致' } });
    fireEvent.click(screen.getByRole('button', { name: '追加不可变对照证据' }));

    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/api/enterprise/tiktok/shadow/evaluations', {
      task_id: 'task-tiktok-1', verdict: 'adopted', issue_category: 'none', summary: '人工结果一致',
    }));
  });
});
