// @vitest-environment jsdom

import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import SkillFolderSelectionDialog from '@/components/SkillFolderSelectionDialog';

const choices = ['bundle/a/SKILL.md', 'bundle/b/SKILL.md', 'bundle/c/SKILL.md'];

function TestDialog({ onImport = vi.fn() }: { onImport?: (paths: string[]) => void }) {
  const [selected, setSelected] = useState<string[]>([]);
  return (
    <SkillFolderSelectionDialog
      choices={choices}
      selectedPaths={selected}
      loading={false}
      error=""
      onSelectedChange={setSelected}
      onImport={() => onImport(selected)}
      onClose={() => {}}
    />
  );
}

afterEach(cleanup);

describe('skill folder selection dialog', () => {
  it('supports one, several, select all, and clearing the selection', async () => {
    const user = userEvent.setup();
    const onImport = vi.fn();
    render(<TestDialog onImport={onImport} />);

    const importButton = screen.getByRole('button', { name: '导入选中（0）' });
    expect(importButton.hasAttribute('disabled')).toBe(true);

    await user.click(screen.getByLabelText('bundle/a'));
    expect(screen.getByText('已选择 1 项')).toBeTruthy();
    await user.click(screen.getByRole('button', { name: '导入选中（1）' }));
    expect(onImport).toHaveBeenLastCalledWith([choices[0]]);

    await user.click(screen.getByLabelText('bundle/c'));
    await user.click(screen.getByRole('button', { name: '导入选中（2）' }));
    expect(onImport).toHaveBeenLastCalledWith([choices[0], choices[2]]);

    await user.click(screen.getByLabelText('全选'));
    await user.click(screen.getByRole('button', { name: '导入选中（3）' }));
    expect(onImport).toHaveBeenLastCalledWith(choices);

    await user.click(screen.getByLabelText('全选'));
    expect(screen.getByRole('button', { name: '导入选中（0）' }).hasAttribute('disabled')).toBe(true);
  });
});
