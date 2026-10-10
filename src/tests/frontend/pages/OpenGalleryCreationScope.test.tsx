// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { api } from '@/api/client';
import { TooltipProvider } from '@/components/ui/tooltip';
import { I18nProvider } from '@/i18n';
import { KnowledgeAddPage } from '@/pages/KnowledgePage';
import { ToolNewPage, ToolTestPage } from '@/pages/ToolsPage';

const admin = { id: 'admin', username: 'admin', tenant_id: 'tenant_demo', role: 'admin' } as const;

function LocationEcho() {
  const location = useLocation();
  return <div data-testid="location">{`${location.pathname}${location.search}`}</div>;
}

afterEach(() => {
  cleanup();
  window.localStorage.clear();
  vi.restoreAllMocks();
});

describe('open gallery creation scope', () => {
  it('uploads a knowledge base to the gallery even if an employee is selected', async () => {
    window.localStorage.setItem('ultrarag_enterprise_agent_scope', 'employee-1');
    vi.spyOn(api, 'get').mockImplementation(async (path) => (
      path.startsWith('/api/enterprise/agents?')
        ? [{ id: 'overall-1', is_overall: true }, { id: 'employee-1', is_overall: false }]
        : []
    ) as never);
    const post = vi.spyOn(api, 'post').mockRejectedValue(new Error('test upload stopped'));

    const { container } = render(
      <I18nProvider>
        <TooltipProvider>
          <MemoryRouter initialEntries={['/enterprise/knowledge/new?scope=gallery']}>
            <Routes>
              <Route path="/enterprise/knowledge/new" element={<KnowledgeAddPage currentUser={admin} />} />
            </Routes>
          </MemoryRouter>
        </TooltipProvider>
      </I18nProvider>,
    );
    await waitFor(() => expect(api.get).toHaveBeenCalledWith(
      '/api/enterprise/knowledge-bases?tenant_id=tenant_demo&agent_id=overall-1',
    ));

    const input = container.querySelector('input[type="file"]');
    expect(input).not.toBeNull();
    fireEvent.change(input!, { target: { files: [new File(['hello'], 'guide.txt', { type: 'text/plain' })] } });

    await waitFor(() => expect(post).toHaveBeenCalledWith(
      '/api/enterprise/knowledge/documents?agent_id=overall-1',
      expect.objectContaining({ tenant_id: 'tenant_demo', filename: 'guide.txt' }),
    ));
  });

  it('saves a gallery tool without the selected employee scope', async () => {
    window.localStorage.setItem('ultrarag_enterprise_agent_scope', 'employee-1');
    vi.spyOn(api, 'get').mockResolvedValue([]);
    const post = vi.spyOn(api, 'post').mockRejectedValue(new Error('test save stopped'));

    render(
      <I18nProvider>
        <TooltipProvider>
          <MemoryRouter initialEntries={['/enterprise/tools/new?scope=gallery']}>
            <Routes>
              <Route path="/enterprise/tools/new" element={<ToolNewPage currentUser={admin} />} />
              <Route path="*" element={<LocationEcho />} />
            </Routes>
          </MemoryRouter>
        </TooltipProvider>
      </I18nProvider>,
    );
    fireEvent.change(screen.getByLabelText('工具名称'), { target: { value: 'gallery_tool' } });
    fireEvent.change(screen.getByLabelText('URL'), { target: { value: 'https://example.test/tool' } });
    fireEvent.click(screen.getByRole('button', { name: '保存' }));

    await waitFor(() => expect(post).toHaveBeenCalledWith(
      '/api/enterprise/tools',
      expect.objectContaining({ name: 'gallery_tool', tenant_id: 'tenant_demo' }),
    ));
    fireEvent.click(screen.getByRole('button', { name: /A2A Agent/ }));
    await waitFor(() => expect(api.get).toHaveBeenCalledWith(
      '/api/enterprise/tools/a2a/codex-adapter?tenant_id=tenant_demo',
    ));
    fireEvent.click(screen.getByRole('button', { name: /MCP 服务器/ }));
    expect(screen.getByTestId('location').textContent).toBe('/enterprise/tools/mcp/new?scope=gallery');
  });

  it('tests a saved gallery tool without the selected employee scope', async () => {
    window.localStorage.setItem('ultrarag_enterprise_agent_scope', 'employee-1');
    vi.spyOn(api, 'get').mockResolvedValue({
      id: 'tool-1', name: 'gallery_tool', display_name: 'Gallery tool',
      tool_type: 'http', method: 'POST', url: 'https://example.test/tool',
      input_schema: {}, output_schema: {}, updated_at: '2026-10-10T00:00:00Z',
    } as never);
    const post = vi.spyOn(api, 'post').mockResolvedValue({ success: true } as never);

    render(
      <I18nProvider>
        <TooltipProvider>
          <MemoryRouter initialEntries={['/enterprise/tools/tool-1/test?scope=gallery']}>
            <Routes>
              <Route path="/enterprise/tools/:toolId/test" element={<ToolTestPage currentUser={admin} />} />
            </Routes>
          </MemoryRouter>
        </TooltipProvider>
      </I18nProvider>,
    );
    fireEvent.click(await screen.findByRole('button', { name: '调用' }));
    await waitFor(() => expect(post).toHaveBeenCalledWith(
      '/api/enterprise/tools/tool-1/test',
      expect.objectContaining({ tenant_id: 'tenant_demo' }),
    ));
  });
});
