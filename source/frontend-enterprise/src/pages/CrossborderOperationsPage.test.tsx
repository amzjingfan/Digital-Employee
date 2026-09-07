// @vitest-environment jsdom

import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { EnterpriseAuthUser } from '@/auth';
import { I18nProvider } from '@/i18n';

import CrossborderOperationsPage from './CrossborderOperationsPage';

const supervisor: EnterpriseAuthUser = {
  id: 'joe-id',
  tenant_id: 'tenant_demo',
  username: 'Joe',
  role: 'member',
  business_role: 'operations_supervisor',
  enterprise_permissions: { work_tasks: ['view', 'create'] },
};

const afterSalesCase = {
  id: 'case-1', case_key: 'CASE-US-001', store_resource_id: 'store-1', store_code: 'AMZ-US',
  platform: 'Amazon', marketplace_country: 'US', language: 'en-US', order_reference_masked: 'AM***2222',
  status: 'waiting_approval', category: 'return_refund', risk_level: 'high', needs_human: false,
  task_id: 'task-1', approval_request_id: 'approval-1', approval_status: 'pending',
  order_snapshot: { order_status: 'shipped', logistics_status: 'stalled' },
  citations: [{ source_id: 'kb-1', version: '3.0', scope: 'tenant_demo/store:AMZ-US' }],
  recommendation: { action: 'refund' }, draft_reply: 'A reviewed refund reply draft.', root_cause: null,
  follow_up_task_ids: [], version: 3, created_at: '2026-09-02T00:00:00Z', updated_at: '2026-09-02T01:00:00Z',
  events: [{ id: 'event-1', event_type: 'resolution_drafted', actor_type: 'human', actor_business_role: 'after_sales_specialist', from_status: 'classified', to_status: 'waiting_approval', detail: {}, occurred_at: '2026-09-02T01:00:00Z' }],
};

const anomaly = {
  id: 'anomaly-1', fingerprint: 'sha256:demo', carrier_resource_id: 'carrier-1', carrier_code: 'UPS-US',
  store_resource_id: 'store-1', platform: 'Amazon', order_reference_masked: 'AM***4444', status_event_id: 'evt-1',
  shipment_status: 'IN_TRANSIT', anomaly_type: 'stalled', status: 'clustered', severity: 'critical', customer_impact: 'high',
  cluster_key: 'cluster:demo', dimensions: { warehouse: 'ONT8', country: 'US' }, evidence: { days_in_transit: 9 },
  escalation_targets: [], follow_up_task_ids: [], task_id: 'task-2', occurrence_count: 2,
  deadline_at: '2026-09-02T04:00:00Z', first_observed_at: '2026-09-01T00:00:00Z', last_observed_at: '2026-09-02T01:00:00Z',
  version: 1, updated_at: '2026-09-02T01:00:00Z', events: [],
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

describe('CrossborderOperationsPage', () => {
  it('renders aggregate gates, case lineage, logistics deduplication and degradation status', async () => {
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes('/crossborder/overview')) return Promise.resolve(response({ after_sales_open: 1, after_sales_needs_human: 0, logistics_open: 1, logistics_high_risk: 1, degraded_dependencies: 1, generated_at: '2026-09-02T01:00:00Z' }));
      if (url.includes('/crossborder/integration-health')) return Promise.resolve(response([{ id: 'health-1', dependency_key: 'amazon-orders-api', display_name: 'Amazon Orders API', domain: 'orders', status: 'degraded', effective_status: 'degraded', reason_code: 'rate_limited', message: 'Requests are throttled.', recovery_hint: 'Retry with backoff.', source: 'health_check', observed_at: '2026-09-02T01:00:00Z', stale_after_seconds: 900, version: 2, updated_at: '2026-09-02T01:00:00Z', events: [] }]));
      if (url.includes('/api/enterprise/business-resources')) return Promise.resolve(response([{ id: 'store-1', resource_type: 'store', code: 'AMZ-US', name: 'Amazon US', status: 'active' }, { id: 'carrier-1', resource_type: 'carrier', code: 'UPS-US', name: 'UPS US', status: 'active' }]));
      if (url.includes('/crossborder/after-sales/case-1')) return Promise.resolve(response(afterSalesCase));
      if (url.includes('/crossborder/after-sales')) return Promise.resolve(response([{ ...afterSalesCase, events: [] }]));
      if (url.includes('/crossborder/logistics/anomaly-1')) return Promise.resolve(response(anomaly));
      if (url.includes('/crossborder/logistics')) return Promise.resolve(response([{ ...anomaly, events: [] }]));
      return Promise.resolve(new Response('{}', { status: 404 }));
    }));

    const user = userEvent.setup();
    render(<I18nProvider><CrossborderOperationsPage currentUser={supervisor} onLogout={vi.fn()} /></I18nProvider>);

    expect(await screen.findByText('CASE-US-001')).toBeTruthy();
    expect(screen.getByText(/订单标识仅保存摘要与掩码/)).toBeTruthy();
    expect(screen.getByRole('link', { name: '打开统一任务' }).getAttribute('href')).toContain('task-1');
    expect(screen.getByText('resolution_drafted · after_sales_specialist')).toBeTruthy();
    expect(screen.getByText('A reviewed refund reply draft.')).toBeTruthy();

    await user.click(screen.getByRole('button', { name: '物流异常' }));
    expect(await screen.findAllByText('AM***4444')).not.toHaveLength(0);
    expect(screen.getByText(/重复 2 次/)).toBeTruthy();
    expect(screen.getByRole('button', { name: '升级跨岗位' })).toBeTruthy();

    await user.click(screen.getByRole('button', { name: '依赖与降级' }));
    expect(await screen.findByText('Amazon Orders API')).toBeTruthy();
    expect(screen.getByText('Requests are throttled.')).toBeTruthy();
  });
});
