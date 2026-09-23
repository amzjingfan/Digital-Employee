import { useCallback, useEffect, useState } from 'react';

import { api } from '@/api/client';
import type { EnterpriseAuthUser } from '@/auth';
import { notify } from '@/components/ui/app-toast';
import { Button } from '@/components/ui/button';

type Fact = {
  id: string;
  domain: string;
  business_key: string;
  observed_at: string;
  source_label: string;
  source_kind: string;
  assigned_bd_user_id: string;
  values: Record<string, unknown>;
  latest_verdict: string | null;
};
type Metric = {
  code: string; version: number; label: string; value: string | null;
  unit: string; reason: string | null; formula: string; timezone: string; window: string;
};
type HistoryWorkspace = {
  total_count: number;
  reviewed_count: number;
  eligible_reviewed_count: number;
  exit_ready: boolean;
  can_confirm: boolean;
  facts: Fact[];
  metrics: Metric[];
  bd_options: { id: string; label: string }[];
};
type ValidationWorkspace = {
  recent_runs: { id: string; mode: string; status: string; source_label: string | null }[];
};

const domains = [
  ['all', '全部'], ['sample', '样品'], ['order', '订单'], ['logistics', '物流'],
  ['video', '视频'], ['attribution', '归因'], ['gmv', 'GMV'],
] as const;
const inputClass = 'min-h-9 rounded-lg border border-[#d9deea] bg-white px-3 text-[12px]';

export default function TikTokHistoryPanel({ currentUser }: { currentUser: EnterpriseAuthUser }) {
  const [history, setHistory] = useState<HistoryWorkspace | null>(null);
  const [validation, setValidation] = useState<ValidationWorkspace | null>(null);
  const [domain, setDomain] = useState('all');
  const [creatorId, setCreatorId] = useState('');
  const [productId, setProductId] = useState('');
  const [observedFrom, setObservedFrom] = useState('');
  const [observedUntil, setObservedUntil] = useState('');
  const [page, setPage] = useState(1);
  const [busy, setBusy] = useState(false);
  const [runId, setRunId] = useState('');
  const [assigneeId, setAssigneeId] = useState('');
  const [sourceKind, setSourceKind] = useState<'synthetic' | 'approved_redacted_history'>('synthetic');
  const [file, setFile] = useState<File | null>(null);
  const [reviewFactId, setReviewFactId] = useState('');
  const [verdict, setVerdict] = useState<'matched' | 'difference' | 'needs_review'>('matched');
  const [reason, setReason] = useState('');
  const [approvalRef, setApprovalRef] = useState('');
  const isAdmin = currentUser.role === 'admin';

  const load = useCallback(async () => {
    try {
      const filters = new URLSearchParams({ page: String(page), limit: '100' });
      if (domain !== 'all') filters.set('domain', domain);
      if (creatorId.trim()) filters.set('creator_id', creatorId.trim());
      if (productId.trim()) filters.set('product_id', productId.trim());
      if (observedFrom) filters.set('observed_from', `${observedFrom}T00:00:00Z`);
      if (observedUntil) filters.set('observed_until', `${observedUntil}T23:59:59Z`);
      const [nextHistory, nextValidation] = await Promise.all([
        api.get<HistoryWorkspace>(`/api/enterprise/tiktok/history?${filters}`),
        isAdmin ? api.get<ValidationWorkspace>('/api/enterprise/tiktok/data-validation') : Promise.resolve(null),
      ]);
      setHistory(nextHistory);
      setValidation(nextValidation);
    } catch (error) {
      notify.error(error instanceof Error ? error.message : '加载历史对照失败');
    }
  }, [domain, creatorId, productId, observedFrom, observedUntil, page, isAdmin]);

  useEffect(() => { void load(); }, [load]);

  async function submitImport() {
    if (!file || !runId || !assigneeId) return;
    if (file.size > 2 * 1024 * 1024) {
      notify.error('文件超过 2 MiB');
      setFile(null);
      return;
    }
    setBusy(true);
    try {
      const parsed: unknown = JSON.parse(await file.text());
      const dataset = parsed && typeof parsed === 'object' && 'dataset' in parsed
        ? (parsed as { dataset: unknown }).dataset : parsed;
      await api.post('/api/enterprise/tiktok/history/import', {
        recorded_run_id: runId,
        source_kind: sourceKind,
        assigned_bd_user_id: assigneeId,
        dataset,
      });
      notify.success('脱敏历史记录已导入，请逐条核对');
      await load();
    } catch (error) {
      notify.error(error instanceof Error ? error.message : '导入失败');
    } finally {
      setFile(null);
      setBusy(false);
    }
  }

  async function submitReview() {
    if (!reviewFactId || reason.trim().length < 3) return;
    setBusy(true);
    try {
      await api.post(`/api/enterprise/tiktok/history/facts/${reviewFactId}/reconciliations`, {
        verdict, reason: reason.trim(),
      });
      setReviewFactId('');
      setReason('');
      notify.success('核对结论已追加');
      await load();
    } catch (error) {
      notify.error(error instanceof Error ? error.message : '核对失败');
    } finally {
      setBusy(false);
    }
  }

  async function confirm() {
    if (approvalRef.trim().length < 3) return;
    setBusy(true);
    try {
      await api.post('/api/enterprise/tiktok/history/confirm', { approval_ref: approvalRef.trim() });
      notify.success('业务 Owner 已确认对照快照');
      await load();
    } catch (error) {
      notify.error(error instanceof Error ? error.message : '确认失败');
    } finally {
      setBusy(false);
    }
  }

  const runs = validation?.recent_runs.filter((run) => run.mode === 'recorded' && run.status === 'passed') || [];
  const reviewable = history?.facts.filter((fact) => (
    currentUser.business_role === 'tiktok_bd_specialist' && fact.assigned_bd_user_id === currentUser.id
  )) || [];

  return <section className="mt-6 space-y-4" aria-label="P3-B1 历史事实与对照">
    <div className="rounded-2xl border border-[#e5e8ef] bg-white p-5">
      <h2 className="m-0 text-[16px] font-semibold">P3-B1 历史事实与逐条对照</h2>
      <p className="mt-1 text-[12px] text-[#66708a]">仅展示带来源的脱敏历史事实。Mock/合成记录不计入 30 条退出门槛。</p>
      <div className="mt-4 flex flex-wrap gap-4 text-[13px]">
        <span>已核对 {history?.eligible_reviewed_count ?? 0} / 30 条</span>
        <span>当前事实 {history?.total_count ?? 0} 条</span>
        <span>{history?.exit_ready ? '业务 Owner 已确认' : '尚未满足业务确认门槛'}</span>
      </div>
      <div className="mt-4 grid gap-2 sm:grid-cols-3">
        {history?.metrics.map((metric) => <div key={metric.code} className="rounded-xl bg-[#f7f8fa] p-3 text-[12px]">
          <span className="block text-[#66708a]">{metric.label} · v{metric.version}</span>
          <strong className="mt-1 block text-[16px]">{metric.value === null ? `不可计算：${metric.reason || 'unknown'}` : `${metric.value} ${metric.unit}`}</strong>
          <span className="mt-1 block text-[#66708a]">{metric.formula} · {metric.timezone} · {metric.window}</span>
        </div>)}
      </div>
    </div>

    {isAdmin && <div className="rounded-2xl border border-[#e5e8ef] bg-white p-5">
      <h3 className="m-0 text-[14px] font-semibold">导入已验证的历史批次</h3>
      <p className="mt-1 text-[12px] text-[#66708a]">仅接受与已通过的 recorded 运行摘要完全一致的脱敏 JSON；文件名不会提交。</p>
      <p className="mt-1 text-[12px] text-[#66708a]">来源类型由管理员申报，导入成功不等于真实来源或 E3 已核实；业务 Owner 仍须逐条确认。</p>
      <div className="mt-3 grid gap-2 sm:grid-cols-2">
        <select aria-label="已通过的 recorded 运行" className={inputClass} value={runId} onChange={(event) => setRunId(event.target.value)}>
          <option value="">选择 recorded 运行</option>
          {runs.map((run) => <option key={run.id} value={run.id}>{run.source_label || '录制回放'} · {run.id.slice(-8)}</option>)}
        </select>
        <select aria-label="分配 BD" className={inputClass} value={assigneeId} onChange={(event) => setAssigneeId(event.target.value)}>
          <option value="">选择核对人员</option>
          {history?.bd_options.map((owner) => <option key={owner.id} value={owner.id}>{owner.label}</option>)}
        </select>
        <select aria-label="历史来源类型" className={inputClass} value={sourceKind} onChange={(event) => setSourceKind(event.target.value as typeof sourceKind)}>
          <option value="synthetic">Mock / 合成测试</option>
          <option value="approved_redacted_history">经批准的脱敏历史</option>
        </select>
        <input aria-label="导入历史 JSON" className={inputClass} type="file" accept=".json,application/json" onChange={(event) => setFile(event.target.files?.[0] || null)} />
      </div>
      <Button className="mt-3" disabled={busy || !file || !runId || !assigneeId} onClick={() => void submitImport()}>导入并生成事实</Button>
    </div>}

    {history?.can_confirm && <div className="rounded-2xl border border-[#e5e8ef] bg-white p-5">
      <h3 className="m-0 text-[14px] font-semibold">业务 Owner 对照确认</h3>
      <div className="mt-3 flex flex-wrap gap-2">
        <input aria-label="业务 Owner 确认编号" className={inputClass} value={approvalRef} onChange={(event) => setApprovalRef(event.target.value)} placeholder="业务 Owner 确认编号" />
        <Button variant="outline" disabled={busy || (history?.eligible_reviewed_count ?? 0) < 30 || approvalRef.trim().length < 3} onClick={() => void confirm()}>确认 30 条核对快照</Button>
      </div>
    </div>}

    <div className="rounded-2xl border border-[#e5e8ef] bg-white p-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="m-0 text-[14px] font-semibold">规范化事实</h3>
        <select aria-label="事实领域" className={inputClass} value={domain} onChange={(event) => { setDomain(event.target.value); setPage(1); }}>
          {domains.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select>
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        <input aria-label="达人 ID" className={inputClass} value={creatorId} onChange={(event) => { setCreatorId(event.target.value); setPage(1); }} placeholder="达人 ID" />
        <input aria-label="商品 ID" className={inputClass} value={productId} onChange={(event) => { setProductId(event.target.value); setPage(1); }} placeholder="商品 ID" />
        <input aria-label="开始日期 UTC" className={inputClass} type="date" value={observedFrom} onChange={(event) => { setObservedFrom(event.target.value); setPage(1); }} />
        <input aria-label="结束日期 UTC" className={inputClass} type="date" value={observedUntil} onChange={(event) => { setObservedUntil(event.target.value); setPage(1); }} />
      </div>
      <div className="mt-3 grid gap-2">
        {history?.facts.map((fact) => <div key={fact.id} className="rounded-xl bg-[#f7f8fa] px-3 py-2 text-[12px]">
          <strong>{fact.business_key}</strong> · {fact.domain} · {fact.source_label} · {new Date(fact.observed_at).toLocaleString()}
          <span className="ml-2 text-[#66708a]">{fact.source_kind === 'synthetic' ? '合成测试' : '脱敏历史'} · {fact.latest_verdict || '待核对'}</span>
          <div className="mt-1 text-[#66708a]">{Object.entries(fact.values).map(([key, value]) => `${key}: ${String(value ?? '未知')}`).join(' · ')}</div>
        </div>)}
        {history?.facts.length === 0 && <p className="text-[12px] text-[#66708a]">当前没有历史事实。</p>}
      </div>
      <div className="mt-3 flex items-center gap-2 text-[12px]">
        <Button variant="outline" disabled={page <= 1} onClick={() => setPage(page - 1)}>上一页</Button>
        <span>第 {page} 页 · {history?.total_count ?? 0} 条</span>
        <Button variant="outline" disabled={page * 100 >= (history?.total_count ?? 0)} onClick={() => setPage(page + 1)}>下一页</Button>
      </div>
      {reviewable.length > 0 && <div className="mt-4 grid gap-2 sm:grid-cols-3">
        <select aria-label="核对事实" className={inputClass} value={reviewFactId} onChange={(event) => setReviewFactId(event.target.value)}>
          <option value="">选择事实</option>
          {reviewable.map((fact) => <option key={fact.id} value={fact.id}>{fact.domain} · {fact.business_key}</option>)}
        </select>
        <select aria-label="核对结论" className={inputClass} value={verdict} onChange={(event) => setVerdict(event.target.value as typeof verdict)}>
          <option value="matched">一致</option><option value="difference">有差异</option><option value="needs_review">待核对</option>
        </select>
        <input aria-label="脱敏差异原因" className={inputClass} value={reason} onChange={(event) => setReason(event.target.value)} placeholder="脱敏核对原因" />
        <Button disabled={busy || !reviewFactId || reason.trim().length < 3} onClick={() => void submitReview()}>追加核对结论</Button>
      </div>}
    </div>
  </section>;
}
