// @vitest-environment jsdom

import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { EnterpriseAuthUser } from '@/auth';
import { I18nProvider } from '@/i18n';

import OffsiteChannelAssetsPanel from './OffsiteChannelAssetsPanel';

const supervisor: EnterpriseAuthUser = {
  id: 'supervisor',
  tenant_id: 'tenant_demo',
  username: 'Supervisor',
  role: 'member',
  business_role: 'operations_supervisor',
  enterprise_permissions: { work_tasks: ['view', 'create'] },
};

const store = { id: 'store-1', code: 'AMZ-US', name: 'Amazon US', status: 'active' };

const asset = {
  id: 'channel-1',
  tenant_id: 'tenant_demo',
  brand_key: 'brand.demo',
  store_resource_id: 'store-1',
  store_code: 'AMZ-US',
  asset_type: 'deal_site',
  canonical_name: 'Example Deals',
  stable_external_ref: 'https://deals.example/',
  region: 'US',
  language: 'en-US',
  categories: ['home'],
  tier: 'unassigned',
  lifecycle_status: 'discovered',
  effective_lifecycle_status: 'discovered',
  owner_user_id: 'supervisor',
  required_evidence_types: ['identity', 'audience_fit', 'terms', 'fees', 'contact_basis'],
  missing_required_evidence: ['identity', 'audience_fit', 'terms', 'fees', 'contact_basis'],
  expired_required_evidence: [],
  freshness_status: 'missing',
  execution_guard: {
    status: 'blocked',
    reasons: ['lifecycle_status:discovered', 'missing_evidence:identity'],
    evaluated_at: '2026-09-08T08:00:00Z',
  },
  last_verified_at: null,
  reviewed_by_user_id: null,
  review_reason: null,
  reviewed_at: null,
  version: 0,
  created_at: '2026-09-08T08:00:00Z',
  updated_at: '2026-09-08T08:00:00Z',
  evidence: [],
  events: [],
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

describe('OffsiteChannelAssetsPanel', () => {
  it('shows evidence gaps and makes the no-external-action boundary explicit', async () => {
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes('/channels/channel-1')) return Promise.resolve(response(asset));
      if (url.includes('/api/v1/offsite/channels')) return Promise.resolve(response([{ ...asset, evidence: [] }]));
      return Promise.resolve(new Response('{}', { status: 404 }));
    }));

    const user = userEvent.setup();
    render(<I18nProvider><OffsiteChannelAssetsPanel currentUser={supervisor} stores={[store]} /></I18nProvider>);

    expect(await screen.findAllByText('Example Deals')).not.toHaveLength(0);
    expect(screen.getByText(/本页面只管理内部资产、证据和复核结论/)).toBeTruthy();
    expect(screen.getByText(/missing_evidence:identity/)).toBeTruthy();
    expect(screen.getAllByText(/identity、audience_fit、terms、fees、contact_basis/)).toHaveLength(2);

    await user.click(screen.getByRole('button', { name: '追加证据' }));
    expect(screen.getByRole('heading', { name: '追加渠道证据' })).toBeTruthy();
    expect(screen.getByPlaceholderText(/不得含邮箱、电话、地址或秘密/)).toBeTruthy();
  });

  it('sends an Idempotency-Key when creating a discovered channel lead', async () => {
    let created = false;
    const fetchMock = vi.fn((input: RequestInfo | URL, options?: RequestInit) => {
      const url = String(input);
      if (options?.method === 'POST') {
        const headers = new Headers(options.headers);
        expect(headers.get('Idempotency-Key')).toMatch(/^offsite-channel-create:/);
        expect(headers.get('Content-Type')).toBe('application/json');
        const body = JSON.parse(String(options.body)) as Record<string, unknown>;
        expect(body.stable_external_ref).toBe('https://deals.example/');
        created = true;
        return Promise.resolve(response(asset));
      }
      if (url.includes('/channels/channel-1')) return Promise.resolve(response(asset));
      if (url.includes('/api/v1/offsite/channels')) {
        return Promise.resolve(response(created ? [{ ...asset, evidence: [] }] : []));
      }
      return Promise.resolve(new Response('{}', { status: 404 }));
    });
    vi.stubGlobal('fetch', fetchMock);

    const user = userEvent.setup();
    render(<I18nProvider><OffsiteChannelAssetsPanel currentUser={supervisor} stores={[store]} /></I18nProvider>);
    expect(await screen.findByText('暂无渠道资产')).toBeTruthy();
    await user.click(screen.getByRole('button', { name: '新增线索' }));
    await user.type(screen.getByPlaceholderText('渠道规范名称'), 'Example Deals');
    await user.type(
      screen.getByPlaceholderText('稳定 URL 或外部 ID（不得含 token）'),
      'https://deals.example/',
    );
    await user.click(screen.getByRole('button', { name: '保存线索' }));

    expect(await screen.findAllByText('Example Deals')).not.toHaveLength(0);
    expect(fetchMock).toHaveBeenCalled();
  });
});
