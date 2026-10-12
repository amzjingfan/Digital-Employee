// @vitest-environment jsdom

import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { afterEach, expect, it, vi } from 'vitest';

import { ResourceImportDialog } from '@/components/ResourceImportDialog';

afterEach(cleanup);

it('copies an entire Skill folder while allowing individual members to be excluded', async () => {
  const onSubmit = vi.fn();
  function Example() {
    const [selectedIds, setSelectedIds] = useState<string[]>([]);
    return (
      <ResourceImportDialog
        open
        loading={false}
        icon={<span />}
        title="从广场复制技能"
        sourcePlaceholder="选择开放广场"
        sources={[{ value: 'gallery', label: '开放广场' }]}
        sourceId="gallery"
        itemsLabel="选择技能"
        items={[
          { id: 'a', label: '招聘', groupId: 'hr', groupName: '人事工具包' },
          { id: 'b', label: '薪酬', groupId: 'hr', groupName: '人事工具包' },
          { id: 'c', label: '独立技能' },
        ]}
        selectedIds={selectedIds}
        emptyText="没有可复制的技能"
        note="测试"
        onSourceChange={() => {}}
        onSelectedChange={setSelectedIds}
        onClose={() => {}}
        onSubmit={() => onSubmit(selectedIds)}
      />
    );
  }

  const user = userEvent.setup();
  render(<Example />);
  await user.click(screen.getByRole('checkbox', { name: '选择整个文件夹 人事工具包' }));
  expect(screen.getByText('2/2 个技能')).toBeTruthy();
  await user.click(screen.getByRole('button', { name: '展开文件夹 人事工具包' }));
  await user.click(screen.getByRole('checkbox', { name: '薪酬' }));
  expect(screen.getByText('1/2 个技能')).toBeTruthy();
  expect(screen.getByRole('checkbox', { name: '选择整个文件夹 人事工具包' }).getAttribute('data-state')).toBe('indeterminate');
  await user.click(screen.getByRole('button', { name: '复制' }));
  expect(onSubmit).toHaveBeenCalledWith(['a']);
});
