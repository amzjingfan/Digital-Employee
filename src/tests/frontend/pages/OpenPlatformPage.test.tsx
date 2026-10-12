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
  ['knowledge', '创建开放知识库', '/enterprise/knowledge/new?scope=gallery'],
  ['general-skills', '创建开放 Skill', '/enterprise/general-skills/new?scope=gallery'],
  ['skills', '创建开放 SOP', '/enterprise/skills/distill?mode=create&agent_id=overall%2F1%3F'],
  ['tools', '创建开放工具', '/enterprise/tools/new?scope=gallery'],
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
      <MemoryRouter initialEntries={[kind === 'root' ? '/enterprise/platform' : `/enterprise/platform/${kind}`]}>
        <Routes>
          <Route
            path="/enterprise/platform"
            element={<OpenPlatformPage isAdmin={isAdmin} />}
          />
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

function stubGroupedSkills(grouped: boolean, slugs = ['hr-one', 'hr-two']) {
  let folderName = 'HR toolkit';
  const rows = slugs.map((slug) => ({
    id: slug,
    tenant_id: 'tenant_demo',
    slug,
    name: slug,
    description: `${slug} description`,
    status: 'published',
    metadata: grouped ? { import_group_id: 'group-1', import_group_name: folderName } : {},
  }));
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    if (String(input).includes('/group/rename') && init?.method === 'POST') {
      folderName = JSON.parse(String(init.body)).name;
    }
    return ({
    ok: true,
    status: 200,
    statusText: 'OK',
    text: async () => JSON.stringify(init?.method === 'POST'
      ? rows.map((row) => ({ ...row, metadata: { import_group_id: 'group-2', import_group_name: 'HR toolkit' } }))
      : String(input).includes('/api/enterprise/agents?') ? [overallAgent('overall-1')]
      : String(input).includes('/api/enterprise/general-skills?')
        ? rows.map((row) => ({ ...row, metadata: grouped
          ? { import_group_id: 'group-1', import_group_name: folderName } : {} })) : []),
    } as Response);
  });
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

describe('OpenPlatformPage skill folders', () => {
  it('keeps folder skills together on the plaza overview', async () => {
    const fetchMock = stubGroupedSkills(true);
    renderPage('root', false);
    await waitForCatalogLoad(fetchMock);

    expect(screen.getByRole('button', { name: /HR toolkit.*2/ })).toBeTruthy();
    expect(screen.queryByRole('button', { name: /hr-one.*description/ })).toBeNull();
    expect(screen.queryByRole('button', { name: /重命名文件夹/ })).toBeNull();
  });

  it('shows a folder card and expands its individual skills', async () => {
    const fetchMock = stubGroupedSkills(true);
    renderPage('general-skills', false);
    await waitForCatalogLoad(fetchMock);

    expect(screen.getByRole('button', { name: /HR toolkit.*2/ })).toBeTruthy();
    expect(screen.queryByRole('button', { name: /hr-one.*description/ })).toBeNull();
    await userEvent.setup().click(screen.getByRole('button', { name: /HR toolkit.*2/ }));
    expect(screen.getByRole('button', { name: /hr-one.*description/ })).toBeTruthy();
    expect(screen.getByRole('button', { name: /hr-two.*description/ })).toBeTruthy();
  });

  it('keeps a single grouped skill inside a folder', async () => {
    const fetchMock = stubGroupedSkills(true, ['hr-one']);
    renderPage('general-skills', false);
    await waitForCatalogLoad(fetchMock);
    expect(screen.getByRole('button', { name: /HR toolkit.*1/ })).toBeTruthy();
    expect(screen.queryByRole('button', { name: /hr-one.*description/ })).toBeNull();
    await userEvent.setup().click(screen.getByRole('button', { name: /HR toolkit.*1/ }));
    expect(screen.getByRole('button', { name: /hr-one.*description/ })).toBeTruthy();
  });

  it('lets an administrator group just one skill', async () => {
    const fetchMock = stubGroupedSkills(false, ['hr-one']);
    renderPage('general-skills', true);
    await waitForCatalogLoad(fetchMock);
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: '整理已有 Skill' }));
    await user.click(screen.getByRole('checkbox', { name: '选择 hr-one' }));
    await user.type(screen.getByRole('textbox', { name: '文件夹名称' }), 'Solo');
    await user.click(screen.getByRole('button', { name: '保存分组' }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/api/enterprise/general-skills/group'),
      expect.objectContaining({ method: 'POST', body: expect.stringContaining('"skill_ids":["hr-one"]') }),
    ));
  });

  it('lets an administrator rename a folder in place', async () => {
    const fetchMock = stubGroupedSkills(true, ['hr-one']);
    renderPage('general-skills', true);
    await waitForCatalogLoad(fetchMock);
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: '重命名文件夹 HR toolkit' }));
    const input = screen.getByRole('textbox', { name: '新文件夹名称' });
    await user.clear(input);
    await user.type(input, 'Updated');
    await user.click(screen.getByRole('button', { name: '保存名称' }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/api/enterprise/general-skills/group/rename'),
      expect.objectContaining({ method: 'POST', body: expect.stringContaining('"group_id":"group-1"') }),
    ));
    await waitFor(() => expect(screen.getByRole('button', { name: /Updated.*1/ })).toBeTruthy());
  });

  it('lets an administrator group selected existing skills', async () => {
    const fetchMock = stubGroupedSkills(false);
    renderPage('general-skills', true);
    await waitForCatalogLoad(fetchMock);
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: '整理已有 Skill' }));
    await user.click(screen.getByRole('checkbox', { name: '选择 hr-one' }));
    await user.click(screen.getByRole('checkbox', { name: '选择 hr-two' }));
    await user.type(screen.getByRole('textbox', { name: '文件夹名称' }), 'HR toolkit');
    await user.click(screen.getByRole('button', { name: '保存分组' }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/api/enterprise/general-skills/group'),
      expect.objectContaining({ method: 'POST' }),
    ));
  });
});
