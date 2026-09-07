// @vitest-environment jsdom

import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { EnterpriseAuthUser } from '@/auth';
import { I18nProvider } from '@/i18n';

import AdvertisingGovernancePage from './AdvertisingGovernancePage';

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
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes('/overview')) return Promise.resolve(response({ recommendations_ready: 1, recommendations_blocked: 0, actions_waiting_approval: 0, effectiveness_reviews_pending: 3, automation_policies_active: 1, kill_switches_engaged: 1 }));
      if (url.includes('/business-resources')) return Promise.resolve(response([{ id: 'ads-1', resource_type: 'ad_account', code: 'ADS-US', name: 'Amazon Ads US' }, { id: 'store-1', resource_type: 'store', code: 'AMZ-US', name: 'Amazon US' }]));
      if (url.includes('/recommendations')) return Promise.resolve(response([{ id: 'rec-1', recommendation_key: 'AD-REC-001', campaign_id: 'CAMPAIGN-1001', product_key: 'PRODUCT-1001', metrics: { acos: 0.2, roas: 5, ctr: 0.0025, conversion_rate: 0.04, days_of_cover: 95 }, constraints: {}, findings: [{ code: 'ctr_below_minimum', severity: 'medium', gate: 'warn' }], recommendation: { note: '在经营约束内降低预算波动。', external_write_executed: false }, proposed_action_type: 'change_daily_budget', proposed_action_payload: { daily_budget: 50 }, risk_level: 'medium', status: 'ready', input_digest: 'sha256:rec', task_id: 'task-ad', linked_task_ids: ['task-design'], version: 0 }]));
      if (url.includes('/effect-follow-ups')) return Promise.resolve(response([{ id: 'effect-7', horizon_days: 7, baseline: { acos: 0.2, roas: 5 }, task_id: 'task-effect', status: 'pending', due_at: '2026-09-09T00:00:00Z' }]));
      if (url.includes('/automation-policies')) return Promise.resolve(response([{ id: 'policy-1', resource_id: 'ads-1', action_type: 'change_daily_budget', status: 'active', rollout_percent: 10, max_single_value: 100, max_daily_value: 300, max_risk_level: 'medium', approval_required: true, kill_switch_engaged: true, revision: 2 }]));
      if (url.includes('/automation-usage')) return Promise.resolve(response([{ id: 'usage-1', policy_revision: 2, action_type: 'change_daily_budget', cohort_bucket: 7, quantitative_value: 50, decision: 'blocked', reason: 'kill_switch_engaged', created_at: '2026-09-02T00:00:00Z' }]));
      return Promise.resolve(new Response('{}', { status: 404 }));
    }));

    const user = userEvent.setup();
    render(<I18nProvider><AdvertisingGovernancePage currentUser={supervisor} onLogout={vi.fn()} /></I18nProvider>);

    expect(await screen.findByText('CAMPAIGN-1001')).toBeTruthy();
    expect(screen.getByText(/自动化策略不能绕过人工审批/)).toBeTruthy();
    expect(screen.getByRole('link', { name: '联动任务 1' }).getAttribute('href')).toContain('task-design');

    await user.click(screen.getByRole('button', { name: '效果复盘' }));
    expect(await screen.findByText('7 天复盘')).toBeTruthy();
    expect(screen.getByText(/仅在外部动作确认成功后建单/)).toBeTruthy();

    await user.click(screen.getByRole('button', { name: '自动化门禁' }));
    expect((await screen.findAllByText('change_daily_budget · rev 2')).length).toBe(2);
    expect(screen.getByText(/灰度 10%/)).toBeTruthy();
    expect(screen.getByText(/kill_switch_engaged/)).toBeTruthy();
  });
});
