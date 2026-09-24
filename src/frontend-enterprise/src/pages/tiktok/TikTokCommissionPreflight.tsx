import { useRef, useState } from 'react';

import { api } from '@/api/client';
import { notify } from '@/components/ui/app-toast';
import { Button } from '@/components/ui/button';

type Result = { check_codes: string[]; can_submit_financial_review: boolean };
type SavedDraft = Result & {
  id: string; rule_version: string; order_refs: string[]; created_at: string;
  development_bps: number; fulfillment_bps: number; maintenance_bps: number;
};

const labels: Record<string, string> = {
  responsibilities_incomplete: '开发、履约或维护负责人未指定',
  rule_version_expired: '输入的规则版本已过期',
  commission_split_invalid: '三个角色的比例之和不是 100%',
  order_scope_overlap: '订单范围存在重复',
  rule_unapproved: '规则尚未批准，不能提交财务审核',
  saved_order_overlap: '已保存草案之间存在订单范围重叠',
  pool_revision_changed: '达人池状态已变化，请重新核对',
  responsibilities_changed: '责任人已变化，请重新核对',
};
const inputClass = 'min-h-9 rounded-lg border border-[#d9deea] bg-white px-3 text-[12px]';

function newKey(): string {
  const bytes = new Uint8Array(16);
  globalThis.crypto.getRandomValues(bytes);
  return Array.from(bytes, (byte) => byte.toString(16).padStart(2, '0')).join('');
}

export default function TikTokCommissionPreflight({ entryId, creatorName, entryRevision }: {
  entryId: string; creatorName: string; entryRevision: number;
}) {
  const [version, setVersion] = useState('');
  const [expiresAt, setExpiresAt] = useState('');
  const [orders, setOrders] = useState('');
  const [evidence, setEvidence] = useState('');
  const [development, setDevelopment] = useState('');
  const [fulfillment, setFulfillment] = useState('');
  const [maintenance, setMaintenance] = useState('');
  const [result, setResult] = useState<Result | null>(null);
  const [busy, setBusy] = useState(false);
  const [drafts, setDrafts] = useState<SavedDraft[] | null>(null);
  const [savedRevision, setSavedRevision] = useState<number | null>(null);
  const inputRevision = useRef(0);
  const saveKey = useRef<string | null>(null);
  function change(setter: (value: string) => void, value: string) {
    inputRevision.current += 1;
    setResult(null);
    setSavedRevision(null);
    saveKey.current = null;
    setter(value);
  }
  const orderRefs = orders.split(/[\s,，]+/).filter(Boolean);
  const ready = /^[A-Za-z0-9][A-Za-z0-9._-]*$/.test(version)
    && Boolean(expiresAt) && orderRefs.length > 0 && orderRefs.every((value) => /^order:[0-9a-f]{32}$/.test(value))
    && /^evidence:[0-9a-f]{32}$/.test(evidence)
    && [development, fulfillment, maintenance].every((value) => /^\d+$/.test(value));

  function payload() {
    return {
      rule_version: version,
      rule_expires_at: new Date(expiresAt).toISOString(),
      scopes: [{ order_refs: orderRefs, development_bps: Number(development),
        fulfillment_bps: Number(fulfillment), maintenance_bps: Number(maintenance),
        calculation_evidence_ref: evidence }],
    };
  }

  async function loadDrafts() {
    try {
      setDrafts(await api.get<SavedDraft[]>(`/api/enterprise/tiktok/commission-drafts/${entryId}`));
    } catch (error) {
      notify.error(error instanceof Error ? error.message : '读取已存草案失败');
    }
  }

  async function preflight() {
    const submittedRevision = ++inputRevision.current;
    setBusy(true);
    setResult(null);
    try {
      const current = await api.post<Result>(`/api/enterprise/tiktok/commission-drafts/${entryId}/preflight`, payload());
      if (submittedRevision === inputRevision.current) setResult(current);
    } catch (error) {
      notify.error(error instanceof Error ? error.message : '分佣预检失败');
    } finally {
      setBusy(false);
    }
  }

  async function save() {
    const submittedRevision = inputRevision.current;
    saveKey.current ??= newKey();
    setBusy(true);
    try {
      await api.post<SavedDraft>(`/api/enterprise/tiktok/commission-drafts/${entryId}`, {
        ...payload(), expected_pool_revision: entryRevision, idempotency_key: saveKey.current,
      });
      if (submittedRevision === inputRevision.current) setSavedRevision(submittedRevision);
      saveKey.current = null;
      await loadDrafts();
    } catch (error) {
      notify.error(error instanceof Error ? error.message : '保存内部草案失败');
    } finally {
      setBusy(false);
    }
  }

  return <div className="mt-3 rounded-lg border border-[#d9deea] bg-white p-3">
    <h4 className="m-0 text-[12px] font-semibold">分佣草案预检</h4>
    <p className="mt-1 text-[12px] text-[#66708a]">仅检查当前一个订单范围。可保存未批准的内部草案；订单引用未经事实核验，保存不会占用订单、提交财务审核或执行付款。比例以基点输入，10,000 代表 100%。订单和计算证据只填不含个人信息的不透明引用。</p>
    <div className="mt-2 grid gap-2 sm:grid-cols-2">
      <input className={inputClass} aria-label={`分佣规则版本 ${creatorName}`} placeholder="拟议规则版本" value={version} onChange={(event) => change(setVersion, event.target.value)} />
      <input className={inputClass} aria-label={`规则失效时间 ${creatorName}`} type="datetime-local" value={expiresAt} onChange={(event) => change(setExpiresAt, event.target.value)} />
      <input className={inputClass} aria-label={`订单引用 ${creatorName}`} placeholder="order: 加 32 位十六进制编号；多个用逗号分隔" value={orders} onChange={(event) => change(setOrders, event.target.value)} />
      <input className={inputClass} aria-label={`计算证据 ${creatorName}`} placeholder="evidence: 加 32 位十六进制编号" value={evidence} onChange={(event) => change(setEvidence, event.target.value)} />
      <input className={inputClass} aria-label={`开发比例 ${creatorName}`} type="number" placeholder="开发基点" value={development} onChange={(event) => change(setDevelopment, event.target.value)} />
      <input className={inputClass} aria-label={`履约比例 ${creatorName}`} type="number" placeholder="履约基点" value={fulfillment} onChange={(event) => change(setFulfillment, event.target.value)} />
      <input className={inputClass} aria-label={`维护比例 ${creatorName}`} type="number" placeholder="维护基点" value={maintenance} onChange={(event) => change(setMaintenance, event.target.value)} />
    </div>
    <Button className="mt-2" variant="outline" disabled={busy || !ready} onClick={() => void preflight()}>预检分佣草案</Button>
    <Button className="ml-2 mt-2" variant="outline" disabled={busy || !result
      || result.check_codes.some((code) => code !== 'rule_unapproved')
      || savedRevision === inputRevision.current} onClick={() => void save()}>保存未批准草案</Button>
    <Button className="ml-2 mt-2" variant="outline" disabled={busy} onClick={() => void loadDrafts()}>查看已存草案</Button>
    {result && <div className="mt-2 text-[12px]" role="status">
      {result.check_codes.map((code) => <p key={code}>{labels[code] ?? code}</p>)}
    </div>}
    {drafts && <div className="mt-3 space-y-2 text-[12px]" aria-label={`已存分佣草案 ${creatorName}`}>
      {drafts.length === 0 && <p>尚无已存草案。</p>}
      {drafts.map((draft) => <div key={draft.id} className="rounded-lg border border-[#d9deea] p-2">
        <div>未批准草案 · {draft.rule_version} · {draft.order_refs.length} 个订单引用 · {new Date(draft.created_at).toLocaleString()}</div>
        <div>拟议比例：开发 {draft.development_bps} / 履约 {draft.fulfillment_bps} / 维护 {draft.maintenance_bps} 基点</div>
        {draft.check_codes.map((code) => <p key={code}>{labels[code] ?? code}</p>)}
      </div>)}
    </div>}
  </div>;
}
