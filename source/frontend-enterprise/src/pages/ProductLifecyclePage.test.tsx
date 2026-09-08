// @vitest-environment jsdom

import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { EnterpriseAuthUser } from '@/auth';
import { I18nProvider } from '@/i18n';

import ProductLifecyclePage from './ProductLifecyclePage';

const supervisor: EnterpriseAuthUser = {
  id: 'joe-id',
  tenant_id: 'tenant_demo',
  username: 'Joe',
  role: 'member',
  business_role: 'operations_supervisor',
  enterprise_permissions: { work_tasks: ['view', 'create'] },
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

describe('ProductLifecyclePage', () => {
  it('renders versioned listing, creative, procurement and launch gates', async () => {
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL, options?: RequestInit) => {
      const url = String(input);
      if (options?.method === 'POST') return Promise.resolve(response({}));
      if (url.includes('/overview')) return Promise.resolve(response({ published_rule_sets: 1, blocked_listing_checks: 0, creative_assets_waiting_review: 1, procurement_recommendations_waiting_review: 1, launch_gates_blocked: 0, launch_gates_waiting_approval: 1, open_quality_issues: 1 }));
      if (url.includes('/business-resources')) return Promise.resolve(response([{ id: 'store-1', resource_type: 'store', code: 'AMZ-US', name: 'Amazon US' }, { id: 'supplier-1', resource_type: 'supplier', code: 'SUP-1', name: 'Supplier' }]));
      if (url.includes('/listing-rules')) return Promise.resolve(response([{ id: 'rule-1', version: '2026.09.1', platform: 'Amazon', marketplace: 'US', category: 'Electronics', status: 'published', content_digest: 'sha256:rule', effective_at: '2026-09-01T00:00:00Z' }]));
      if (url.includes('/listing-checks')) return Promise.resolve(response([{ id: 'check-1', check_key: 'CHECK-1', product_key: 'PRODUCT-DEMO-1001', sku: 'SKU-DEMO-1001', rule_version: '2026.09.1', sku_fact_version: 'facts-v3', gate_status: 'pass', findings: [], task_id: 'task-listing', created_at: '2026-09-02T00:00:00Z' }]));
      if (url.includes('/creative-briefs')) return Promise.resolve(response([{ id: 'brief-1', brief_key: 'BRIEF-1', product_key: 'PRODUCT-DEMO-1001', language: 'en-US', required_assets: ['main_image'], status: 'in_progress', task_id: 'task-brief' }]));
      if (url.includes('/creative-assets')) return Promise.resolve(response([{ id: 'asset-1', asset_key: 'ASSET-MAIN', version: 1, product_key: 'PRODUCT-DEMO-1001', asset_type: 'main_image', file_digest: 'sha256:asset', status: 'approved', required_human_approval: true, checks: {}, created_at: '2026-09-02T00:00:00Z' }]));
      if (url.includes('/creative-qc')) return Promise.resolve(response([]));
      if (url.includes('/creative-evidence')) return Promise.resolve(response([]));
      if (url.includes('/creative-deliveries')) return Promise.resolve(response([]));
      if (url.includes('/creative-generations')) return Promise.resolve(response([]));
      if (url.includes('/procurement-recommendations')) return Promise.resolve(response([{ id: 'proc-1', recommendation_key: 'PROC-1', product_key: 'PRODUCT-DEMO-1001', sku: 'SKU-DEMO-1001', recommended_quantity: 300, estimated_landed_cost: 2850, lead_time_days: 15, formula: 'ceil_to_MOQ(net_need)', risk_level: 'low', risk_reasons: [], status: 'reviewed', task_id: 'task-proc' }]));
      if (url.includes('/launch-gates')) return Promise.resolve(response([{ id: 'gate-1', launch_key: 'LAUNCH-1', product_key: 'PRODUCT-DEMO-1001', sku: 'SKU-DEMO-1001', status: 'waiting_approval', blockers: [], evidence_digest: 'sha256:gate', approval_request_id: 'approval-1', approval_status: 'pending', task_id: 'task-gate', version: 1 }]));
      if (url.includes('/quality-issues')) return Promise.resolve(response([{ id: 'quality-1', source_case_id: 'case-1', product_key: 'SKU-DEMO-1001', category: 'damaged', root_cause: 'Packaging protection failed.', task_ids: ['task-p', 'task-d', 'task-l'], status: 'open', created_at: '2026-09-02T00:00:00Z' }]));
      return Promise.resolve(new Response('{}', { status: 404 }));
    }));

    const user = userEvent.setup();
    render(<I18nProvider><ProductLifecyclePage currentUser={supervisor} onLogout={vi.fn()} /></I18nProvider>);

    expect(await screen.findByText('Amazon US · Electronics')).toBeTruthy();
    expect(screen.getByText(/不直接发布 Listing、素材或采购单/)).toBeTruthy();
    expect(screen.getByRole('link', { name: '打开任务' }).getAttribute('href')).toContain('task-listing');

    await user.click(screen.getByRole('button', { name: '采购建议' }));
    expect(await screen.findByText(/建议 300 件/)).toBeTruthy();
    expect(screen.getByText('ceil_to_MOQ(net_need)')).toBeTruthy();

    await user.click(screen.getByRole('button', { name: '新品门禁' }));
    expect(await screen.findByText('SKU-DEMO-1001 · LAUNCH-1')).toBeTruthy();
    expect(screen.getByText('审批 pending')).toBeTruthy();

    await user.click(screen.getByRole('button', { name: '质量闭环' }));
    expect(await screen.findByText('Packaging protection failed.')).toBeTruthy();
    expect(screen.getByText(/已创建 3 个跨岗位任务/)).toBeTruthy();
  });
});
