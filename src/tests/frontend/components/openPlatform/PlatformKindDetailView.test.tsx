// @vitest-environment jsdom

import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import PlatformKindDetailView from '@/components/openPlatform/PlatformKindDetailView';
import { I18nProvider } from '@/i18n';

afterEach(cleanup);

describe('PlatformKindDetailView creation action', () => {
  it.each([
    ['knowledge', '创建开放知识库'],
    ['general-skills', '创建开放 Skill'],
    ['skills', '创建开放 SOP'],
    ['tools', '创建开放工具'],
  ] as const)('shows %s creation for an empty plaza', async (kind, createLabel) => {
    const onCreate = vi.fn();
    render(
      <I18nProvider>
        <PlatformKindDetailView
          kind={kind}
          title="广场"
          subtitle=""
          countLabel="内容"
          signals={[]}
          icon={() => <svg />}
          items={[]}
          loading={false}
          employeeStats={() => []}
          onBack={vi.fn()}
          onRefresh={vi.fn()}
          onCreate={onCreate}
          createLabel={createLabel}
          onOpenItem={vi.fn()}
        />
      </I18nProvider>,
    );

    await userEvent.setup().click(screen.getByRole('button', { name: createLabel }));
    expect(onCreate).toHaveBeenCalledOnce();
  });

  it('does not show a resource creation action for the employee plaza', () => {
    render(
      <I18nProvider>
        <PlatformKindDetailView
          kind="agents"
          title="数字员工广场"
          subtitle=""
          countLabel="员工"
          signals={[]}
          icon={() => <svg />}
          items={[]}
          loading={false}
          employeeStats={() => []}
          onBack={vi.fn()}
          onRefresh={vi.fn()}
          onOpenItem={vi.fn()}
        />
      </I18nProvider>,
    );

    expect(screen.queryByRole('button', { name: /^创建开放/ })).toBeNull();
  });
});
