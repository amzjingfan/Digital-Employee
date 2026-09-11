// @vitest-environment jsdom

import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { EnterpriseAuthUser } from '@/auth';
import { I18nProvider } from '@/i18n';

import AdvertisingGovernancePage from '@/pages/AdvertisingGovernancePage';

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

describe('AdvertisingGovernancePage', () => {
  it('shows constrained recommendations, review tasks and immutable policy decisions', async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes('/overview')) return Promise.resolve(response({ recommendations_ready: 1, recommendations_blocked: 0, actions_waiting_approval: 0, effectiveness_reviews_pending: 3, automation_policies_active: 1, kill_switches_engaged: 1 }));
      if (url.includes('/business-resources')) return Promise.resolve(response([{ id: 'ads-1', resource_type: 'ad_account', code: 'ADS-US', name: 'Amazon Ads US' }, { id: 'store-1', resource_type: 'store', code: 'AMZ-US', name: 'Amazon US' }]));
      if (url.includes('/recommendations')) return Promise.resolve(response([{ id: 'rec-1', recommendation_key: 'AD-REC-001', campaign_id: 'CAMPAIGN-1001', product_key: 'PRODUCT-1001', metrics: { acos: 0.2, roas: 5, ctr: 0.0025, conversion_rate: 0.04, days_of_cover: 95 }, constraints: {}, findings: [{ code: 'ctr_below_minimum', severity: 'medium', gate: 'warn' }], recommendation: { note: '在经营约束内降低预算波动。', external_write_executed: false }, proposed_action_type: 'change_daily_budget', proposed_action_payload: { daily_budget: 50 }, risk_level: 'medium', status: 'ready', input_digest: 'sha256:rec', task_id: 'task-ad', linked_task_ids: ['task-design'], version: 0 }]));
      if (url.includes('/effect-follow-ups')) return Promise.resolve(response([{ id: 'effect-7', horizon_days: 7, baseline: { acos: 0.2, roas: 5 }, task_id: 'task-effect', status: 'pending', due_at: '2026-09-09T00:00:00Z' }]));
      if (url.includes('/automation-policies')) return Promise.resolve(response([{ id: 'policy-1', resource_id: 'ads-1', action_type: 'change_daily_budget', status: 'active', rollout_percent: 10, max_single_value: 100, max_daily_value: 300, max_risk_level: 'medium', approval_required: true, kill_switch_engaged: true, revision: 2 }]));
      if (url.includes('/automation-usage')) return Promise.resolve(response([{ id: 'usage-1', policy_revision: 2, action_type: 'change_daily_budget', cohort_bucket: 7, quantitative_value: 50, decision: 'blocked', reason: 'kill_switch_engaged', created_at: '2026-09-02T00:00:00Z' }]));
      if (url.includes('/pdca/search-term-runs')) return Promise.resolve(response([{ id: 'pdca-run-1', attempt: 1, mode: 'rules_only', state: 'succeeded', target_acos: '0.3', currency: 'USD', source_row_count: 3, fact_count: 2, action_count: 2, quality_score: 70, mapping_version: 'amazon-search-term-csv.v1', rule_version: 'pdca-search-term-rules.v1', summary: { spend: '42.5', sales: '100', orders: 2, acos: { value: '0.425', reason: null } }, warnings: ['Product attribution evidence was not supplied'], external_execution_allowed: false, top_actions: [{ id: 'action-1', campaign_id: 'CAMPAIGN-1001', ad_group_id: 'ADGROUP-1', search_term: 'synthetic query', match_type: 'broad', action_type: 'manual_review', priority: 'high', must_do_score: 88, rationale: 'Synthetic evidence requires review.', execution_hint: 'Advice only: this system did not execute a write.', status: 'suggested', external_execution_allowed: false }], created_at: '2026-09-08T00:00:00Z' }]));
      return Promise.resolve(new Response('{}', { status: 404 }));
    });
    vi.stubGlobal('fetch', fetchMock);

    const user = userEvent.setup();
    render(<I18nProvider><AdvertisingGovernancePage currentUser={supervisor} onLogout={vi.fn()} /></I18nProvider>);

    expect(await screen.findByText('Amazon 搜索词规则诊断')).toBeTruthy();
    expect(screen.getByText(/rules_only · advice_only/)).toBeTruthy();
    expect(screen.getByText(/synthetic query · manual_review/)).toBeTruthy();
    expect(screen.getByText(/did not execute a write/)).toBeTruthy();
    expect(screen.getByText(/自动化策略不能绕过人工审批/)).toBeTruthy();
    expect(fetchMock.mock.calls.some(([input]) => {
      const url = String(input);
      return url.includes('/pdca/search-term-runs') &&
        url.includes('ad_account_resource_id=ads-1') &&
        url.includes('store_resource_id=store-1');
    })).toBe(true);

    await user.click(screen.getByRole('button', { name: '巡检建议' }));
    expect(await screen.findByText('CAMPAIGN-1001')).toBeTruthy();
    expect(screen.getByRole('link', { name: '联动任务 1' }).getAttribute('href')).toContain('task-design');

    await user.click(screen.getByRole('button', { name: '效果复盘' }));
    expect(await screen.findByText('7 天复盘')).toBeTruthy();
    expect(screen.getByText(/仅在外部动作确认成功后建单/)).toBeTruthy();

    await user.click(screen.getByRole('button', { name: '自动化门禁' }));
    expect((await screen.findAllByText('change_daily_budget · rev 2')).length).toBe(2);
    expect(screen.getByText(/灰度 10%/)).toBeTruthy();
    expect(screen.getByText(/kill_switch_engaged/)).toBeTruthy();
  });

  it('does not load or show PDCA history for a non-advertising role', async () => {
    const listingUser: EnterpriseAuthUser = {
      ...supervisor,
      id: 'listing-id',
      business_role: 'listing_compliance_specialist',
    };
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes('/overview')) return Promise.resolve(response({ recommendations_ready: 0, recommendations_blocked: 0, actions_waiting_approval: 0, effectiveness_reviews_pending: 0, automation_policies_active: 0, kill_switches_engaged: 0 }));
      if (url.includes('/business-resources')) return Promise.resolve(response([{ id: 'ads-1', resource_type: 'ad_account', code: 'ADS-US', name: 'Amazon Ads US' }]));
      return Promise.resolve(response([]));
    });
    vi.stubGlobal('fetch', fetchMock);

    render(<I18nProvider><AdvertisingGovernancePage currentUser={listingUser} onLogout={vi.fn()} /></I18nProvider>);

    await waitFor(() => expect(screen.queryByText('加载中…')).toBeNull());
    expect(screen.queryByRole('button', { name: '搜索词 PDCA' })).toBeNull();
    expect(fetchMock.mock.calls.some(([input]) => String(input).includes('/pdca/search-term-runs'))).toBe(false);
  });
});
