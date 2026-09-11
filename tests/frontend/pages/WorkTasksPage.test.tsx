// @vitest-environment jsdom

import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { EnterpriseAuthUser } from '@/auth';
import { I18nProvider } from '@/i18n';

import WorkTasksPage from '@/pages/WorkTasksPage';

const supervisor: EnterpriseAuthUser = {
  id: 'joe-id', tenant_id: 'tenant_demo', username: 'Joe', role: 'member',
  business_role: 'operations_supervisor', enterprise_permissions: { work_tasks: ['view', 'create'] },
};

const task = {
  id: 'worktask-1', tenant_id: 'tenant_demo', source_type: 'operations_report_follow_up',
  source_report_id: 'report-1', title: '核对物流异常并补充承运商回执', description: '来自日报',
  owner_business_role: 'logistics_exception_specialist', owner_role_label: '物流异常专员',
  assignee_agent_id: 'agent-logistics', assignee_agent_name: '物流异常专员',
  priority: 'high', risk_level: 'high', status: 'pending', scope: {}, version: 0,
  due_at: '2026-09-01T10:00:00Z', created_at: '2026-09-01T08:00:00Z', updated_at: '2026-09-01T08:00:00Z',
  evidence: [{ id: 'evidence-1', source_type: 'execution', source_id: 'execution-1', severity: 'high', label: '执行异常', summary: '物流连接器超时', source_route: '/enterprise/business-resources', occurred_at: '2026-09-01T07:00:00Z' }],
  events: [{ id: 'event-1', event_type: 'created_from_report', actor_business_role: 'operations_supervisor', from_status: null, to_status: 'pending', detail: {}, created_at: '2026-09-01T08:00:00Z' }],
};

function response(payload: unknown): Response {
  return new Response(JSON.stringify(payload), { status: 200, headers: { 'Content-Type': 'application/json' } });
}

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

describe('WorkTasksPage', () => {
  it('shows role queues, report evidence and available task action', async () => {
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes('/api/enterprise/work-tasks/worktask-1')) return Promise.resolve(response(task));
      if (url.includes('/api/enterprise/work-tasks')) return Promise.resolve(response({ items: [{ ...task, evidence: [], events: [] }], queues: [{ business_role: 'logistics_exception_specialist', label: '物流异常专员', pending: 1, in_progress: 0, waiting_input: 0, review: 0, overdue: 1, total_open: 1 }] }));
      return Promise.resolve(new Response('{}', { status: 404 }));
    }));

    render(<I18nProvider><WorkTasksPage currentUser={supervisor} onLogout={vi.fn()} /></I18nProvider>);

    expect(await screen.findAllByText('核对物流异常并补充承运商回执')).not.toHaveLength(0);
    expect(screen.getAllByText(/物流异常专员/).length).toBeGreaterThan(0);
    expect(screen.getByText('物流连接器超时')).toBeTruthy();
    expect(screen.getByRole('button', { name: '开始处理' })).toBeTruthy();
    expect(screen.getByRole('link', { name: /执行异常/ }).getAttribute('href')).toBe('/enterprise/business-resources');
  });
});

