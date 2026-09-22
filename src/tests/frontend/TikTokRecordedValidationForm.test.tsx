// @vitest-environment jsdom

import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { api } from '@/api/client';
import TikTokRecordedValidationForm from '@/pages/tiktok/TikTokRecordedValidationForm';

vi.mock('@/api/client', () => ({
  api: { post: vi.fn() },
}));

const scope = {
  id: 'scope-1',
  store_resource_id: 'store-us',
  creator_scope_summary: 'US creators',
  business_owner_user_id: 'admin',
  data_owner_user_id: 'member',
  status: 'active' as const,
  revision: 3,
};

const owners = [
  { id: 'admin', label: '管理员' },
  { id: 'member', label: '数据负责人' },
];

const validDataset = {
  samples: [],
  orders: [],
  logistics: [],
  videos: [],
  attribution: [],
  gmv: [],
};

async function fillApprovalForm(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText('来源标签'), 'approved-export');
  await user.type(screen.getByLabelText('审批引用'), 'approval:001');
  await user.selectOptions(screen.getByLabelText('独立审批人'), 'member');
  await user.type(screen.getByLabelText('数据开始时间'), '2026-09-20T00:00');
  await user.type(screen.getByLabelText('数据结束时间'), '2026-09-21T23:30');
  await user.type(screen.getByLabelText('回放基准时间'), '2026-09-22T00:00');
  await user.type(screen.getByLabelText('审批时间'), '2026-09-22T01:00');
  await user.type(screen.getByLabelText('审批有效期'), '2026-10-02T00:00');
}

function renderForm(onCompleted = vi.fn()) {
  render(
    <TikTokRecordedValidationForm
      currentUserId="admin"
      scope={scope}
      ownerOptions={owners}
      onCompleted={onCompleted}
    />,
  );
  return onCompleted;
}

describe('TikTokRecordedValidationForm', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.post).mockResolvedValue({ status: 'passed' });
  });

  afterEach(() => cleanup());

  it('submits the dataset without filename and clears the file after completion', async () => {
    const user = userEvent.setup();
    const onCompleted = renderForm();
    const file = new File([JSON.stringify(validDataset)], 'private-export-name.json', {
      type: 'application/json',
    });
    await user.upload(screen.getByLabelText('选择脱敏 JSON'), file);
    await fillApprovalForm(user);
    await user.click(screen.getByRole('checkbox', { name: '确认文件已脱敏并获准回放' }));
    await user.click(screen.getByRole('button', { name: '运行录制回放' }));

    await waitFor(() => expect(api.post).toHaveBeenCalledTimes(1));
    expect(api.post).toHaveBeenCalledWith(
      '/api/enterprise/tiktok/data-validation/runs/recorded',
      expect.objectContaining({
        scope_revision: 3,
        dataset: validDataset,
        sanitization_attested: true,
      }),
    );
    const submitted = JSON.stringify(vi.mocked(api.post).mock.calls[0][1]);
    expect(submitted).not.toContain(file.name);
    expect(submitted).toContain(new Date('2026-09-22T00:00').toISOString());
    expect((screen.getByLabelText('选择脱敏 JSON') as HTMLInputElement).value).toBe('');
    expect(onCompleted).toHaveBeenCalledTimes(1);
  });

  it('rejects files over 2 MiB before reading or posting', async () => {
    const user = userEvent.setup();
    renderForm();
    const file = new File([new Uint8Array(2 * 1024 * 1024 + 1)], 'large.json', {
      type: 'application/json',
    });
    await user.upload(screen.getByLabelText('选择脱敏 JSON'), file);

    expect((await screen.findByRole('alert')).textContent).toContain('文件超过 2 MiB 限制');
    expect(api.post).not.toHaveBeenCalled();
  });

  it('reports malformed JSON without echoing parser input', async () => {
    const user = userEvent.setup();
    renderForm();
    await user.upload(
      screen.getByLabelText('选择脱敏 JSON'),
      new File(['{"raw-parser-marker"'], 'broken.json', { type: 'application/json' }),
    );
    await fillApprovalForm(user);
    await user.click(screen.getByRole('checkbox', { name: '确认文件已脱敏并获准回放' }));
    await user.click(screen.getByRole('button', { name: '运行录制回放' }));

    const alert = await screen.findByRole('alert');
    expect(alert.textContent).toContain('JSON 文件格式无效');
    expect(alert.textContent).not.toContain('raw-parser-marker');
    expect(api.post).not.toHaveBeenCalled();
  });

  it('requires active scope, file, separate approver, metadata and attestation', async () => {
    render(
      <TikTokRecordedValidationForm
        currentUserId="admin"
        scope={{ ...scope, status: 'draft' }}
        ownerOptions={owners}
        onCompleted={vi.fn()}
      />,
    );
    expect((screen.getByRole('button', { name: '运行录制回放' }) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.queryByRole('option', { name: '管理员' })).toBeNull();
    expect(screen.getByRole('option', { name: '数据负责人' })).toBeTruthy();
  });

  it('retains approval metadata but clears the file after API failure', async () => {
    vi.mocked(api.post).mockRejectedValueOnce(new Error('scope_revision_conflict'));
    const user = userEvent.setup();
    renderForm();
    await user.upload(
      screen.getByLabelText('选择脱敏 JSON'),
      new File([JSON.stringify(validDataset)], 'private.json', { type: 'application/json' }),
    );
    await fillApprovalForm(user);
    await user.click(screen.getByRole('checkbox', { name: '确认文件已脱敏并获准回放' }));
    await user.click(screen.getByRole('button', { name: '运行录制回放' }));

    expect((await screen.findByRole('alert')).textContent).toContain('录制回放运行失败');
    expect((screen.getByLabelText('来源标签') as HTMLInputElement).value).toBe('approved-export');
    expect((screen.getByLabelText('审批引用') as HTMLInputElement).value).toBe('approval:001');
    expect((screen.getByLabelText('选择脱敏 JSON') as HTMLInputElement).value).toBe('');
  });

  it('does not log source data to the console', async () => {
    const log = vi.spyOn(console, 'log').mockImplementation(() => undefined);
    try {
      const user = userEvent.setup();
      renderForm();
      await user.upload(
        screen.getByLabelText('选择脱敏 JSON'),
        new File([JSON.stringify(validDataset)], 'private.json', { type: 'application/json' }),
      );
      await fillApprovalForm(user);
      await user.click(screen.getByRole('checkbox', { name: '确认文件已脱敏并获准回放' }));
      await user.click(screen.getByRole('button', { name: '运行录制回放' }));
      await waitFor(() => expect(api.post).toHaveBeenCalledTimes(1));
      expect(log).not.toHaveBeenCalled();
    } finally {
      log.mockRestore();
    }
  });
});
