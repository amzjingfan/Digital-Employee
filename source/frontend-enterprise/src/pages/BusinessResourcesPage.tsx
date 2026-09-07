import { useCallback, useEffect, useMemo, useState } from 'react';

import { api, TENANT_ID } from '@/api/client';
import { canUseEnterpriseCapability, isEnterpriseAdmin, type EnterpriseAuthUser } from '@/auth';
import AppHeader from '@/components/AppHeader';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogTitle,
  Input,
  Textarea,
} from '@/components/ui';
import { Button } from '@/components/ui/button';
import { notify } from '@/components/ui/app-toast';
import { cn } from '@/lib/utils';

type ResourceType = 'store' | 'carrier' | 'ad_account' | 'supplier';
type ApprovalStatus = 'pending' | 'approved' | 'rejected' | 'cancelled' | 'invalidated';
type ExecutionStatus =
  | 'queued'
  | 'running'
  | 'retry_wait'
  | 'succeeded'
  | 'failed'
  | 'compensation_requested'
  | 'compensating'
  | 'compensated'
  | 'compensation_failed'
  | 'manual_resolution_required';
type ActionType =
  | 'issue_refund'
  | 'publish_listing'
  | 'change_routing_rule'
  | 'change_daily_budget'
  | 'change_ad_bid'
  | 'update_negative_keywords'
  | 'change_campaign_status'
  | 'publish_creative_asset'
  | 'issue_purchase_order';

type BusinessResource = {
  id: string;
  resource_type: ResourceType;
  code: string;
  name: string;
  status: string;
  revision: number;
  access_level: 'viewer' | 'operator';
  metadata: Record<string, unknown>;
  scopes: Array<{ business_role: string; access_level: string }>;
};

type BusinessExecution = {
  id: string;
  connector_type: string;
  environment: 'sandbox' | 'live';
  status: ExecutionStatus;
  attempt_count: number;
  max_attempts: number;
  approval_content_digest: string;
  resource_snapshot_digest: string;
  external_operation_id?: string | null;
  receipt: Record<string, unknown>;
  last_error_code?: string | null;
  last_error_message?: string | null;
  next_attempt_at?: string | null;
  completed_at?: string | null;
  compensated_at?: string | null;
  events: Array<{
    phase: string;
    event_type: string;
    attempt_no: number;
    occurred_at: string;
  }>;
};

type ApprovalRequest = {
  id: string;
  resource_id: string;
  resource_type: ResourceType;
  resource_name: string;
  action_type: ActionType;
  summary: string;
  payload: Record<string, unknown>;
  status: ApprovalStatus;
  content_digest: string;
  resource_snapshot_digest: string;
  requester_user_id: string;
  requester_business_role: string;
  decided_by_user_id?: string | null;
  decision_reason?: string | null;
  requested_at: string;
  decided_at?: string | null;
  invalidated_at?: string | null;
  invalidation_reason?: string | null;
  events: Array<{
    event_type: string;
    actor_user_id: string;
    actor_business_role: string;
    occurred_at: string;
  }>;
  execution?: BusinessExecution | null;
};

const RESOURCE_LABELS: Record<ResourceType, string> = {
  store: '店铺',
  carrier: '物流商',
  ad_account: '广告账户',
  supplier: '供应商',
};

const ACTION_LABELS: Record<ActionType, string> = {
  issue_refund: '发起退款',
  publish_listing: '发布 Listing',
  change_routing_rule: '调整物流路由',
  change_daily_budget: '调整广告日预算',
  change_ad_bid: '调整广告竞价',
  update_negative_keywords: '更新广告否词',
  change_campaign_status: '调整广告活动状态',
  publish_creative_asset: '发布创意素材',
  issue_purchase_order: '下达采购单',
};

const ACTION_RESOURCE_TYPES: Record<ActionType, ResourceType[]> = {
  issue_refund: ['store'],
  publish_listing: ['store'],
  change_routing_rule: ['carrier'],
  change_daily_budget: ['ad_account'],
  change_ad_bid: ['ad_account'],
  update_negative_keywords: ['ad_account'],
  change_campaign_status: ['ad_account'],
  publish_creative_asset: ['store', 'ad_account'],
  issue_purchase_order: ['supplier'],
};

const ROLE_ACTIONS: Record<string, ActionType[]> = {
  after_sales_specialist: ['issue_refund'],
  listing_compliance_specialist: ['publish_listing'],
  logistics_exception_specialist: ['change_routing_rule'],
  advertising_inspection_specialist: [
    'change_daily_budget',
    'change_ad_bid',
    'update_negative_keywords',
    'change_campaign_status',
  ],
  designer: ['publish_creative_asset'],
  procurement_specialist: ['issue_purchase_order'],
  operations_supervisor: Object.keys(ACTION_LABELS) as ActionType[],
};

const PAYLOAD_TEMPLATES: Record<ActionType, Record<string, unknown>> = {
  issue_refund: { order_id: '', amount: 0, currency: 'USD' },
  publish_listing: {
    listing_id: '',
    marketplace: 'Amazon US',
    product_type: '',
    attributes: {},
  },
  change_routing_rule: { route_policy: '', previous_route_policy: '' },
  change_daily_budget: {
    campaign_id: '',
    daily_budget: 0,
    previous_daily_budget: 0,
    currency: 'USD',
  },
  change_ad_bid: {
    campaign_id: '',
    target_id: '',
    bid: 0,
    previous_bid: 0,
    currency: 'USD',
  },
  update_negative_keywords: {
    campaign_id: '',
    keywords: [],
    match_type: 'NEGATIVE_EXACT',
    rollback_keyword_ids: [],
  },
  change_campaign_status: {
    campaign_id: '',
    status: 'PAUSED',
    previous_status: 'ENABLED',
  },
  publish_creative_asset: { asset_id: '', channel: 'Amazon' },
  issue_purchase_order: { po_number: '', amount: 0, currency: 'USD' },
};

const RESOURCE_METADATA_TEMPLATES: Record<ResourceType, Record<string, unknown>> = {
  store: {
    platform: 'amazon',
    region: 'na',
    seller_id: '',
    marketplace_id: 'ATVPDKIKX0DER',
    auth_profile: 'AMAZON_US',
  },
  carrier: {
    execute_url: 'https://logistics.example.com/staffdeck/actions',
    compensate_url: 'https://logistics.example.com/staffdeck/compensations',
    auth_profile: 'LOGISTICS_PRIMARY',
    supports_idempotency: true,
  },
  ad_account: {
    profile_id: '',
    ads_base_url: 'https://advertising-api.amazon.com',
    campaign_update_path: '',
    bid_update_path: '',
    negative_keyword_update_path: '',
    negative_keyword_rollback_path: '',
    auth_profile: 'AMAZON_US',
  },
  supplier: {
    execute_url: 'https://procurement.example.com/staffdeck/purchase-orders',
    compensate_url: 'https://procurement.example.com/staffdeck/purchase-orders/cancel',
    auth_profile: 'PROCUREMENT_PRIMARY',
    supports_idempotency: true,
  },
};

const ROLE_LABELS: Record<string, string> = {
  operations_supervisor: '运营主管',
  after_sales_specialist: '售后',
  listing_compliance_specialist: 'Listing 合规',
  logistics_exception_specialist: '物流',
  advertising_inspection_specialist: '广告',
  designer: '美工',
  procurement_specialist: '采购',
};

function formatTime(value?: string | null): string {
  return value ? new Date(value).toLocaleString() : '-';
}

function statusLabel(status: ApprovalStatus): string {
  return {
    pending: '待审批',
    approved: '已批准',
    rejected: '已拒绝',
    cancelled: '已撤回',
    invalidated: '已失效',
  }[status];
}

function executionStatusLabel(status: ExecutionStatus): string {
  return {
    queued: '待执行',
    running: '执行中',
    retry_wait: '等待重试',
    succeeded: '执行成功',
    failed: '执行失败',
    compensation_requested: '等待补偿',
    compensating: '补偿中',
    compensated: '已补偿',
    compensation_failed: '补偿失败',
    manual_resolution_required: '需人工处理',
  }[status];
}

export default function BusinessResourcesPage({
  currentUser,
  onLogout,
}: {
  currentUser: EnterpriseAuthUser;
  onLogout?: () => void;
}) {
  const [resources, setResources] = useState<BusinessResource[]>([]);
  const [approvals, setApprovals] = useState<ApprovalRequest[]>([]);
  const [activeType, setActiveType] = useState<'all' | ResourceType>('all');
  const [activeView, setActiveView] = useState<'resources' | 'approvals' | 'executions'>('resources');
  const [loading, setLoading] = useState(true);
  const [createOpen, setCreateOpen] = useState(false);
  const [createType, setCreateType] = useState<ResourceType>('store');
  const [createCode, setCreateCode] = useState('');
  const [createName, setCreateName] = useState('');
  const [createMetadata, setCreateMetadata] = useState(
    JSON.stringify(RESOURCE_METADATA_TEMPLATES.store, null, 2),
  );
  const [actionResource, setActionResource] = useState<BusinessResource | null>(null);
  const [actionType, setActionType] = useState<ActionType>('publish_listing');
  const [actionSummary, setActionSummary] = useState('');
  const [actionPayload, setActionPayload] = useState('{}');
  const [decisionTarget, setDecisionTarget] = useState<ApprovalRequest | null>(null);
  const [decisionKind, setDecisionKind] = useState<'approve' | 'reject'>('approve');
  const [decisionReason, setDecisionReason] = useState('');
  const [executionTarget, setExecutionTarget] = useState<ApprovalRequest | null>(null);
  const [executionCommand, setExecutionCommand] = useState<'retry' | 'compensate'>('retry');
  const [executionReason, setExecutionReason] = useState('');
  const [busy, setBusy] = useState(false);

  const canManageResources = canUseEnterpriseCapability(
    currentUser,
    'business_resources',
    'create',
  );
  const canApprove = isEnterpriseAdmin(currentUser)
    || currentUser.business_role === 'operations_supervisor';
  const allowedActions = isEnterpriseAdmin(currentUser)
    ? (Object.keys(ACTION_LABELS) as ActionType[])
    : ROLE_ACTIONS[currentUser.business_role || ''] || [];

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const resourcePath = `/api/enterprise/business-resources?tenant_id=${encodeURIComponent(TENANT_ID)}`;
      const approvalPath = canApprove
        ? `/api/enterprise/business-approvals?tenant_id=${encodeURIComponent(TENANT_ID)}`
        : `/api/enterprise/business-action-requests?tenant_id=${encodeURIComponent(TENANT_ID)}`;
      const [resourceRows, approvalRows] = await Promise.all([
        api.get<BusinessResource[]>(resourcePath),
        api.get<ApprovalRequest[]>(approvalPath),
      ]);
      setResources(resourceRows);
      setApprovals(approvalRows);
    } catch (error) {
      notify.error(error instanceof Error ? error.message : '加载业务资源失败');
    } finally {
      setLoading(false);
    }
  }, [canApprove]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    const active = approvals.some((item) => item.execution && [
      'queued', 'running', 'retry_wait', 'compensation_requested', 'compensating',
    ].includes(item.execution.status));
    if (!active) return undefined;
    const timer = window.setInterval(() => { void load(); }, 3000);
    return () => window.clearInterval(timer);
  }, [approvals, load]);

  const counts = useMemo(() => {
    const output = { store: 0, carrier: 0, ad_account: 0, supplier: 0 };
    resources.forEach((item) => { output[item.resource_type] += 1; });
    return output;
  }, [resources]);
  const displayedResources = useMemo(
    () => activeType === 'all' ? resources : resources.filter((item) => item.resource_type === activeType),
    [activeType, resources],
  );

  function openAction(resource: BusinessResource) {
    const first = allowedActions.find((item) => ACTION_RESOURCE_TYPES[item].includes(resource.resource_type));
    if (!first) {
      notify.warning('当前岗位没有适用于该资源的高风险动作');
      return;
    }
    setActionResource(resource);
    setActionType(first);
    setActionSummary('');
    setActionPayload(JSON.stringify(PAYLOAD_TEMPLATES[first], null, 2));
  }

  function changeAction(next: ActionType) {
    setActionType(next);
    setActionPayload(JSON.stringify(PAYLOAD_TEMPLATES[next], null, 2));
  }

  async function saveResource() {
    if (!createCode.trim() || !createName.trim()) {
      notify.warning('请填写资源编码和名称');
      return;
    }
    setBusy(true);
    try {
      const metadata = JSON.parse(createMetadata) as Record<string, unknown>;
      await api.post('/api/enterprise/business-resources', {
        tenant_id: TENANT_ID,
        resource_type: createType,
        code: createCode.trim(),
        name: createName.trim(),
        metadata,
      });
      setCreateOpen(false);
      setCreateCode('');
      setCreateName('');
      setCreateMetadata(JSON.stringify(RESOURCE_METADATA_TEMPLATES[createType], null, 2));
      notify.success('业务资源已创建并应用默认岗位范围');
      await load();
    } catch (error) {
      notify.error(error instanceof Error ? error.message : '创建失败');
    } finally {
      setBusy(false);
    }
  }

  async function submitAction() {
    if (!actionResource || actionSummary.trim().length < 8) {
      notify.warning('请填写不少于 8 个字的申请说明');
      return;
    }
    let payload: Record<string, unknown>;
    try {
      payload = JSON.parse(actionPayload) as Record<string, unknown>;
    } catch {
      notify.error('操作参数必须是有效 JSON');
      return;
    }
    setBusy(true);
    try {
      await api.post('/api/enterprise/business-action-requests', {
        tenant_id: TENANT_ID,
        resource_id: actionResource.id,
        action_type: actionType,
        summary: actionSummary.trim(),
        payload,
      });
      setActionResource(null);
      setActiveView('approvals');
      notify.success('高风险操作已提交审批，尚未执行外部动作');
      await load();
    } catch (error) {
      notify.error(error instanceof Error ? error.message : '提交审批失败');
    } finally {
      setBusy(false);
    }
  }

  async function decide() {
    if (!decisionTarget || decisionReason.trim().length < 2) {
      notify.warning('请填写审批意见');
      return;
    }
    setBusy(true);
    try {
      await api.post(
        `/api/enterprise/business-approvals/${encodeURIComponent(decisionTarget.id)}/${decisionKind}`,
        { tenant_id: TENANT_ID, reason: decisionReason.trim() },
      );
      setDecisionTarget(null);
      setDecisionReason('');
      notify.success(decisionKind === 'approve' ? '申请已批准，等待外部执行' : '申请已拒绝');
      await load();
    } catch (error) {
      notify.error(error instanceof Error ? error.message : '审批失败');
    } finally {
      setBusy(false);
    }
  }

  async function controlExecution() {
    const execution = executionTarget?.execution;
    if (!execution || executionReason.trim().length < 4) {
      notify.warning('请填写不少于 4 个字的操作原因');
      return;
    }
    setBusy(true);
    try {
      await api.post(
        `/api/enterprise/business-executions/${encodeURIComponent(execution.id)}/${executionCommand}`,
        { tenant_id: TENANT_ID, reason: executionReason.trim() },
      );
      setExecutionTarget(null);
      setExecutionReason('');
      notify.success(executionCommand === 'retry' ? '执行任务已重新入队' : '补偿任务已入队');
      await load();
    } catch (error) {
      notify.error(error instanceof Error ? error.message : '执行控制失败');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="min-h-full box-border px-[48px] pt-[32px] pb-[43px] max-[900px]:px-[16px]">
      <AppHeader
        onLogout={onLogout}
        userName={currentUser.username}
        title="业务资源与审批"
        description="按岗位隔离店铺、物流商、广告账户和供应商；高风险动作必须经过独立审批。"
      />

      <div className="mt-6 grid grid-cols-4 gap-3 max-[900px]:grid-cols-2">
        {(Object.keys(RESOURCE_LABELS) as ResourceType[]).map((type) => (
          <button
            key={type}
            type="button"
            onClick={() => { setActiveType(type); setActiveView('resources'); }}
            className={cn(
              'rounded-[16px] border px-4 py-3 text-left transition-colors',
              activeType === type ? 'border-[#18181a] bg-[#f6f6f6]' : 'border-[#e5e8ef] bg-white hover:bg-[#fafafa]',
            )}
          >
            <span className="block text-[12px] text-[#858b9c]">{RESOURCE_LABELS[type]}</span>
            <strong className="mt-1 block text-[24px] text-[#18181a]">{counts[type]}</strong>
          </button>
        ))}
      </div>

      <div className="mt-6 flex flex-wrap items-center justify-between gap-3">
        <div className="inline-flex rounded-[10px] bg-[#f1f3f6] p-1">
          <button type="button" onClick={() => setActiveView('resources')} className={cn('rounded-[8px] px-4 py-2 text-[13px]', activeView === 'resources' && 'bg-white shadow-sm')}>资源范围</button>
          <button type="button" onClick={() => setActiveView('approvals')} className={cn('rounded-[8px] px-4 py-2 text-[13px]', activeView === 'approvals' && 'bg-white shadow-sm')}>审批记录 · {approvals.filter((item) => item.status === 'pending').length}</button>
          <button type="button" onClick={() => setActiveView('executions')} className={cn('rounded-[8px] px-4 py-2 text-[13px]', activeView === 'executions' && 'bg-white shadow-sm')}>执行与回执 · {approvals.filter((item) => item.execution && !['succeeded', 'compensated'].includes(item.execution.status)).length}</button>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => void load()}>刷新</Button>
          {canManageResources && <Button onClick={() => setCreateOpen(true)}>新增业务资源</Button>}
        </div>
      </div>

      {activeView === 'resources' ? (
        <div className="mt-4 overflow-hidden rounded-[16px] border border-[#e5e8ef] bg-white">
          {displayedResources.length === 0 && !loading ? (
            <p className="p-10 text-center text-[13px] text-[#858b9c]">当前岗位范围内暂无业务资源。</p>
          ) : displayedResources.map((resource) => {
            const applicable = allowedActions.filter((action) => ACTION_RESOURCE_TYPES[action].includes(resource.resource_type));
            return (
              <div key={resource.id} className="flex flex-wrap items-center gap-4 border-b border-[#eef0f4] px-5 py-4 last:border-b-0">
                <span className="rounded-full bg-[#eef3ff] px-3 py-1 text-[12px] text-[#315ea8]">{RESOURCE_LABELS[resource.resource_type]}</span>
                <div className="min-w-[220px] flex-1">
                  <strong className="block text-[14px] text-[#18181a]">{resource.name}</strong>
                  <span className="mt-1 block text-[12px] text-[#858b9c]">{resource.code} · 修订 {resource.revision ?? 1} · {resource.status} · {resource.access_level === 'operator' ? '可操作' : '只读'}</span>
                </div>
                <div className="max-w-[360px] text-right text-[11px] text-[#858b9c]">
                  {resource.scopes.map((scope) => ROLE_LABELS[scope.business_role] || scope.business_role).join('、')}
                </div>
                {applicable.length > 0 && resource.access_level === 'operator' && (
                  <Button variant="outline" size="sm" onClick={() => openAction(resource)}>发起高风险操作</Button>
                )}
              </div>
            );
          })}
        </div>
      ) : activeView === 'approvals' ? (
        <div className="mt-4 space-y-3">
          {approvals.length === 0 && !loading && <p className="rounded-[16px] border border-[#e5e8ef] bg-white p-10 text-center text-[13px] text-[#858b9c]">暂无审批记录。</p>}
          {approvals.map((item) => (
            <article key={item.id} className="rounded-[16px] border border-[#e5e8ef] bg-white p-5">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <div className="flex flex-wrap items-center gap-2">
                    <strong className="text-[14px] text-[#18181a]">{ACTION_LABELS[item.action_type]}</strong>
                    <span className="rounded-full bg-[#f1f3f6] px-2 py-1 text-[11px]">{item.resource_name}</span>
                    <span className={cn('rounded-full px-2 py-1 text-[11px]', item.status === 'pending' ? 'bg-[#fff4d6] text-[#8a5b00]' : item.status === 'approved' ? 'bg-[#e9f8ef] text-[#237a45]' : 'bg-[#fdecec] text-[#a33a3a]')}>{statusLabel(item.status)}</span>
                  </div>
                  <p className="mt-2 text-[13px] text-[#464c5e]">{item.summary}</p>
                  <p className="mt-2 text-[11px] text-[#858b9c]">申请岗位：{ROLE_LABELS[item.requester_business_role] || item.requester_business_role} · {formatTime(item.requested_at)}</p>
                  {item.decision_reason && <p className="mt-2 text-[12px] text-[#657087]">审批意见：{item.decision_reason}</p>}
                  {item.invalidation_reason && (
                    <p className="mt-2 rounded-[8px] bg-[#fff3f3] px-3 py-2 text-[12px] text-[#a33a3a]">
                      失效原因：{item.invalidation_reason} · {formatTime(item.invalidated_at)}
                    </p>
                  )}
                  <p className="mt-2 font-mono text-[10px] text-[#9aa0af]">
                    内容摘要 {(item.content_digest || 'legacy-unverified').slice(0, 20)}… · 资源摘要 {(item.resource_snapshot_digest || 'legacy-unverified').slice(0, 20)}…
                  </p>
                </div>
                {canApprove && item.status === 'pending' && item.requester_user_id !== currentUser.id && (
                  <div className="flex gap-2">
                    <Button variant="outline" size="sm" onClick={() => { setDecisionTarget(item); setDecisionKind('reject'); }}>拒绝</Button>
                    <Button size="sm" onClick={() => { setDecisionTarget(item); setDecisionKind('approve'); }}>批准</Button>
                  </div>
                )}
                {canApprove && item.status === 'pending' && item.requester_user_id === currentUser.id && (
                  <span className="text-[11px] text-[#b26a00]">职责分离：不能审批自己的申请</span>
                )}
              </div>
            </article>
          ))}
        </div>
      ) : (
        <div className="mt-4 space-y-3">
          {approvals.every((item) => !item.execution) && !loading && (
            <p className="rounded-[16px] border border-[#e5e8ef] bg-white p-10 text-center text-[13px] text-[#858b9c]">暂无执行任务。批准高风险操作后，系统会原子创建执行任务。</p>
          )}
          {approvals.filter((item) => item.execution).map((item) => {
            const execution = item.execution as BusinessExecution;
            const canRetry = ['failed', 'retry_wait', 'compensation_failed', 'manual_resolution_required'].includes(execution.status);
            const canCompensate = execution.status === 'succeeded' && item.requester_user_id !== currentUser.id;
            return (
              <article key={execution.id} className="rounded-[16px] border border-[#e5e8ef] bg-white p-5">
                <div className="flex flex-wrap items-start justify-between gap-4">
                  <div className="min-w-[260px] flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <strong className="text-[14px] text-[#18181a]">{ACTION_LABELS[item.action_type]}</strong>
                      <span className="rounded-full bg-[#f1f3f6] px-2 py-1 text-[11px]">{item.resource_name}</span>
                      <span className={cn(
                        'rounded-full px-2 py-1 text-[11px]',
                        execution.status === 'succeeded' || execution.status === 'compensated'
                          ? 'bg-[#e9f8ef] text-[#237a45]'
                          : execution.status === 'queued' || execution.status === 'running' || execution.status === 'retry_wait'
                            ? 'bg-[#fff4d6] text-[#8a5b00]'
                            : 'bg-[#fdecec] text-[#a33a3a]',
                      )}>{executionStatusLabel(execution.status)}</span>
                      <span className="rounded-full bg-[#eef3ff] px-2 py-1 text-[11px] text-[#315ea8]">{execution.environment} · {execution.connector_type}</span>
                    </div>
                    <p className="mt-2 text-[13px] text-[#464c5e]">{item.summary}</p>
                    <p className="mt-2 text-[11px] text-[#858b9c]">尝试 {execution.attempt_count}/{execution.max_attempts} · 外部操作号 {execution.external_operation_id || '-'} · 下次尝试 {formatTime(execution.next_attempt_at)}</p>
                    {execution.last_error_message && <p className="mt-2 text-[12px] text-[#a33a3a]">{execution.last_error_code}: {execution.last_error_message}</p>}
                    {Object.keys(execution.receipt || {}).length > 0 && (
                      <details className="mt-3 rounded-[10px] bg-[#f7f8fa] p-3 text-[11px] text-[#535b6c]">
                        <summary className="cursor-pointer">查看脱敏回执</summary>
                        <pre className="mt-2 max-h-[220px] overflow-auto whitespace-pre-wrap">{JSON.stringify(execution.receipt, null, 2)}</pre>
                      </details>
                    )}
                  </div>
                  {canApprove && (
                    <div className="flex gap-2">
                      {canRetry && <Button variant="outline" size="sm" onClick={() => { setExecutionTarget(item); setExecutionCommand('retry'); }}>安全重试</Button>}
                      {canCompensate && <Button variant="outline" size="sm" onClick={() => { setExecutionTarget(item); setExecutionCommand('compensate'); }}>发起补偿</Button>}
                    </div>
                  )}
                </div>
              </article>
            );
          })}
        </div>
      )}

      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent aria-describedby={undefined} className="sm:max-w-[520px]">
          <DialogTitle>新增业务资源</DialogTitle>
          <label className="space-y-2 text-[13px]">资源类型
            <select value={createType} onChange={(event) => { const next = event.target.value as ResourceType; setCreateType(next); setCreateMetadata(JSON.stringify(RESOURCE_METADATA_TEMPLATES[next], null, 2)); }} className="h-10 w-full rounded-[8px] border border-input bg-background px-3">
              {(Object.keys(RESOURCE_LABELS) as ResourceType[]).map((type) => <option key={type} value={type}>{RESOURCE_LABELS[type]}</option>)}
            </select>
          </label>
          <label className="space-y-2 text-[13px]">资源编码<Input value={createCode} onChange={(event) => setCreateCode(event.target.value)} placeholder="例如 AMZ-US-FLAGSHIP" /></label>
          <label className="space-y-2 text-[13px]">资源名称<Input value={createName} onChange={(event) => setCreateName(event.target.value)} placeholder="例如 Amazon 美国旗舰店" /></label>
          <label className="space-y-2 text-[13px]">连接配置（JSON，不含密钥）<Textarea rows={8} value={createMetadata} onChange={(event) => setCreateMetadata(event.target.value)} /></label>
          <p className="text-[12px] text-[#858b9c]">只填写账号标识、端点和 auth_profile。密钥必须通过环境变量提供，禁止写入这里。</p>
          <DialogFooter><Button variant="outline" onClick={() => setCreateOpen(false)}>取消</Button><Button disabled={busy} onClick={() => void saveResource()}>创建</Button></DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={Boolean(executionTarget)} onOpenChange={(open) => !open && setExecutionTarget(null)}>
        <DialogContent aria-describedby={undefined} className="sm:max-w-[520px]">
          <DialogTitle>{executionCommand === 'retry' ? '安全重试执行任务' : '发起补偿操作'}</DialogTitle>
          <p className="text-[13px] text-[#464c5e]">{executionTarget?.summary}</p>
          <p className="text-[12px] text-[#b26a00]">远端结果不明时请先人工核对外部平台。补偿是新的业务操作，也可能失败。</p>
          <label className="space-y-2 text-[13px]">操作原因<Textarea rows={4} value={executionReason} onChange={(event) => setExecutionReason(event.target.value)} placeholder="填写核对依据、恢复目标和风险判断" /></label>
          <DialogFooter><Button variant="outline" onClick={() => setExecutionTarget(null)}>取消</Button><Button disabled={busy} onClick={() => void controlExecution()}>{executionCommand === 'retry' ? '确认重新入队' : '确认发起补偿'}</Button></DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={Boolean(actionResource)} onOpenChange={(open) => !open && setActionResource(null)}>
        <DialogContent aria-describedby={undefined} className="sm:max-w-[620px]">
          <DialogTitle>发起高风险操作 · {actionResource?.name}</DialogTitle>
          <label className="space-y-2 text-[13px]">操作类型
            <select value={actionType} onChange={(event) => changeAction(event.target.value as ActionType)} className="h-10 w-full rounded-[8px] border border-input bg-background px-3">
              {allowedActions.filter((action) => actionResource && ACTION_RESOURCE_TYPES[action].includes(actionResource.resource_type)).map((action) => <option key={action} value={action}>{ACTION_LABELS[action]}</option>)}
            </select>
          </label>
          <label className="space-y-2 text-[13px]">申请说明<Input value={actionSummary} onChange={(event) => setActionSummary(event.target.value)} placeholder="说明业务原因、影响范围和回滚方案" /></label>
          <label className="space-y-2 text-[13px]">操作参数（JSON）<Textarea rows={8} value={actionPayload} onChange={(event) => setActionPayload(event.target.value)} /></label>
          <p className="text-[12px] text-[#b26a00]">审批通过只代表获得执行授权，不代表外部平台已经执行。</p>
          <DialogFooter><Button variant="outline" onClick={() => setActionResource(null)}>取消</Button><Button disabled={busy} onClick={() => void submitAction()}>提交审批</Button></DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={Boolean(decisionTarget)} onOpenChange={(open) => !open && setDecisionTarget(null)}>
        <DialogContent aria-describedby={undefined} className="sm:max-w-[520px]">
          <DialogTitle>{decisionKind === 'approve' ? '批准高风险操作' : '拒绝高风险操作'}</DialogTitle>
          <p className="text-[13px] text-[#464c5e]">{decisionTarget?.summary}</p>
          <label className="space-y-2 text-[13px]">审批意见<Textarea rows={4} value={decisionReason} onChange={(event) => setDecisionReason(event.target.value)} placeholder="填写审批依据、约束或拒绝原因" /></label>
          <DialogFooter><Button variant="outline" onClick={() => setDecisionTarget(null)}>取消</Button><Button disabled={busy} variant={decisionKind === 'reject' ? 'destructive' : 'default'} onClick={() => void decide()}>{decisionKind === 'approve' ? '确认批准' : '确认拒绝'}</Button></DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
