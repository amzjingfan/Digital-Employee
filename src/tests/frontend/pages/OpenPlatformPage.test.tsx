// @vitest-environment jsdom

import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { notify } from '@/components/ui';
import { I18nProvider } from '@/i18n';
import OpenPlatformPage from '@/pages/OpenPlatformPage';
import type { AgentProfileRead } from '@/types';

const CREATE_PATHS = [
  ['knowledge', '创建开放知识库', '/enterprise/knowledge/new'],
  ['general-skills', '创建开放 Skill', '/enterprise/general-skills/new?scope=gallery'],
  ['skills', '创建开放 SOP', '/enterprise/skills/distill?mode=create&agent_id=overall%2F1%3F'],
  ['tools', '创建开放工具', '/enterprise/tools/new'],
] as const;

function overallAgent(id: string): AgentProfileRead {
  return {
    id,
    tenant_id: 'tenant_demo',
    name: '开放广场',
    is_overall: true,
    status: 'active',
    metadata: {},
    resources: [],
    created_at: '2026-09-23T00:00:00Z',
    updated_at: '2026-09-23T00:00:00Z',
  };
}

function stubCatalogFetch(agents: AgentProfileRead[]) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => ({
    ok: true,
    status: 200,
    statusText: 'OK',
    text: async () => JSON.stringify(String(input).includes('/api/enterprise/agents?') ? agents : []),
  } as Response));
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

function LocationEcho() {
  const location = useLocation();
  return <div data-testid="location">{`${location.pathname}${location.search}`}</div>;
}

function renderPage(kind: string, isAdmin: boolean) {
  return render(
    <I18nProvider>
      <MemoryRouter initialEntries={[`/enterprise/platform/${kind}`]}>
        <Routes>
          <Route
            path="/enterprise/platform/:kind"
            element={
              <OpenPlatformPage
                isAdmin={isAdmin}
                currentUser={{
                  id: 'user-1',
                  username: 'tester',
                  tenant_id: 'tenant_demo',
                  role: isAdmin ? 'admin' : 'member',
                }}
              />
            }
          />
          <Route path="*" element={<LocationEcho />} />
        </Routes>
      </MemoryRouter>
    </I18nProvider>,
  );
}

async function waitForCatalogLoad(fetchMock: ReturnType<typeof stubCatalogFetch>) {
  await waitFor(() => expect(fetchMock.mock.calls.some(([input]) =>
    String(input).includes('/api/enterprise/tools?'))).toBe(true));
  await waitFor(() => expect(document.querySelector('[aria-busy="true"]')).toBeNull());
}

afterEach(() => {
  cleanup();
  window.localStorage.clear();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe('OpenPlatformPage creation actions', () => {
  it.each(CREATE_PATHS)('opens %s creation in overall scope for an administrator', async (kind, label, destination) => {
    const fetchMock = stubCatalogFetch([overallAgent('overall/1?')]);
    const dispatch = vi.spyOn(window, 'dispatchEvent');
    renderPage(kind, true);
    await waitForCatalogLoad(fetchMock);

    await userEvent.setup().click(screen.getByRole('button', { name: label }));

    expect(screen.getByTestId('location').textContent).toBe(destination);
    expect(window.localStorage.getItem('ultrarag_enterprise_agent_scope')).toBe('overall/1?');
    expect(dispatch).toHaveBeenCalledWith(expect.objectContaining({
      type: 'ultrarag-enterprise-agent-scope-change',
      detail: { agentId: 'overall/1?' },
    }));
  });

  it.each(CREATE_PATHS)('shows %s creation to a member but denies publishing', async (kind, label) => {
    const fetchMock = stubCatalogFetch([overallAgent('overall-1')]);
    const error = vi.spyOn(notify, 'error');
    window.localStorage.setItem('ultrarag_enterprise_agent_scope', 'employee-1');
    renderPage(kind, false);
    await waitForCatalogLoad(fetchMock);

    await userEvent.setup().click(screen.getByRole('button', { name: label }));

    expect(error).toHaveBeenCalledWith('仅管理员可以创建开放广场内容');
    expect(window.localStorage.getItem('ultrarag_enterprise_agent_scope')).toBe('employee-1');
    expect(screen.queryByTestId('location')).toBeNull();
  });

  it('does not enter creation without an overall agent', async () => {
    const fetchMock = stubCatalogFetch([]);
    const error = vi.spyOn(notify, 'error');
    renderPage('knowledge', true);
    await waitForCatalogLoad(fetchMock);

    await userEvent.setup().click(screen.getByRole('button', { name: '创建开放知识库' }));

    expect(error).toHaveBeenCalledWith('暂时无法找到开放广场');
    expect(window.localStorage.getItem('ultrarag_enterprise_agent_scope')).toBeNull();
    expect(screen.queryByTestId('location')).toBeNull();
  });

  it('does not show a creation button for the employee plaza', async () => {
    const fetchMock = stubCatalogFetch([overallAgent('overall-1')]);
    renderPage('agents', true);
    await waitForCatalogLoad(fetchMock);

    expect(screen.queryByRole('button', { name: /^创建开放/ })).toBeNull();
  });
});
