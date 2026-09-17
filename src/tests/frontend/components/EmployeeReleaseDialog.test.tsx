// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { I18nProvider } from '@/i18n';
import type { AgentProfileRead, AgentReleaseRead } from '@/types';

import EmployeeReleaseDialog from '@/components/EmployeeReleaseDialog';

const agent: AgentProfileRead = {
  id: 'agent-logistics',
  tenant_id: 'tenant_demo',
  name: '物流异常专员',
  is_overall: false,
  status: 'active',
  release_state: 'draft',
  published_release_version: 1,
  metadata: {},
  resources: [],
  created_at: '2026-09-01T00:00:00Z',
  updated_at: '2026-09-01T00:00:00Z',
};

const release: AgentReleaseRead = {
  id: 'release-1',
  tenant_id: 'tenant_demo',
  agent_id: agent.id,
  version: 1,
  status: 'published',
  snapshot: {},
  snapshot_digest: 'sha256:12345678901234567890',
  created_by_user_id: 'user-admin',
  release_reason: 'Reviewed baseline',
  created_at: '2026-09-01T00:00:00Z',
  published_at: '2026-09-01T00:00:00Z',
};

function response(body: unknown): Response {
  return {
    ok: true,
    status: 200,
    statusText: 'OK',
    text: async () => JSON.stringify(body),
  } as Response;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe('EmployeeReleaseDialog', () => {
  it('loads history and requires a reason before publishing', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (init?.method === 'POST' && url.endsWith('/releases/publish')) return response(release);
      return response([release]);
    });
    vi.stubGlobal('fetch', fetchMock);
    const changed = vi.fn();

    render(
      <I18nProvider>
        <EmployeeReleaseDialog
          agent={agent}
          open
          canPublish
          onClose={() => {}}
          onChanged={changed}
        />
      </I18nProvider>,
    );

    expect(await screen.findByText('v1')).toBeTruthy();
    const button = screen.getByRole('button', { name: '发布生产版本' }) as HTMLButtonElement;
    expect(button.disabled).toBe(true);
    fireEvent.change(screen.getByLabelText('发布或回滚原因'), {
      target: { value: '发布审核后的岗位配置' },
    });
    expect(button.disabled).toBe(false);
    fireEvent.click(button);

    await waitFor(() => expect(changed).toHaveBeenCalledOnce());
    const post = fetchMock.mock.calls.find(([, init]) => init?.method === 'POST');
    expect(post?.[0]).toBe('/api/enterprise/agents/agent-logistics/releases/publish');
    expect(JSON.parse(String(post?.[1]?.body))).toEqual({
      tenant_id: 'tenant_demo',
      reason: '发布审核后的岗位配置',
    });
  });
});
