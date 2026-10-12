// @vitest-environment jsdom

import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, expect, it, vi } from 'vitest';

import GeneralSkillsPage from '@/pages/GeneralSkillsPage';
import { I18nProvider } from '@/i18n';
import { TooltipProvider } from '@/components/ui/tooltip';

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  window.localStorage.clear();
});

it('copies every available Skill in a plaza folder into the employee with one request', async () => {
  window.localStorage.setItem('ultrarag_enterprise_agent_scope', 'employee');
  const skills = ['recruitment', 'compensation'].map((slug) => ({
    id: slug,
    tenant_id: 'tenant_demo',
    slug,
    name: slug,
    description: slug,
    skill_markdown: `# ${slug}`,
    skill_files: [{ path: 'SKILL.md', content: `# ${slug}` }],
    metadata: { import_group_id: 'hr', import_group_name: '人事工具包' },
    status: 'published',
    capability_scope: 'general',
    permissions: {},
    runtime_config: {},
    created_at: '2026-10-12T00:00:00Z',
    updated_at: '2026-10-12T00:00:00Z',
  }));
  const posted: string[][] = [];
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const data = init?.method === 'POST' && url.includes('/resources/import')
      ? (() => {
        const ids = JSON.parse(String(init.body)).resource_ids as string[];
        posted.push(ids);
        return { imported: ids.map((resource_id) => ({ resource_id })), missing: [] };
      })()
      : url.includes('/agents?') ? [
        { id: 'gallery', tenant_id: 'tenant_demo', name: '开放广场', is_overall: true, status: 'active', metadata: {}, resources: [] },
        { id: 'employee', tenant_id: 'tenant_demo', name: '员工', is_overall: false, status: 'active', metadata: {}, resources: [] },
      ]
        : url.includes('agent_id=gallery') ? skills
          : url.includes('agent_id=employee') ? (posted.length ? skills : [])
            : [];
    return new Response(JSON.stringify(data), { status: 200, headers: { 'Content-Type': 'application/json' } });
  });
  vi.stubGlobal('fetch', fetchMock);

  const user = userEvent.setup();
  render(
    <I18nProvider>
      <TooltipProvider>
        <MemoryRouter initialEntries={['/enterprise/general-skills']}>
          <GeneralSkillsPage currentUser={{ id: 'admin', username: 'admin', tenant_id: 'tenant_demo', role: 'admin' }} />
        </MemoryRouter>
      </TooltipProvider>
    </I18nProvider>,
  );

  await waitFor(() => expect(screen.getByRole('button', { name: /新增/ })).toBeTruthy());
  await user.click(screen.getByRole('button', { name: /新增/ }));
  await user.click(screen.getByRole('menuitem', { name: '从广场复制' }));
  await waitFor(() => expect(screen.getByRole('checkbox', { name: '选择整个文件夹 人事工具包' })).toBeTruthy());
  await user.click(screen.getByRole('checkbox', { name: '选择整个文件夹 人事工具包' }));
  await user.click(screen.getByRole('button', { name: '复制' }));

  await waitFor(() => expect(posted).toEqual([['recruitment', 'compensation']]));
  await waitFor(() => expect(screen.getAllByText('人事工具包').length).toBeGreaterThan(0));
});
