import { useRef, useState } from 'react';

import { api } from '@/api/client';
import { notify } from '@/components/ui/app-toast';
import { Button } from '@/components/ui/button';

type Result = { check_codes: string[]; can_submit_financial_review: boolean };

const labels: Record<string, string> = {
  responsibilities_incomplete: '开发、履约或维护负责人未指定',
  rule_version_expired: '输入的规则版本已过期',
  commission_split_invalid: '三个角色的比例之和不是 100%',
  order_scope_overlap: '订单范围存在重复',
  rule_unapproved: '规则尚未批准，不能提交财务审核',
};
const inputClass = 'min-h-9 rounded-lg border border-[#d9deea] bg-white px-3 text-[12px]';

export default function TikTokCommissionPreflight({ entryId, creatorName }: { entryId: string; creatorName: string }) {
  const [version, setVersion] = useState('');
  const [expiresAt, setExpiresAt] = useState('');
  const [orders, setOrders] = useState('');
  const [evidence, setEvidence] = useState('');
  const [development, setDevelopment] = useState('');
  const [fulfillment, setFulfillment] = useState('');
  const [maintenance, setMaintenance] = useState('');
  const [result, setResult] = useState<Result | null>(null);
  const [busy, setBusy] = useState(false);
  const inputRevision = useRef(0);
  function change(setter: (value: string) => void, value: string) {
    inputRevision.current += 1;
    setResult(null);
    setter(value);
  }
  const orderRefs = orders.split(/[\s,，]+/).filter(Boolean);
  const ready = /^[A-Za-z0-9][A-Za-z0-9._-]*$/.test(version)
    && Boolean(expiresAt) && orderRefs.length > 0 && orderRefs.every((value) => /^order:[0-9a-f]{32}$/.test(value))
    && /^evidence:[0-9a-f]{32}$/.test(evidence)
    && [development, fulfillment, maintenance].every((value) => /^\d+$/.test(value));

  async function preflight() {
    const submittedRevision = ++inputRevision.current;
    setBusy(true);
    setResult(null);
    try {
      const current = await api.post<Result>(`/api/enterprise/tiktok/commission-drafts/${entryId}/preflight`, {
        rule_version: version,
        rule_expires_at: new Date(expiresAt).toISOString(),
        scopes: [{ order_refs: orderRefs, development_bps: Number(development),
          fulfillment_bps: Number(fulfillment), maintenance_bps: Number(maintenance),
          calculation_evidence_ref: evidence }],
      });
      if (submittedRevision === inputRevision.current) setResult(current);
    } catch (error) {
      notify.error(error instanceof Error ? error.message : '分佣预检失败');
    } finally {
      setBusy(false);
    }
  }

  return <div className="mt-3 rounded-lg border border-[#d9deea] bg-white p-3">
    <h4 className="m-0 text-[12px] font-semibold">分佣草案预检</h4>
    <p className="mt-1 text-[12px] text-[#66708a]">仅检查当前一个订单范围，不保存草案或执行付款；跨草案冲突尚未校验。比例以基点输入，10,000 代表 100%。订单和计算证据只填不含个人信息的不透明引用。</p>
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
    {result && <div className="mt-2 text-[12px]" role="status">
      {result.check_codes.map((code) => <p key={code}>{labels[code] ?? code}</p>)}
    </div>}
  </div>;
}
