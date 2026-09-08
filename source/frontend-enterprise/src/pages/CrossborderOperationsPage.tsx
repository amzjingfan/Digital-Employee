import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';

import { api, TENANT_ID } from '@/api/client';
import type { EnterpriseAuthUser } from '@/auth';
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
import OffsiteChannelAssetsPanel from '@/pages/offsite/OffsiteChannelAssetsPanel';

type TraceEvent = {
  id: string;
  event_type: string;
  actor_type: string;
  actor_business_role?: string | null;
  from_status?: string | null;
  to_status?: string | null;
  detail: Record<string, unknown>;
  occurred_at: string;
};

type AfterSalesCase = {
  id: string;
  case_key: string;
  store_resource_id: string;
  store_code: string;
  platform: string;
  marketplace_country: string;
  language: string;
  order_reference_masked: string;
  status: string;
  category?: string | null;
  risk_level: string;
  needs_human: boolean;
  human_reason?: string | null;
  task_id: string;
  approval_request_id?: string | null;
  approval_status?: string | null;
  order_snapshot: Record<string, unknown>;
  citations: Array<Record<string, unknown>>;
  recommendation: Record<string, unknown>;
  draft_reply?: string | null;
  root_cause?: string | null;
  follow_up_task_ids: string[];
  version: number;
  created_at: string;
  updated_at: string;
  closed_at?: string | null;
  events: TraceEvent[];
};

type LogisticsAnomaly = {
  id: string;
  fingerprint: string;
  carrier_resource_id: string;
  carrier_code: string;
  store_resource_id?: string | null;
  platform: string;
  order_reference_masked: string;
  status_event_id: string;
  shipment_status: string;
  anomaly_type: string;
  status: string;
  severity: string;
  customer_impact: string;
  cluster_key: string;
  dimensions: Record<string, unknown>;
  evidence: Record<string, unknown>;
  escalation_targets: string[];
  follow_up_task_ids: string[];
  task_id: string;
  occurrence_count: number;
  deadline_at?: string | null;
  first_observed_at: string;
  last_observed_at: string;
  resolution?: string | null;
  version: number;
  updated_at: string;
  events: TraceEvent[];
};

type IntegrationHealth = {
  id: string;
  dependency_key: string;
  display_name: string;
  domain: string;
  status: string;
  effective_status: string;
  reason_code?: string | null;
  message: string;
  recovery_hint: string;
  source: string;
  last_success_at?: string | null;
  observed_at: string;
  stale_after_seconds: number;
  version: number;
  updated_at: string;
  events: TraceEvent[];
};

type Overview = {
  after_sales_open: number;
  after_sales_needs_human: number;
  logistics_open: number;
  logistics_high_risk: number;
  degraded_dependencies: number;
  generated_at: string;
};

type BusinessResource = {
  id: string;
  resource_type: 'store' | 'carrier' | 'ad_account' | 'supplier';
  code: string;
  name: string;
  status: string;
};

type Props = { currentUser: EnterpriseAuthUser; onLogout: () => void };
type Tab = 'after-sales' | 'logistics' | 'health' | 'offsite';

const CASE_STATUS: Record<string, string> = {
  intake: '待查询', queried: '待分类', classified: '待拟稿', drafted: '待结案',
  waiting_approval: '待审批', needs_human: '需人工', closed: '已结案', rejected: '已驳回',
};
const ANOMALY_STATUS: Record<string, string> = {
  detected: '已识别', clustered: '已聚类', escalated: '已升级', resolved: '已解决',
};
const ANOMALY_TYPE: Record<string, string> = {
  overdue: '履约超时', no_first_scan: '无首扫', stalled: '轨迹停滞', customs_hold: '清关滞留',
  delivery_dispute: '妥投争议', appointment_issue: '预约异常',
};

function formatTime(value?: string | null): string {
  if (!value) return '-';
  return new Intl.DateTimeFormat(undefined, {
    month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit',
  }).format(new Date(value));
}

function statusClass(status: string): string {
  if (['critical', 'unavailable', 'needs_human', 'rejected'].includes(status)) return 'bg-[#fff0ef] text-[#b42318]';
  if (['high', 'degraded', 'stale', 'waiting_approval'].includes(status)) return 'bg-[#fff5e7] text-[#9a5b13]';
  if (['healthy', 'closed', 'resolved'].includes(status)) return 'bg-[#edf9f4] text-[#23735f]';
  return 'bg-[#eef3ff] text-[#315ea8]';
}

function Pill({ children, status }: { children: ReactNode; status: string }) {
  return <span className={cn('rounded-full px-2.5 py-1 text-[11px]', statusClass(status))}>{children}</span>;
}

function TraceTimeline({ events }: { events: TraceEvent[] }) {
  return <div className="space-y-2">
    {events.length === 0 && <p className="py-3 text-[12px] text-[#858b9c]">列表视图隐藏 Trace；选择记录后加载。</p>}
    {events.map((event) => <div key={event.id} className="rounded-[11px] bg-[#f7f8fa] px-3 py-2">
      <div className="flex items-center justify-between gap-3 text-[11px] text-[#858b9c]">
        <span>{event.event_type} · {event.actor_business_role || event.actor_type}</span>
        <span>{formatTime(event.occurred_at)}</span>
      </div>
      <p className="mt-1 text-[12px] text-[#464c5e]">{event.from_status || '创建'} → {event.to_status || '保持'}</p>
    </div>)}
  </div>;
}

export default function CrossborderOperationsPage({ currentUser, onLogout }: Props) {
  const manager = currentUser.role === 'admin' || currentUser.business_role === 'operations_supervisor';
  const canAfterSales = manager || currentUser.business_role === 'after_sales_specialist';
  const canMutateLogistics = manager || currentUser.business_role === 'logistics_exception_specialist';
  const canViewLogistics = canMutateLogistics || ['after_sales_specialist', 'procurement_specialist'].includes(currentUser.business_role || '');
  const canOffsite = manager || ['tiktok_bd_specialist', 'tiktok_tap_manager'].includes(currentUser.business_role || '');
  const initialTab: Tab = canOffsite && !manager
    ? 'offsite'
    : currentUser.business_role === 'logistics_exception_specialist'
      ? 'logistics'
      : canAfterSales ? 'after-sales' : 'health';
  const [tab, setTab] = useState<Tab>(initialTab);
  const [overview, setOverview] = useState<Overview | null>(null);
  const [cases, setCases] = useState<AfterSalesCase[]>([]);
  const [anomalies, setAnomalies] = useState<LogisticsAnomaly[]>([]);
  const [health, setHealth] = useState<IntegrationHealth[]>([]);
  const [resources, setResources] = useState<BusinessResource[]>([]);
  const [selectedCase, setSelectedCase] = useState<AfterSalesCase | null>(null);
  const [selectedAnomaly, setSelectedAnomaly] = useState<LogisticsAnomaly | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [dialog, setDialog] = useState<'case' | 'draft' | 'close' | 'anomaly' | 'escalate' | 'resolve' | 'health' | null>(null);
  const [form, setForm] = useState<Record<string, string | boolean>>({});

  const stores = resources.filter((item) => item.resource_type === 'store' && item.status === 'active');
  const carriers = resources.filter((item) => item.resource_type === 'carrier' && item.status === 'active');
  const selectedCaseId = selectedCase?.id || '';
  const selectedAnomalyId = selectedAnomaly?.id || '';

  const loadCase = useCallback(async (caseId: string) => {
    const row = await api.get<AfterSalesCase>(`/api/enterprise/work-tasks/crossborder/after-sales/${encodeURIComponent(caseId)}?tenant_id=${encodeURIComponent(TENANT_ID)}`);
    setSelectedCase(row);
    setCases((current) => current.map((item) => item.id === row.id ? row : item));
  }, []);

  const loadAnomaly = useCallback(async (anomalyId: string) => {
    const row = await api.get<LogisticsAnomaly>(`/api/enterprise/work-tasks/crossborder/logistics/${encodeURIComponent(anomalyId)}?tenant_id=${encodeURIComponent(TENANT_ID)}`);
    setSelectedAnomaly(row);
    setAnomalies((current) => current.map((item) => item.id === row.id ? row : item));
  }, []);

  const loadAll = useCallback(async () => {
    setLoading(true);
    try {
      const calls: Array<Promise<unknown>> = [
        api.get<Overview>(`/api/enterprise/work-tasks/crossborder/overview?tenant_id=${encodeURIComponent(TENANT_ID)}`),
        api.get<IntegrationHealth[]>(`/api/enterprise/work-tasks/crossborder/integration-health?tenant_id=${encodeURIComponent(TENANT_ID)}`),
        api.get<BusinessResource[]>(`/api/enterprise/business-resources?tenant_id=${encodeURIComponent(TENANT_ID)}`),
      ];
      if (canAfterSales) calls.push(api.get<AfterSalesCase[]>(`/api/enterprise/work-tasks/crossborder/after-sales?tenant_id=${encodeURIComponent(TENANT_ID)}`));
      if (canViewLogistics) calls.push(api.get<LogisticsAnomaly[]>(`/api/enterprise/work-tasks/crossborder/logistics?tenant_id=${encodeURIComponent(TENANT_ID)}`));
      const results = await Promise.allSettled(calls);
      if (results[0].status === 'fulfilled') setOverview(results[0].value as Overview);
      if (results[1].status === 'fulfilled') setHealth(results[1].value as IntegrationHealth[]);
      if (results[2].status === 'fulfilled') setResources(results[2].value as BusinessResource[]);
      let index = 3;
      const caseResult = canAfterSales ? results[index] : undefined;
      if (caseResult?.status === 'fulfilled') {
        const rows = caseResult.value as AfterSalesCase[];
        setCases(rows);
        if (!selectedCaseId && rows[0]) void loadCase(rows[0].id);
        index += 1;
      }
      const logisticsResult = canViewLogistics ? results[index] : undefined;
      if (logisticsResult?.status === 'fulfilled') {
        const rows = logisticsResult.value as LogisticsAnomaly[];
        setAnomalies(rows);
        if (!selectedAnomalyId && rows[0]) void loadAnomaly(rows[0].id);
      }
    } finally {
      setLoading(false);
    }
  }, [canAfterSales, canViewLogistics, loadAnomaly, loadCase, selectedAnomalyId, selectedCaseId]);

  useEffect(() => { void loadAll(); }, [loadAll]);

  function openDialog(next: typeof dialog, defaults: Record<string, string | boolean>) {
    setForm(defaults);
    setDialog(next);
  }

  async function runAction(action: () => Promise<unknown>, success: string) {
    setBusy(true);
    try {
      await action();
      setDialog(null);
      notify.success(success);
      await loadAll();
      if (selectedCase) await loadCase(selectedCase.id).catch(() => setSelectedCase(null));
      if (selectedAnomaly) await loadAnomaly(selectedAnomaly.id).catch(() => setSelectedAnomaly(null));
    } catch (error) {
      notify.error(error instanceof Error ? error.message : '操作失败');
    } finally {
      setBusy(false);
    }
  }

  async function createCase() {
    await runAction(async () => {
      const row = await api.post<AfterSalesCase>('/api/enterprise/work-tasks/crossborder/after-sales', {
        tenant_id: TENANT_ID,
        case_key: String(form.case_key || ''),
        store_resource_id: String(form.store_resource_id || ''),
        platform: String(form.platform || 'Amazon'),
        marketplace_country: String(form.country || 'US'),
        language: String(form.language || 'en-US'),
        order_reference: String(form.order_reference || ''),
        summary: String(form.summary || ''),
      });
      setSelectedCase(row);
    }, '售后工单已进入专员队列');
  }

  async function recordQuery() {
    if (!selectedCase) return;
    await runAction(() => api.post(`/api/enterprise/work-tasks/crossborder/after-sales/${encodeURIComponent(selectedCase.id)}/query`, {
      tenant_id: TENANT_ID,
      expected_version: selectedCase.version,
      order_snapshot: {
        order_status: 'shipped', payment_status: 'paid', shipment_status: 'in_transit',
        logistics_status: 'stalled', sku_codes: ['DEMO-SKU'], currency: 'USD', order_amount: 39.9,
        updated_at: new Date().toISOString(), history: [{ event_code: 'PICKED_UP', status: 'complete', source: 'carrier', occurred_at: new Date(Date.now() - 48 * 3600_000).toISOString() }],
      },
      citations: [{
        source_id: 'kb-reviewed-aftersales-policy', title: '已审核售后政策', version: '1.0.0',
        scope: `${TENANT_ID}/store:${selectedCase.store_code}`, excerpt: '演示引用：实际接入时由混合检索返回。', retrieved_at: new Date().toISOString(),
      }],
      dependency_status: { orders: 'healthy', logistics: 'healthy', knowledge: 'healthy' },
      observed_at: new Date().toISOString(),
    }), '查询证据与知识引用已固化');
  }

  async function classifyCase() {
    if (!selectedCase) return;
    await runAction(() => api.post(`/api/enterprise/work-tasks/crossborder/after-sales/${encodeURIComponent(selectedCase.id)}/classify`, {
      tenant_id: TENANT_ID, expected_version: selectedCase.version, category: 'not_received', confidence: 0.92,
      risk_level: 'medium', exception_flags: [], note: '基于订单、轨迹和政策引用分类。',
    }), '工单已分类为未收货');
  }

  async function draftCase() {
    if (!selectedCase) return;
    const approval = Boolean(form.requires_approval);
    await runAction(() => api.post(`/api/enterprise/work-tasks/crossborder/after-sales/${encodeURIComponent(selectedCase.id)}/draft`, {
      tenant_id: TENANT_ID, expected_version: selectedCase.version,
      recommendation: { action: approval ? 'refund' : 'customer_update', policy_version: '1.0.0' },
      reply_draft: String(form.reply_draft || ''), requires_approval: approval,
      refund_amount: approval ? Number(form.refund_amount || 0) : null,
      currency: approval ? String(form.currency || 'USD') : null,
      approval_summary: approval ? `售后工单 ${selectedCase.case_key} 退款审批` : '',
    }), approval ? '草稿已提交独立审批' : '回复草稿已生成，未发送');
  }

  async function resolveCaseException() {
    if (!selectedCase) return;
    await runAction(() => api.post(`/api/enterprise/work-tasks/crossborder/after-sales/${encodeURIComponent(selectedCase.id)}/resolve-exception`, {
      tenant_id: TENANT_ID, expected_version: selectedCase.version,
      resolution_note: '运营主管已人工核验订单、身份、轨迹和政策冲突。', resume_status: 'classified',
    }), '人工例外已核验，流程恢复');
  }

  async function closeCase() {
    if (!selectedCase) return;
    await runAction(() => api.post(`/api/enterprise/work-tasks/crossborder/after-sales/${encodeURIComponent(selectedCase.id)}/close`, {
      tenant_id: TENANT_ID, expected_version: selectedCase.version,
      root_cause: String(form.root_cause || ''), outcome: String(form.outcome || ''), follow_ups: [],
    }), '工单已结案并生成跨岗位跟进');
  }

  async function ingestAnomaly() {
    await runAction(async () => {
      const deadline = String(form.deadline_at || '');
      const result = await api.post<{ items: LogisticsAnomaly[] }>('/api/enterprise/work-tasks/crossborder/logistics/ingest', {
        tenant_id: TENANT_ID, batch_key: `manual:${currentUser.id}:${Date.now()}`,
        items: [{
          carrier_resource_id: String(form.carrier_resource_id || ''), store_resource_id: String(form.store_resource_id || '') || null,
          platform: String(form.platform || 'Amazon'), order_reference: String(form.order_reference || ''),
          status_event_id: String(form.status_event_id || ''), shipment_status: String(form.shipment_status || 'IN_TRANSIT'),
          anomaly_type: String(form.anomaly_type || 'stalled'), customer_impact: String(form.customer_impact || 'high'),
          deadline_at: deadline ? new Date(deadline).toISOString() : null, observed_at: new Date().toISOString(),
          channel: String(form.channel || 'FBA'), warehouse: String(form.warehouse || ''), country: String(form.country || 'US'),
          sku: String(form.sku || ''), batch: String(form.batch || ''),
          evidence: { source_record_id: String(form.status_event_id || ''), source_updated_at: new Date().toISOString(), tracking_status: String(form.shipment_status || 'IN_TRANSIT') },
        }],
      });
      if (result.items[0]) setSelectedAnomaly(result.items[0]);
    }, '物流异常已去重、聚类并进入队列');
  }

  async function escalateAnomaly() {
    if (!selectedAnomaly) return;
    await runAction(() => api.post(`/api/enterprise/work-tasks/crossborder/logistics/${encodeURIComponent(selectedAnomaly.id)}/escalate`, {
      tenant_id: TENANT_ID, expected_version: selectedAnomaly.version,
      targets: ['after_sales_specialist', 'procurement_specialist', 'operations_supervisor'],
      reason: String(form.reason || ''),
    }), '异常已升级至售后、采购和运营主管');
  }

  async function resolveAnomaly() {
    if (!selectedAnomaly) return;
    await runAction(() => api.post(`/api/enterprise/work-tasks/crossborder/logistics/${encodeURIComponent(selectedAnomaly.id)}/resolve`, {
      tenant_id: TENANT_ID, expected_version: selectedAnomaly.version, resolution: String(form.resolution || ''),
    }), '物流异常已解决');
  }

  async function reportHealth() {
    await runAction(() => api.post('/api/enterprise/work-tasks/crossborder/integration-health/report', {
      tenant_id: TENANT_ID, dependency_key: String(form.dependency_key || ''), display_name: String(form.display_name || ''),
      domain: String(form.domain || 'orders'), status: String(form.status || 'degraded'),
      reason_code: String(form.reason_code || '') || null, message: String(form.message || ''),
      recovery_hint: String(form.recovery_hint || ''), source: 'operator', observed_at: new Date().toISOString(), stale_after_seconds: 900,
    }), '依赖状态已更新并留痕');
  }

  const cards = useMemo(() => [
    ['售后待处理', overview?.after_sales_open ?? 0, overview?.after_sales_needs_human ? `${overview.after_sales_needs_human} 条需人工` : '无人工阻塞'],
    ['物流待处理', overview?.logistics_open ?? 0, overview?.logistics_high_risk ? `${overview.logistics_high_risk} 条高风险` : '无高风险'],
    ['异常依赖', overview?.degraded_dependencies ?? 0, overview?.degraded_dependencies ? '禁止静默降级' : '依赖正常'],
  ], [overview]);

  return <div className="min-h-full px-6 pb-12 pt-8 lg:px-12">
    <AppHeader title="跨境业务闭环" description="售后、物流与站外渠道资产统一留痕；证据不足、过期或未经审批时不允许外部执行。" userName={currentUser.display_name || currentUser.username} onLogout={onLogout} />

    <div className="mt-6 grid gap-4 md:grid-cols-3">
      {cards.map(([label, value, note]) => <div key={String(label)} className="rounded-[18px] border border-[#e6e8ee] bg-white p-5">
        <p className="text-[12px] text-[#858b9c]">{label}</p><p className="mt-2 text-[30px] font-semibold text-[#202331]">{value}</p><p className="mt-1 text-[11px] text-[#667085]">{note}</p>
      </div>)}
    </div>

    <div className="mt-5 rounded-[14px] border border-[#f2d49a] bg-[#fff9ec] px-4 py-3 text-[12px] text-[#7a5014]">
      安全门禁：客户回复仅生成草稿；退款等高风险动作必须进入独立审批，申请人与审批人必须分离。订单标识仅保存摘要与掩码。
    </div>

    <div className="mt-5 flex flex-wrap gap-2">
      {canAfterSales && <Button variant={tab === 'after-sales' ? 'default' : 'outline'} onClick={() => setTab('after-sales')}>售后工单</Button>}
      {canViewLogistics && <Button variant={tab === 'logistics' ? 'default' : 'outline'} onClick={() => setTab('logistics')}>物流异常</Button>}
      {canOffsite && <Button variant={tab === 'offsite' ? 'default' : 'outline'} onClick={() => setTab('offsite')}>站外渠道资产</Button>}
      <Button variant={tab === 'health' ? 'default' : 'outline'} onClick={() => setTab('health')}>依赖与降级</Button>
    </div>

    {loading && <p className="mt-8 text-[13px] text-[#858b9c]">正在加载业务闭环…</p>}

    {!loading && tab === 'after-sales' && canAfterSales && <div className="mt-5 grid gap-5 xl:grid-cols-[360px_minmax(0,1fr)]">
      <aside className="rounded-[18px] border border-[#e6e8ee] bg-white p-3">
        <div className="flex items-center justify-between px-2 pb-3"><strong className="text-[14px]">售后工单</strong><Button size="sm" onClick={() => openDialog('case', { case_key: `CASE-${Date.now()}`, store_resource_id: stores[0]?.id || '', platform: 'Amazon', country: 'US', language: 'en-US', order_reference: '', summary: '' })}>新建</Button></div>
        {cases.length === 0 && <p className="py-10 text-center text-[12px] text-[#858b9c]">暂无售后工单</p>}
        <div className="space-y-2">{cases.map((item) => <button key={item.id} type="button" onClick={() => void loadCase(item.id)} className={cn('w-full rounded-[12px] border px-3 py-3 text-left', selectedCase?.id === item.id ? 'border-[#92c8bc] bg-[#f1faf7]' : 'border-transparent hover:bg-[#f7f8fa]')}>
          <div className="flex justify-between gap-2"><strong className="text-[12px] text-[#303444]">{item.order_reference_masked}</strong><Pill status={item.status}>{CASE_STATUS[item.status] || item.status}</Pill></div>
          <p className="mt-2 text-[11px] text-[#667085]">{item.platform} · {item.marketplace_country} · {item.store_code}</p><p className="mt-1 text-[10px] text-[#858b9c]">{formatTime(item.updated_at)}</p>
        </button>)}</div>
      </aside>
      <main>{selectedCase ? <div className="space-y-5">
        <section className="rounded-[18px] border border-[#e6e8ee] bg-white p-5">
          <div className="flex flex-wrap items-start justify-between gap-3"><div><div className="flex flex-wrap items-center gap-2"><h2 className="text-[18px] font-semibold">{selectedCase.case_key}</h2><Pill status={selectedCase.status}>{CASE_STATUS[selectedCase.status] || selectedCase.status}</Pill><Pill status={selectedCase.risk_level}>{selectedCase.risk_level}</Pill></div><p className="mt-2 text-[12px] text-[#667085]">订单 {selectedCase.order_reference_masked} · {selectedCase.platform} {selectedCase.marketplace_country} · {selectedCase.language}</p></div><a className="text-[12px] text-[#315ea8]" href={`/enterprise/work-tasks?task_id=${encodeURIComponent(selectedCase.task_id)}`}>打开统一任务</a></div>
          {selectedCase.human_reason && <p className="mt-3 rounded-[10px] bg-[#fff0ef] p-3 text-[12px] text-[#b42318]">人工接管原因：{selectedCase.human_reason}</p>}
          <div className="mt-4 flex flex-wrap gap-2">
            {selectedCase.status === 'intake' && <Button onClick={() => void recordQuery()}>固化查询与引用</Button>}
            {selectedCase.status === 'queried' && <Button onClick={() => void classifyCase()}>分类为未收货</Button>}
            {selectedCase.status === 'classified' && <Button onClick={() => openDialog('draft', { reply_draft: 'We are sorry for the delay. We checked the latest tracking evidence and will follow the reviewed policy.', requires_approval: false, refund_amount: '39.90', currency: 'USD' })}>生成回复草稿</Button>}
            {selectedCase.status === 'needs_human' && manager && <Button onClick={() => void resolveCaseException()}>主管核验并恢复</Button>}
            {['drafted', 'waiting_approval'].includes(selectedCase.status) && <Button disabled={selectedCase.status === 'waiting_approval' && selectedCase.approval_status !== 'approved'} onClick={() => openDialog('close', { root_cause: '承运商轨迹停滞，客户承诺时效未满足。', outcome: '已完成证据复核并形成客户回复草稿；未在本页面执行外部写操作。' })}>结案并建跟进</Button>}
            {selectedCase.approval_request_id && <a href="/enterprise/business-resources" className="inline-flex h-9 items-center rounded-md border px-3 text-[12px] text-[#315ea8]">审批 {selectedCase.approval_status || 'pending'}</a>}
          </div>
        </section>
        <div className="grid gap-5 lg:grid-cols-2"><section className="rounded-[18px] border border-[#e6e8ee] bg-white p-5"><h3 className="text-[14px] font-semibold">查询快照与引用</h3><pre className="mt-3 max-h-[260px] overflow-auto whitespace-pre-wrap rounded-[12px] bg-[#f7f8fa] p-3 text-[11px] text-[#505668]">{JSON.stringify({ order_snapshot: selectedCase.order_snapshot, citations: selectedCase.citations }, null, 2)}</pre></section><section className="rounded-[18px] border border-[#e6e8ee] bg-white p-5"><h3 className="text-[14px] font-semibold">业务 Trace</h3><div className="mt-3"><TraceTimeline events={selectedCase.events} /></div></section></div>
        {selectedCase.draft_reply && <section className="rounded-[18px] border border-[#e6e8ee] bg-white p-5"><h3 className="text-[14px] font-semibold">回复草稿（未发送）</h3><p className="mt-3 whitespace-pre-wrap text-[13px] leading-6 text-[#464c5e]">{selectedCase.draft_reply}</p></section>}
      </div> : <div className="rounded-[18px] border border-dashed p-12 text-center text-[13px] text-[#858b9c]">选择一条售后工单</div>}</main>
    </div>}

    {!loading && tab === 'logistics' && canViewLogistics && <div className="mt-5 grid gap-5 xl:grid-cols-[360px_minmax(0,1fr)]">
      <aside className="rounded-[18px] border border-[#e6e8ee] bg-white p-3"><div className="flex items-center justify-between px-2 pb-3"><strong className="text-[14px]">物流异常</strong>{canMutateLogistics && <Button size="sm" onClick={() => openDialog('anomaly', { carrier_resource_id: carriers[0]?.id || '', store_resource_id: stores[0]?.id || '', platform: 'Amazon', order_reference: '', status_event_id: `EVENT-${Date.now()}`, shipment_status: 'IN_TRANSIT', anomaly_type: 'stalled', customer_impact: 'high', deadline_at: '', channel: 'FBA', warehouse: '', country: 'US', sku: '', batch: '' })}>录入异常</Button>}</div>
        {anomalies.length === 0 && <p className="py-10 text-center text-[12px] text-[#858b9c]">暂无可见异常</p>}
        <div className="space-y-2">{anomalies.map((item) => <button key={item.id} type="button" onClick={() => void loadAnomaly(item.id)} className={cn('w-full rounded-[12px] border px-3 py-3 text-left', selectedAnomaly?.id === item.id ? 'border-[#92c8bc] bg-[#f1faf7]' : 'border-transparent hover:bg-[#f7f8fa]')}><div className="flex justify-between gap-2"><strong className="text-[12px]">{item.order_reference_masked}</strong><Pill status={item.severity}>{item.severity}</Pill></div><p className="mt-2 text-[11px] text-[#667085]">{ANOMALY_TYPE[item.anomaly_type] || item.anomaly_type} · {ANOMALY_STATUS[item.status] || item.status}</p><p className="mt-1 text-[10px] text-[#858b9c]">重复 {item.occurrence_count} 次 · {formatTime(item.updated_at)}</p></button>)}</div>
      </aside>
      <main>{selectedAnomaly ? <div className="space-y-5"><section className="rounded-[18px] border border-[#e6e8ee] bg-white p-5"><div className="flex flex-wrap justify-between gap-3"><div><div className="flex flex-wrap items-center gap-2"><h2 className="text-[18px] font-semibold">{ANOMALY_TYPE[selectedAnomaly.anomaly_type] || selectedAnomaly.anomaly_type}</h2><Pill status={selectedAnomaly.status}>{ANOMALY_STATUS[selectedAnomaly.status] || selectedAnomaly.status}</Pill><Pill status={selectedAnomaly.severity}>{selectedAnomaly.severity}</Pill></div><p className="mt-2 text-[12px] text-[#667085]">{selectedAnomaly.order_reference_masked} · {selectedAnomaly.carrier_code} · 截止 {formatTime(selectedAnomaly.deadline_at)}</p></div><a className="text-[12px] text-[#315ea8]" href={`/enterprise/work-tasks?task_id=${encodeURIComponent(selectedAnomaly.task_id)}`}>打开统一任务</a></div>
        {canMutateLogistics && selectedAnomaly.status !== 'resolved' && <div className="mt-4 flex gap-2"><Button onClick={() => openDialog('escalate', { reason: '平台时限临近，请售后主动沟通、采购评估批次风险、运营主管统筹。' })}>升级跨岗位</Button><Button variant="outline" onClick={() => openDialog('resolve', { resolution: '承运商已恢复扫描并确认新的妥投计划。' })}>标记解决</Button></div>}</section>
        <div className="grid gap-5 lg:grid-cols-2"><section className="rounded-[18px] border border-[#e6e8ee] bg-white p-5"><h3 className="text-[14px] font-semibold">聚类与证据</h3><p className="mt-2 break-all text-[11px] text-[#858b9c]">{selectedAnomaly.cluster_key}</p><pre className="mt-3 max-h-[280px] overflow-auto whitespace-pre-wrap rounded-[12px] bg-[#f7f8fa] p-3 text-[11px]">{JSON.stringify({ dimensions: selectedAnomaly.dimensions, evidence: selectedAnomaly.evidence, escalation_targets: selectedAnomaly.escalation_targets, follow_up_task_ids: selectedAnomaly.follow_up_task_ids }, null, 2)}</pre></section><section className="rounded-[18px] border border-[#e6e8ee] bg-white p-5"><h3 className="text-[14px] font-semibold">业务 Trace</h3><div className="mt-3"><TraceTimeline events={selectedAnomaly.events} /></div></section></div>
      </div> : <div className="rounded-[18px] border border-dashed p-12 text-center text-[13px] text-[#858b9c]">选择一条物流异常</div>}</main>
    </div>}

    {!loading && tab === 'health' && <div className="mt-5 rounded-[18px] border border-[#e6e8ee] bg-white p-5"><div className="flex items-center justify-between"><div><h2 className="text-[16px] font-semibold">依赖与降级状态</h2><p className="mt-1 text-[12px] text-[#858b9c]">超时未上报自动显示 stale；故障原因、恢复建议和变更事件均可审计。</p></div>{manager && <Button onClick={() => openDialog('health', { dependency_key: 'amazon-orders-api', display_name: 'Amazon Orders API', domain: 'orders', status: 'degraded', reason_code: 'rate_limited', message: '接口限流，查询结果可能延迟。', recovery_hint: '按退避策略重试并人工核验临近时限工单。' })}>上报状态</Button>}</div>
      <div className="mt-5 grid gap-3 md:grid-cols-2 xl:grid-cols-3">{health.map((item) => <div key={item.id} className="rounded-[14px] border border-[#eceef2] p-4"><div className="flex items-center justify-between"><strong className="text-[13px]">{item.display_name}</strong><Pill status={item.effective_status}>{item.effective_status}</Pill></div><p className="mt-2 text-[11px] text-[#858b9c]">{item.domain} · {item.dependency_key} · v{item.version}</p>{item.message && <p className="mt-3 text-[12px] text-[#505668]">{item.message}</p>}{item.recovery_hint && <p className="mt-2 rounded-[9px] bg-[#f7f8fa] p-2 text-[11px] text-[#667085]">恢复：{item.recovery_hint}</p>}<p className="mt-2 text-[10px] text-[#858b9c]">观测 {formatTime(item.observed_at)} · TTL {item.stale_after_seconds}s</p></div>)}</div>
      {health.length === 0 && <p className="py-12 text-center text-[13px] text-[#858b9c]">尚无健康度上报；生产接入时应为每个订单、支付、物流、知识库和审批依赖建立探针。</p>}
    </div>}

    {!loading && tab === 'offsite' && canOffsite && <OffsiteChannelAssetsPanel currentUser={currentUser} stores={stores} />}

    <Dialog open={dialog === 'case'} onOpenChange={(open) => !open && setDialog(null)}><DialogContent><DialogTitle>新建售后工单</DialogTitle><label className="text-[12px]">店铺<select className="mt-1 h-10 w-full rounded-md border px-3" value={String(form.store_resource_id || '')} onChange={(event) => setForm({ ...form, store_resource_id: event.target.value })}>{stores.map((item) => <option key={item.id} value={item.id}>{item.name} · {item.code}</option>)}</select></label><Input value={String(form.case_key || '')} onChange={(event) => setForm({ ...form, case_key: event.target.value })} placeholder="工单业务键"/><div className="grid grid-cols-3 gap-2"><Input value={String(form.platform || '')} onChange={(event) => setForm({ ...form, platform: event.target.value })} placeholder="平台"/><Input value={String(form.country || '')} onChange={(event) => setForm({ ...form, country: event.target.value })} placeholder="国家"/><Input value={String(form.language || '')} onChange={(event) => setForm({ ...form, language: event.target.value })} placeholder="语言"/></div><Input value={String(form.order_reference || '')} onChange={(event) => setForm({ ...form, order_reference: event.target.value })} placeholder="订单号（仅摘要与掩码落库）"/><Textarea value={String(form.summary || '')} onChange={(event) => setForm({ ...form, summary: event.target.value })} placeholder="客户问题摘要（不要录入姓名、电话、地址）"/><DialogFooter><Button variant="outline" onClick={() => setDialog(null)}>取消</Button><Button disabled={busy || stores.length === 0} onClick={() => void createCase()}>进入售后队列</Button></DialogFooter></DialogContent></Dialog>

    <Dialog open={dialog === 'draft'} onOpenChange={(open) => !open && setDialog(null)}><DialogContent><DialogTitle>生成回复草稿</DialogTitle><Textarea rows={6} value={String(form.reply_draft || '')} onChange={(event) => setForm({ ...form, reply_draft: event.target.value })}/><label className="flex items-center gap-2 text-[12px]"><input type="checkbox" checked={Boolean(form.requires_approval)} onChange={(event) => setForm({ ...form, requires_approval: event.target.checked })}/>包含退款，进入双人审批</label>{Boolean(form.requires_approval) && <div className="grid grid-cols-2 gap-2"><Input type="number" value={String(form.refund_amount || '')} onChange={(event) => setForm({ ...form, refund_amount: event.target.value })} placeholder="退款金额"/><Input value={String(form.currency || 'USD')} onChange={(event) => setForm({ ...form, currency: event.target.value.toUpperCase() })} placeholder="USD"/></div>}<p className="text-[11px] text-[#858b9c]">保存草稿不会发送消息；勾选退款后会固化审批内容摘要，后续内容漂移将使审批失效。</p><DialogFooter><Button variant="outline" onClick={() => setDialog(null)}>取消</Button><Button disabled={busy} onClick={() => void draftCase()}>保存草稿</Button></DialogFooter></DialogContent></Dialog>

    <Dialog open={dialog === 'close'} onOpenChange={(open) => !open && setDialog(null)}><DialogContent><DialogTitle>结案与根因回流</DialogTitle><Textarea rows={3} value={String(form.root_cause || '')} onChange={(event) => setForm({ ...form, root_cause: event.target.value })} placeholder="根因"/><Textarea rows={3} value={String(form.outcome || '')} onChange={(event) => setForm({ ...form, outcome: event.target.value })} placeholder="处理结果"/><p className="text-[11px] text-[#858b9c]">系统将按工单类型自动创建 Listing、物流或采购跟进任务，并保留来源链。</p><DialogFooter><Button variant="outline" onClick={() => setDialog(null)}>取消</Button><Button disabled={busy} onClick={() => void closeCase()}>确认结案</Button></DialogFooter></DialogContent></Dialog>

    <Dialog open={dialog === 'anomaly'} onOpenChange={(open) => !open && setDialog(null)}><DialogContent><DialogTitle>录入物流异常</DialogTitle><div className="grid grid-cols-2 gap-2"><label className="text-[11px]">物流商<select className="mt-1 h-10 w-full rounded-md border px-2" value={String(form.carrier_resource_id || '')} onChange={(event) => setForm({ ...form, carrier_resource_id: event.target.value })}>{carriers.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label><label className="text-[11px]">店铺<select className="mt-1 h-10 w-full rounded-md border px-2" value={String(form.store_resource_id || '')} onChange={(event) => setForm({ ...form, store_resource_id: event.target.value })}><option value="">无</option>{stores.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label></div><Input value={String(form.order_reference || '')} onChange={(event) => setForm({ ...form, order_reference: event.target.value })} placeholder="订单号"/><div className="grid grid-cols-2 gap-2"><Input value={String(form.status_event_id || '')} onChange={(event) => setForm({ ...form, status_event_id: event.target.value })} placeholder="状态事件 ID"/><Input value={String(form.shipment_status || '')} onChange={(event) => setForm({ ...form, shipment_status: event.target.value })} placeholder="物流状态"/></div><div className="grid grid-cols-2 gap-2"><select className="h-10 rounded-md border px-3" value={String(form.anomaly_type || '')} onChange={(event) => setForm({ ...form, anomaly_type: event.target.value })}>{Object.entries(ANOMALY_TYPE).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select><select className="h-10 rounded-md border px-3" value={String(form.customer_impact || '')} onChange={(event) => setForm({ ...form, customer_impact: event.target.value })}><option value="low">低影响</option><option value="medium">中影响</option><option value="high">高影响</option><option value="critical">严重</option></select></div><label className="text-[11px]">平台截止时间<Input type="datetime-local" value={String(form.deadline_at || '')} onChange={(event) => setForm({ ...form, deadline_at: event.target.value })}/></label><div className="grid grid-cols-3 gap-2"><Input value={String(form.warehouse || '')} onChange={(event) => setForm({ ...form, warehouse: event.target.value })} placeholder="仓库"/><Input value={String(form.sku || '')} onChange={(event) => setForm({ ...form, sku: event.target.value })} placeholder="SKU"/><Input value={String(form.batch || '')} onChange={(event) => setForm({ ...form, batch: event.target.value })} placeholder="批次"/></div><DialogFooter><Button variant="outline" onClick={() => setDialog(null)}>取消</Button><Button disabled={busy || carriers.length === 0} onClick={() => void ingestAnomaly()}>去重并入队</Button></DialogFooter></DialogContent></Dialog>

    <Dialog open={dialog === 'escalate'} onOpenChange={(open) => !open && setDialog(null)}><DialogContent><DialogTitle>升级跨岗位</DialogTitle><Textarea rows={4} value={String(form.reason || '')} onChange={(event) => setForm({ ...form, reason: event.target.value })}/><p className="text-[11px] text-[#858b9c]">将分别创建售后、采购、运营主管待办；相同异常和岗位不会重复建单。</p><DialogFooter><Button variant="outline" onClick={() => setDialog(null)}>取消</Button><Button disabled={busy} onClick={() => void escalateAnomaly()}>确认升级</Button></DialogFooter></DialogContent></Dialog>
    <Dialog open={dialog === 'resolve'} onOpenChange={(open) => !open && setDialog(null)}><DialogContent><DialogTitle>解决物流异常</DialogTitle><Textarea rows={4} value={String(form.resolution || '')} onChange={(event) => setForm({ ...form, resolution: event.target.value })}/><DialogFooter><Button variant="outline" onClick={() => setDialog(null)}>取消</Button><Button disabled={busy} onClick={() => void resolveAnomaly()}>确认解决</Button></DialogFooter></DialogContent></Dialog>

    <Dialog open={dialog === 'health'} onOpenChange={(open) => !open && setDialog(null)}><DialogContent><DialogTitle>上报依赖状态</DialogTitle><div className="grid grid-cols-2 gap-2"><Input value={String(form.dependency_key || '')} onChange={(event) => setForm({ ...form, dependency_key: event.target.value })} placeholder="依赖键"/><Input value={String(form.display_name || '')} onChange={(event) => setForm({ ...form, display_name: event.target.value })} placeholder="显示名称"/></div><div className="grid grid-cols-2 gap-2"><select className="h-10 rounded-md border px-3" value={String(form.domain || '')} onChange={(event) => setForm({ ...form, domain: event.target.value })}>{['orders','payments','shipping','logistics','knowledge','approvals','tasks'].map((item) => <option key={item} value={item}>{item}</option>)}</select><select className="h-10 rounded-md border px-3" value={String(form.status || '')} onChange={(event) => setForm({ ...form, status: event.target.value })}><option value="healthy">healthy</option><option value="degraded">degraded</option><option value="unavailable">unavailable</option></select></div><Input value={String(form.reason_code || '')} onChange={(event) => setForm({ ...form, reason_code: event.target.value })} placeholder="原因代码"/><Textarea value={String(form.message || '')} onChange={(event) => setForm({ ...form, message: event.target.value })} placeholder="对业务的影响"/><Textarea value={String(form.recovery_hint || '')} onChange={(event) => setForm({ ...form, recovery_hint: event.target.value })} placeholder="恢复建议"/><DialogFooter><Button variant="outline" onClick={() => setDialog(null)}>取消</Button><Button disabled={busy} onClick={() => void reportHealth()}>上报并留痕</Button></DialogFooter></DialogContent></Dialog>
  </div>;
}
