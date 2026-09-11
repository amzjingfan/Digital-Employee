// @vitest-environment jsdom

import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { EnterpriseAuthUser } from '@/auth';
import { I18nProvider } from '@/i18n';

import OperationsReportsPage from '@/pages/OperationsReportsPage';

const supervisor: EnterpriseAuthUser = {
  id: 'joe-id',
  tenant_id: 'tenant_demo',
  username: 'Joe',
  role: 'member',
  business_role: 'operations_supervisor',
  enterprise_permissions: { operations_reports: ['view', 'create'] },
};

const report = {
  id: 'report-1',
  tenant_id: 'tenant_demo',
  report_type: 'daily',
  title: '2026-09-01 日报',
  status: 'draft',
  timezone: 'Asia/Shanghai',
  period_start: '2026-08-31T16:00:00Z',
  period_end: '2026-09-01T16:00:00Z',
  scope: {},
  metrics: {
    pending_approvals: 2,
    active_executions: 1,
    failed_executions: 1,
    overdue_runs: 1,
    failed_runs: 0,
    authorization_denials: 3,
    data_as_of: '2026-09-01T08:00:00Z',
  },
  sections: {
    major_exceptions: [{ source_id: 'source-1', severity: 'high', summary: 'publish_listing · timeout' }],
    role_activity: [{ name: '物流异常专员', total: 4, statuses: { completed: 3, running: 1 } }],
    data_quality: ['报告周期内没有广告巡检运行数据'],
  },
  data_status: 'partial',
  source_count: 1,
  generated_by_user_id: 'joe-id',
  generated_at: '2026-09-01T08:00:00Z',
  updated_at: '2026-09-01T08:00:00Z',
  sources: [{
    id: 'source-1',
    source_type: 'execution',
    source_id: 'execution-1',
    business_key: 'execution:approval-1',
    severity: 'high',
    label: '执行异常',
    summary: 'publish_listing · timeout',
    source_route: '/enterprise/business-resources?view=executions&execution_id=execution-1',
    occurred_at: '2026-09-01T07:00:00Z',
  }],
  comments: [],
};

function response(payload: unknown): Response {
  return new Response(JSON.stringify(payload), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  });
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe('OperationsReportsPage', () => {
  it('renders evidence-backed metrics, data warnings and source links', async () => {
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes('/api/enterprise/operations-reports/report-1')) {
        return Promise.resolve(response(report));
      }
      if (url.includes('/api/enterprise/operations-reports')) {
        return Promise.resolve(response([{ ...report, sources: [], comments: [] }]));
      }
      return Promise.resolve(new Response('{}', { status: 404 }));
    }));

    render(<I18nProvider><OperationsReportsPage currentUser={supervisor} onLogout={vi.fn()} /></I18nProvider>);

    expect(await screen.findAllByText('2026-09-01 日报')).not.toHaveLength(0);
    expect(screen.getByText('报告周期内没有广告巡检运行数据')).toBeTruthy();
    expect(screen.getAllByText('publish_listing · timeout').length).toBeGreaterThan(0);
    expect(screen.getByRole('link', { name: /执行异常/ }).getAttribute('href')).toContain('execution-1');
    expect(screen.getByRole('button', { name: '确认报告' })).toBeTruthy();
    expect(screen.getByRole('button', { name: '创建后续任务' })).toBeTruthy();
  });
});

