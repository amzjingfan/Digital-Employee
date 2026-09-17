// @vitest-environment jsdom

import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { I18nProvider } from '@/i18n';
import type { EnterpriseAuthUser } from '@/auth';

import BusinessResourcesPage from '@/pages/BusinessResourcesPage';

const supervisor: EnterpriseAuthUser = {
  id: 'joe-id',
  tenant_id: 'tenant_demo',
  username: 'Joe',
  role: 'member',
  business_role: 'operations_supervisor',
  enterprise_permissions: {
    business_resources: ['view', 'create', 'update', 'delete'],
  },
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

describe('BusinessResourcesPage', () => {
  it('renders scoped resources and prevents a supervisor from approving their own request', async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes('/api/enterprise/business-resources')) {
        return Promise.resolve(response([
          {
            id: 'store-1',
            tenant_id: 'tenant_demo',
            resource_type: 'store',
            code: 'AMZ-US',
            name: 'Amazon 美国旗舰店',
            status: 'active',
            access_level: 'operator',
            metadata: {},
            scopes: [{ business_role: 'listing_compliance_specialist', access_level: 'operator' }],
          },
        ]));
      }
      if (url.includes('/api/enterprise/business-approvals')) {
        return Promise.resolve(response([
          {
            id: 'approval-1',
            resource_id: 'store-1',
            resource_type: 'store',
            resource_name: 'Amazon 美国旗舰店',
            action_type: 'publish_listing',
            summary: '运营主管提交的发布申请',
            payload: { listing_id: 'A100' },
            status: 'pending',
            requester_user_id: 'joe-id',
            requester_business_role: 'operations_supervisor',
            requested_at: '2026-09-01T00:00:00Z',
            events: [],
          },
        ]));
      }
      return Promise.resolve(new Response('{}', { status: 404 }));
    });
    vi.stubGlobal('fetch', fetchMock);

    const user = userEvent.setup();
    render(<I18nProvider><BusinessResourcesPage currentUser={supervisor} /></I18nProvider>);

    expect(await screen.findByText('Amazon 美国旗舰店')).toBeTruthy();
    expect(screen.getByRole('button', { name: '新增业务资源' })).toBeTruthy();

    await user.click(screen.getByRole('button', { name: /审批记录/ }));
    expect(await screen.findByText('职责分离：不能审批自己的申请')).toBeTruthy();
    expect(screen.queryByRole('button', { name: '批准' })).toBeNull();
  });

  it('shows a redacted execution receipt and compensation control after success', async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes('/api/enterprise/business-resources')) {
        return Promise.resolve(response([]));
      }
      if (url.includes('/api/enterprise/business-approvals')) {
        return Promise.resolve(response([
          {
            id: 'approval-2',
            resource_id: 'store-1',
            resource_type: 'store',
            resource_name: 'Amazon 美国旗舰店',
            action_type: 'publish_listing',
            summary: 'Listing 专员提交的发布申请',
            payload: { listing_id: 'SKU-100' },
            status: 'approved',
            requester_user_id: 'listing-id',
            requester_business_role: 'listing_compliance_specialist',
            requested_at: '2026-09-01T00:00:00Z',
            events: [],
            execution: {
              id: 'execution-1',
              connector_type: 'amazon_sp_api',
              environment: 'sandbox',
              status: 'succeeded',
              attempt_count: 1,
              max_attempts: 3,
              external_operation_id: 'sandbox-execution-1',
              receipt: { provider: 'staffdeck-sandbox', accepted: true },
              events: [],
            },
          },
        ]));
      }
      return Promise.resolve(new Response('{}', { status: 404 }));
    });
    vi.stubGlobal('fetch', fetchMock);

    const user = userEvent.setup();
    render(<I18nProvider><BusinessResourcesPage currentUser={supervisor} /></I18nProvider>);

    await user.click(await screen.findByRole('button', { name: /执行与回执/ }));
    expect(await screen.findByText('执行成功')).toBeTruthy();
    expect(screen.getByText(/sandbox · amazon_sp_api/)).toBeTruthy();
    expect(screen.getByRole('button', { name: '发起补偿' })).toBeTruthy();
    expect(screen.getByText('查看脱敏回执')).toBeTruthy();
  });
});
