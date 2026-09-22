// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { api } from '@/api/client';
import type { EnterpriseAuthUser } from '@/auth';
import { notify } from '@/components/ui/app-toast';
import TikTokDataValidationPanel from '@/pages/tiktok/TikTokDataValidationPanel';

vi.mock('@/api/client', () => ({
  api: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
  },
}));

vi.mock('@/components/ui/app-toast', () => ({
  notify: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

const adminUser: EnterpriseAuthUser = {
  id: 'admin',
  tenant_id: 'tenant_demo',
  username: 'admin',
  role: 'admin',
};

const memberUser: EnterpriseAuthUser = {
  id: 'member',
  tenant_id: 'tenant_demo',
  username: 'member',
  role: 'member',
};

const workspace = {
  tenant_id: 'tenant_demo',
  catalog_version: 'p3-b0.v1',
  scope: null,
  readiness: {
    workbench_ready: true,
    real_data_ready: false,
    blockers: [{
      code: 'recorded_or_real_validation_missing',
      target_type: 'workspace',
      target_code: 'real_data',
      detail: '缺少真实或脱敏录制回放',
    }],
  },
  field_contracts: [{
    id: 'field-1',
    tenant_id: 'tenant_demo',
    field_code: 'order.order_id',
    domain: 'order',
    label: '订单 ID',
    data_type: 'string',
    required: true,
    owner_user_id: 'admin',
    business_key: 'order_id',
    freshness_sla_seconds: 3600,
    missing_behavior: 'block_stage',
    sources: [{
      source_key: 'mock.order.order_id',
      source_type: 'mock_fixture',
      object_name: 'orders',
      field_path: 'order_id',
      priority: 1,
      usage: 'mock',
      decision: 'use',
      authorization_state: 'not_required',
    }],
    status: 'confirmed',
    revision: 2,
    created_at: '2026-09-22T00:00:00Z',
    updated_at: '2026-09-22T00:00:00Z',
  }],
  capability_evidence: [{
    id: 'cap-1',
    tenant_id: 'tenant_demo',
    entry_code: 'seller.orders.read',
    entry_kind: 'capability',
    platform_domain: 'Seller',
    action: '读取订单',
    direction: 'read',
    subject_key: 'global',
    resource_id: null,
    required_scope: '',
    endpoint_or_artifact: '',
    api_version: '',
    evidence_level: 'E2',
    evidence_type: 'mock',
    status: 'verified',
    decision: null,
    summary: 'Mock 契约已验证',
    evidence_ref: 'mock:contract',
    checked_by_user_id: 'admin',
    checked_at: '2026-09-22T00:00:00Z',
    valid_until: null,
    revision: 2,
    created_at: '2026-09-22T00:00:00Z',
    updated_at: '2026-09-22T00:00:00Z',
  }, {
    id: 'provider-1',
    tenant_id: 'tenant_demo',
    entry_code: 'provider.fastmoss',
    entry_kind: 'provider_decision',
    platform_domain: 'FastMoss',
    action: 'integration_decision',
    direction: 'decision',
    subject_key: 'global',
    resource_id: null,
    required_scope: '',
    endpoint_or_artifact: '',
    api_version: '',
    evidence_level: 'E1',
    evidence_type: 'contract',
    status: 'blocked',
    decision: 'defer',
    summary: '等待商务条款',
    evidence_ref: 'contract:fastmoss',
    checked_by_user_id: 'admin',
    checked_at: '2026-09-20T00:00:00Z',
    valid_until: '2026-09-21T00:00:00Z',
    revision: 3,
    created_at: '2026-09-20T00:00:00Z',
    updated_at: '2026-09-20T00:00:00Z',
  }],
  recent_runs: [{
    id: 'run-1',
    tenant_id: 'tenant_demo',
    mode: 'mock',
    catalog_version: 'p3-b0.v1',
    dataset_digest: 'sha256:digest',
    record_count: 6,
    status: 'passed',
    workbench_ready_snapshot: true,
    real_data_ready_snapshot: false,
    checks: [{ code: 'required_fields', passed: true, checked_count: 30 }],
    issues: [],
    started_by_user_id: 'admin',
    created_at: '2026-09-22T00:00:00Z',
  }],
  store_options: [{ id: 'store-us', label: 'TikTok Shop US' }],
  owner_options: [{ id: 'admin', label: '管理员' }],
};

describe('TikTokDataValidationPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.get).mockResolvedValue(structuredClone(workspace));
    vi.mocked(api.post).mockResolvedValue(workspace.recent_runs[0]);
    vi.mocked(api.put).mockResolvedValue({});
  });

  afterEach(() => cleanup());

  it('shows separate readiness states and lets an admin run Mock validation', async () => {
    render(<TikTokDataValidationPanel currentUser={adminUser} />);

    expect(await screen.findByText('工作台配置就绪')).toBeTruthy();
    expect(screen.getByText('真实数据未就绪')).toBeTruthy();
    await userEvent.click(screen.getByRole('button', { name: '运行 Mock 校验' }));
    expect(api.post).toHaveBeenCalledWith('/api/enterprise/tiktok/data-validation/runs/mock');
    expect(screen.queryByText('mock-order-001')).toBeNull();
  });

  it('keeps the same tenant workspace read-only for a member', async () => {
    render(<TikTokDataValidationPanel currentUser={memberUser} />);

    expect(await screen.findByText('只读模式')).toBeTruthy();
    expect(screen.queryByRole('button', { name: '初始化验证目录' })).toBeNull();
    expect(screen.queryByRole('button', { name: '运行 Mock 校验' })).toBeNull();
    expect(screen.queryByRole('button', { name: '保存字段契约' })).toBeNull();
  });

  it('bootstraps an empty catalog and reloads the workspace', async () => {
    vi.mocked(api.get)
      .mockResolvedValueOnce({ ...structuredClone(workspace), field_contracts: [], capability_evidence: [] })
      .mockResolvedValueOnce(structuredClone(workspace));
    render(<TikTokDataValidationPanel currentUser={adminUser} />);

    await userEvent.click(await screen.findByRole('button', { name: '初始化验证目录' }));

    expect(api.post).toHaveBeenCalledWith('/api/enterprise/tiktok/data-validation/bootstrap');
    await waitFor(() => expect(api.get).toHaveBeenCalledTimes(2));
  });

  it('saves the US pilot scope without inventing tenant references', async () => {
    render(<TikTokDataValidationPanel currentUser={adminUser} />);
    await screen.findByText('试点范围');
    await userEvent.selectOptions(screen.getByLabelText('US 试点店铺'), 'store-us');
    await userEvent.selectOptions(screen.getByLabelText('业务 Owner'), 'admin');
    await userEvent.selectOptions(screen.getByLabelText('数据 Owner'), 'admin');
    await userEvent.type(screen.getByLabelText('达人范围'), 'US pilot creators');
    await userEvent.click(screen.getByRole('button', { name: '保存试点范围' }));

    expect(api.put).toHaveBeenCalledWith('/api/enterprise/tiktok/data-validation/pilot-scope', expect.objectContaining({
      revision: 0,
      store_resource_id: 'store-us',
      creator_scope_summary: 'US pilot creators',
    }));
  });

  it('saves field revisions and preserves the form when the API rejects it', async () => {
    vi.mocked(api.put).mockRejectedValueOnce(new Error('revision_conflict'));
    render(<TikTokDataValidationPanel currentUser={adminUser} />);
    const input = await screen.findByLabelText('订单 ID 业务键');
    await userEvent.clear(input);
    await userEvent.type(input, 'external_order_id');
    await userEvent.selectOptions(screen.getByLabelText('订单 ID 缺失处理'), 'manual_review');
    await userEvent.selectOptions(screen.getByLabelText('订单 ID 契约状态'), 'blocked');
    await userEvent.click(screen.getByRole('button', { name: '保存字段契约' }));

    expect(api.put).toHaveBeenCalledWith(
      '/api/enterprise/tiktok/data-validation/field-contracts/order.order_id',
      expect.objectContaining({
        revision: 2,
        business_key: 'external_order_id',
        missing_behavior: 'manual_review',
        status: 'blocked',
      }),
    );
    expect((input as HTMLInputElement).value).toBe('external_order_id');
    expect(notify.error).toHaveBeenCalledWith('revision_conflict');
    expect(screen.getByRole('alert').textContent).toContain('revision_conflict');
  });

  it('saves capability evidence and provider decisions with their revisions', async () => {
    render(<TikTokDataValidationPanel currentUser={adminUser} />);
    await screen.findByText('能力证据与供应商决定');

    await userEvent.selectOptions(screen.getByLabelText('seller.orders.read 证据类型'), 'official_docs');
    fireEvent.change(screen.getByLabelText('seller.orders.read 检查时间'), {
      target: { value: '2026-09-22T08:30' },
    });
    await userEvent.click(screen.getByRole('button', { name: '保存能力证据 seller.orders.read' }));
    expect(api.put).toHaveBeenCalledWith(
      '/api/enterprise/tiktok/data-validation/capability-evidence/seller.orders.read',
      expect.objectContaining({
        revision: 2,
        evidence_level: 'E2',
        evidence_type: 'official_docs',
        checked_at: expect.stringContaining('2026-09-22T'),
      }),
    );

    await userEvent.click(screen.getByRole('button', { name: '保存供应商决定 provider.fastmoss' }));
    expect(api.put).toHaveBeenCalledWith(
      '/api/enterprise/tiktok/data-validation/capability-evidence/provider.fastmoss',
      expect.objectContaining({ revision: 3, decision: 'defer' }),
    );
  });

  it('renders blocked, expired, and E0-E3 evidence states as text', async () => {
    render(<TikTokDataValidationPanel currentUser={adminUser} />);

    expect(await screen.findByText('已阻塞')).toBeTruthy();
    expect(screen.getByText('已过期')).toBeTruthy();
    expect(screen.getAllByText('E2').length).toBeGreaterThan(0);
    expect(screen.getAllByText('E1').length).toBeGreaterThan(0);
    expect(screen.getByText('证据等级：E0–E3')).toBeTruthy();
  });
});
