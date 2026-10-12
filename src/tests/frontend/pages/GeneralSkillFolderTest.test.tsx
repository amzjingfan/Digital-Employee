// @vitest-environment jsdom

import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, expect, it, vi } from 'vitest';

import { I18nProvider } from '@/i18n';
import { TooltipProvider } from '@/components/ui/tooltip';
import { GeneralSkillEditPage } from '@/pages/GeneralSkillsPage';

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  window.localStorage.clear();
});

it('defaults a grouped Skill editor to testing its complete folder', async () => {
  const skills = ['layout', 'style'].map((slug) => ({
    id: `skill-${slug}`,
    tenant_id: 'tenant_demo',
    slug,
    name: slug,
    description: slug,
    skill_markdown: `# ${slug}`,
    skill_files: [{ path: 'SKILL.md', content: `# ${slug}` }],
    skill_directories: [],
    metadata: { import_group_id: 'group-design', import_group_name: 'Design kit' },
    status: 'published',
    capability_scope: 'general',
    permissions: {},
    runtime_config: {},
    created_at: '2026-10-12T00:00:00Z',
    updated_at: '2026-10-12T00:00:00Z',
  }));
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (init?.method === 'POST') {
      return new Response('event: complete\ndata: {"skill_slug":"group-design","reply":"已完成","structured_result":{"success":true,"loaded_skill_slugs":["layout"]}}\n\n', {
        status: 200,
        headers: { 'Content-Type': 'text/event-stream' },
      });
    }
    const data = url.includes('/general-skills?') ? skills
      : url.includes('/agents?') ? [{
        id: 'overall', tenant_id: 'tenant_demo', name: '开放广场', is_overall: true,
        status: 'active', metadata: {}, resources: [],
      }]
        : [];
    return new Response(JSON.stringify(data), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    });
  });
  vi.stubGlobal('fetch', fetchMock);

  render(
    <I18nProvider>
      <TooltipProvider>
      <MemoryRouter initialEntries={['/enterprise/general-skills/layout/edit?scope=gallery']}>
        <Routes>
          <Route
            path="/enterprise/general-skills/:slug/edit"
            element={<GeneralSkillEditPage currentUser={{
              id: 'admin', username: 'admin', tenant_id: 'tenant_demo', role: 'admin',
            }} />}
          />
        </Routes>
      </MemoryRouter>
      </TooltipProvider>
    </I18nProvider>,
  );

  await waitFor(() => expect(screen.getByText(/整个文件夹：Design kit（2 个技能）/)).toBeTruthy());
  await userEvent.setup().type(screen.getByPlaceholderText('输入要测试的问题'), '如何排版');
  await userEvent.setup().click(screen.getByRole('button', { name: '运行' }));
  await waitFor(() => expect(fetchMock.mock.calls.some(([input, init]) =>
    String(input).includes('/general-skills/groups/group-design/run/stream')
      && init?.method === 'POST'
      && JSON.parse(String(init.body)).query === '如何排版')).toBe(true));
});
