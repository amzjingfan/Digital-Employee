// @vitest-environment jsdom

import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, expect, it, vi } from 'vitest';

import { I18nProvider } from '@/i18n';
import { TooltipProvider } from '@/components/ui/tooltip';
import KnowledgeManagePage from '@/pages/KnowledgePage';

afterEach(() => {
  cleanup();
  window.localStorage.clear();
  vi.unstubAllGlobals();
});

it('opens the requested gallery knowledge base editor from its plaza link', async () => {
  window.localStorage.setItem('ultrarag_enterprise_agent_scope', 'employee-1');
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => ({
    ok: true,
    status: 200,
    statusText: 'OK',
    text: async () => JSON.stringify(String(input).includes('/api/enterprise/agents?')
      ? [{ id: 'overall-1', tenant_id: 'tenant_demo', name: '开放广场', is_overall: true,
        status: 'active', metadata: {}, resources: [] }]
      : String(input).includes('/api/enterprise/knowledge-bases?')
        ? [{ id: 'kb-1', tenant_id: 'tenant_demo', name: 'Policy KB', description: 'Policy',
          status: 'active', document_count: 1, bucket_count: 0, chunk_count: 0 }]
        : []),
  } as Response));
  vi.stubGlobal('fetch', fetchMock);

  render(
    <I18nProvider>
      <TooltipProvider>
        <MemoryRouter initialEntries={['/enterprise/knowledge?scope=gallery&edit=kb-1']}>
          <KnowledgeManagePage currentUser={{ id: 'admin-1', username: 'admin',
            tenant_id: 'tenant_demo', role: 'admin' }} />
        </MemoryRouter>
      </TooltipProvider>
    </I18nProvider>,
  );

  await waitFor(() => expect((screen.getByPlaceholderText('知识库名称') as HTMLInputElement).value).toBe('Policy KB'));
  expect(fetchMock.mock.calls.some(([input]) => String(input).includes('/api/enterprise/knowledge-bases?')
    && !String(input).includes('agent_id=employee-1'))).toBe(true);
});
