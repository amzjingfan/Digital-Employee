import { useCallback, useEffect, useState } from 'react';

import { api, TENANT_ID } from '@/api/client';
import type { EnterpriseAuthUser } from '@/auth';
import { notify } from '@/components/ui/app-toast';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogFooter, DialogTitle, Input, Textarea } from '@/components/ui';
import { cn } from '@/lib/utils';

type StoreResource = {
  id: string;
  code: string;
  name: string;
  status: string;
};

type Evidence = {
  id: string;
  evidence_type: string;
  evidence_class: string;
  value: Record<string, unknown>;
  source_type: string;
  source_record_id: string;
  captured_at: string;
  expires_at: string;
  confidence: number;
  rule_version: string;
  raw_hash: string;
  freshness_status: 'fresh' | 'expired';
};

type ChannelAsset = {
  id: string;
  brand_key: string;
  store_resource_id: string;
  store_code: string;
  asset_type: string;
  canonical_name: string;
  stable_external_ref: string;
  region: string;
  language: string;
  categories: string[];
  tier: string;
  lifecycle_status: string;
  effective_lifecycle_status: string;
  required_evidence_types: string[];
  missing_required_evidence: string[];
  expired_required_evidence: string[];
  freshness_status: 'fresh' | 'stale' | 'missing';
  execution_guard: {
    status: 'blocked' | 'eligible_for_proposal';
    reasons: string[];
    evaluated_at: string;
  };
  version: number;
  updated_at: string;
  evidence: Evidence[];
};

type Props = {
  currentUser: EnterpriseAuthUser;
  stores: StoreResource[];
};

const ASSET_TYPES = [
  ['deal_site', 'Deal 站'],
  ['facebook_group', 'Facebook 群组'],
  ['creator', '达人'],
  ['media_outlet', '媒体'],
  ['author', '作者'],
  ['affiliate', '联盟'],
  ['community', '社区'],
] as const;

const EVIDENCE_TYPES = [
  'identity',
  'audience_fit',
  'activity',
  'administrator',
  'terms',
  'fees',
  'contact_basis',
  'authenticity',
  'compliance',
  'current_role',
  'historical_result',
] as const;

function idempotencyKey(prefix: string): string {
  const random = globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`;
  return `${prefix}:${random}`;
}

function formatTime(value?: string | null): string {
  if (!value) return '-';
  return new Intl.DateTimeFormat(undefined, {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(value));
}

function statusClass(status: string): string {
  if (['blocked', 'needs_review', 'rejected', 'expired', 'stale'].includes(status)) {
    return 'bg-[#fff0ef] text-[#b42318]';
  }
  if (['fresh', 'verified', 'piloting', 'active', 'eligible_for_proposal'].includes(status)) {
    return 'bg-[#edf9f4] text-[#23735f]';
  }
  return 'bg-[#eef3ff] text-[#315ea8]';
}

export default function OffsiteChannelAssetsPanel({ currentUser, stores }: Props) {
  const manager = currentUser.role === 'admin' || currentUser.business_role === 'operations_supervisor';
  const [assets, setAssets] = useState<ChannelAsset[]>([]);
  const [selected, setSelected] = useState<ChannelAsset | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [dialog, setDialog] = useState<'asset' | 'evidence' | 'review' | null>(null);
  const [form, setForm] = useState<Record<string, string>>({});

  const loadDetail = useCallback(async (assetId: string) => {
    const row = await api.get<ChannelAsset>(
      `/api/v1/offsite/channels/${encodeURIComponent(assetId)}?tenant_id=${encodeURIComponent(TENANT_ID)}`,
    );
    setSelected(row);
    setAssets((current) => current.map((item) => item.id === row.id ? { ...row, evidence: [] } : item));
  }, []);

  const loadAssets = useCallback(async () => {
    setLoading(true);
    try {
      const rows = await api.get<ChannelAsset[]>(
        `/api/v1/offsite/channels?tenant_id=${encodeURIComponent(TENANT_ID)}`,
      );
      setAssets(rows);
      if (selected) {
        const exists = rows.some((item) => item.id === selected.id);
        if (exists) await loadDetail(selected.id);
        else setSelected(null);
      } else if (rows[0]) {
        await loadDetail(rows[0].id);
      }
    } catch (error) {
      notify.error(error instanceof Error ? error.message : '站外渠道资产加载失败');
    } finally {
      setLoading(false);
    }
  }, [loadDetail, selected]);

  useEffect(() => {
    void loadAssets();
    // Selection changes are refreshed explicitly after mutations to avoid a request loop.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function openDialog(next: typeof dialog, defaults: Record<string, string>) {
    setForm(defaults);
    setDialog(next);
  }

  async function runAction(action: () => Promise<ChannelAsset>, success: string) {
    setBusy(true);
    try {
      const row = await action();
      setSelected(row);
      setDialog(null);
      notify.success(success);
      await loadAssets();
    } catch (error) {
      notify.error(error instanceof Error ? error.message : '操作失败');
    } finally {
      setBusy(false);
    }
  }

  async function createAsset() {
    await runAction(
      () => api.postWithHeaders<ChannelAsset>(
        '/api/v1/offsite/channels',
        {
          tenant_id: TENANT_ID,
          brand_key: form.brand_key,
          store_resource_id: form.store_resource_id,
          asset_type: form.asset_type,
          canonical_name: form.canonical_name,
          stable_external_ref: form.stable_external_ref,
          region: form.region,
          language: form.language,
          categories: form.categories.split(',').map((item) => item.trim()).filter(Boolean),
        },
        { 'Idempotency-Key': idempotencyKey('offsite-channel-create') },
      ),
      '渠道线索已保存；当前仍不可执行外部动作',
    );
  }

  async function addEvidence() {
    if (!selected) return;
    let value: Record<string, unknown>;
    try {
      value = JSON.parse(form.value_json) as Record<string, unknown>;
    } catch {
      notify.error('证据值必须是 JSON 对象');
      return;
    }
    const capturedAt = new Date();
    const expiresAt = new Date(capturedAt.getTime() + Number(form.valid_days || 30) * 86_400_000);
    await runAction(
      () => api.postWithHeaders<ChannelAsset>(
        `/api/v1/offsite/channels/${encodeURIComponent(selected.id)}/evidence`,
        {
          tenant_id: TENANT_ID,
          evidence_type: form.evidence_type,
          evidence_class: form.evidence_class,
          value,
          source_type: form.source_type,
          source_record_id: form.source_record_id,
          ingestion_batch_id: form.ingestion_batch_id || null,
          captured_at: capturedAt.toISOString(),
          expires_at: expiresAt.toISOString(),
          confidence: Number(form.confidence),
          rule_version: form.rule_version,
        },
        { 'Idempotency-Key': idempotencyKey('offsite-evidence-add') },
      ),
      '证据已追加；旧证据未被覆盖',
    );
  }

  async function reviewAsset() {
    if (!selected) return;
    const evidenceIds = selected.evidence
      .filter((item) => item.freshness_status === 'fresh')
      .map((item) => item.id);
    await runAction(
      () => api.post<ChannelAsset>(
        `/api/v1/offsite/channels/${encodeURIComponent(selected.id)}/review`,
        {
          tenant_id: TENANT_ID,
          expected_version: selected.version,
          lifecycle_status: form.lifecycle_status,
          tier: form.tier,
          evidence_ids: evidenceIds,
          reason: form.reason,
        },
      ),
      '人工复核已留痕；未创建任何外部 Operation',
    );
  }

  return <div className="mt-5 grid gap-5 xl:grid-cols-[360px_minmax(0,1fr)]">
    <aside className="rounded-[18px] border border-[#e6e8ee] bg-white p-3">
      <div className="flex items-start justify-between gap-3 px-2 pb-3">
        <div>
          <strong className="text-[14px]">站外渠道资产</strong>
          <p className="mt-1 text-[10px] text-[#858b9c]">功能 26 · P0 数据底座</p>
        </div>
        <Button
          size="sm"
          disabled={stores.length === 0}
          onClick={() => openDialog('asset', {
            brand_key: 'brand.demo',
            store_resource_id: stores[0]?.id || '',
            asset_type: 'deal_site',
            canonical_name: '',
            stable_external_ref: '',
            region: 'US',
            language: 'en-US',
            categories: '',
          })}
        >新增线索</Button>
      </div>
      {loading && <p className="py-10 text-center text-[12px] text-[#858b9c]">正在加载渠道资产…</p>}
      {!loading && assets.length === 0 && <p className="py-10 text-center text-[12px] text-[#858b9c]">暂无渠道资产</p>}
      <div className="space-y-2">
        {assets.map((item) => <button
          key={item.id}
          type="button"
          onClick={() => void loadDetail(item.id)}
          className={cn(
            'w-full rounded-[12px] border px-3 py-3 text-left',
            selected?.id === item.id
              ? 'border-[#92c8bc] bg-[#f1faf7]'
              : 'border-transparent hover:bg-[#f7f8fa]',
          )}
        >
          <div className="flex items-start justify-between gap-2">
            <strong className="text-[12px] text-[#303444]">{item.canonical_name}</strong>
            <span className={cn('rounded-full px-2 py-1 text-[10px]', statusClass(item.effective_lifecycle_status))}>
              {item.effective_lifecycle_status}
            </span>
          </div>
          <p className="mt-2 text-[11px] text-[#667085]">{item.asset_type} · {item.store_code}</p>
          <p className="mt-1 text-[10px] text-[#858b9c]">{item.freshness_status} · {formatTime(item.updated_at)}</p>
        </button>)}
      </div>
    </aside>

    <main>
      {selected ? <div className="space-y-5">
        <section className="rounded-[18px] border border-[#e6e8ee] bg-white p-5">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <h2 className="text-[18px] font-semibold">{selected.canonical_name}</h2>
                <span className={cn('rounded-full px-2.5 py-1 text-[11px]', statusClass(selected.effective_lifecycle_status))}>
                  {selected.effective_lifecycle_status}
                </span>
                <span className={cn('rounded-full px-2.5 py-1 text-[11px]', statusClass(selected.execution_guard.status))}>
                  {selected.execution_guard.status}
                </span>
              </div>
              <p className="mt-2 text-[12px] text-[#667085]">
                {selected.brand_key} · {selected.store_code} · {selected.region}/{selected.language} · {selected.tier}
              </p>
              <p className="mt-2 break-all text-[11px] text-[#858b9c]">{selected.stable_external_ref}</p>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button variant="outline" onClick={() => openDialog('evidence', {
                evidence_type: selected.missing_required_evidence[0] || 'identity',
                evidence_class: 'observed_fact',
                source_type: 'authorized_import',
                source_record_id: '',
                ingestion_batch_id: '',
                confidence: '0.90',
                valid_days: '30',
                rule_version: 'offsite-channel-evidence-v1',
                value_json: '{\n  "result": "reviewed",\n  "sample_count": 1\n}',
              })}>追加证据</Button>
              {manager && <Button onClick={() => openDialog('review', {
                lifecycle_status: selected.lifecycle_status === 'discovered' ? 'candidate' : selected.lifecycle_status,
                tier: selected.tier,
                reason: '',
              })}>人工复核</Button>}
            </div>
          </div>
          <div className="mt-4 rounded-[12px] border border-[#f2d49a] bg-[#fff9ec] p-3 text-[11px] text-[#7a5014]">
            本页面只管理内部资产、证据和复核结论；即使显示 eligible_for_proposal，也不代表允许付款、发布、触达或创建外部执行。
          </div>
          {selected.execution_guard.reasons.length > 0 && <div className="mt-3 rounded-[12px] bg-[#fff0ef] p-3 text-[11px] text-[#b42318]">
            阻断原因：{selected.execution_guard.reasons.join('；')}
          </div>}
        </section>

        <div className="grid gap-5 lg:grid-cols-2">
          <section className="rounded-[18px] border border-[#e6e8ee] bg-white p-5">
            <h3 className="text-[14px] font-semibold">证据缺口</h3>
            <p className="mt-2 text-[11px] text-[#667085]">必需：{selected.required_evidence_types.join('、')}</p>
            <p className="mt-2 text-[11px] text-[#b42318]">缺失：{selected.missing_required_evidence.join('、') || '无'}</p>
            <p className="mt-1 text-[11px] text-[#b42318]">过期：{selected.expired_required_evidence.join('、') || '无'}</p>
          </section>
          <section className="rounded-[18px] border border-[#e6e8ee] bg-white p-5">
            <h3 className="text-[14px] font-semibold">边界说明</h3>
            <p className="mt-2 text-[11px] leading-5 text-[#667085]">
              当前不连接第三方渠道，不抓取私人数据，也不把公开线索自动标记为已验证。所有状态变化都需要主管复核，证据到期会在执行资格计算中立即阻断。
            </p>
          </section>
        </div>

        <section className="rounded-[18px] border border-[#e6e8ee] bg-white p-5">
          <h3 className="text-[14px] font-semibold">追加式证据时间线</h3>
          {selected.evidence.length === 0 && <p className="py-8 text-center text-[12px] text-[#858b9c]">尚未登记证据</p>}
          <div className="mt-3 space-y-3">
            {selected.evidence.map((item) => <article key={item.id} className="rounded-[12px] bg-[#f7f8fa] p-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <strong className="text-[12px]">{item.evidence_type} · {item.evidence_class}</strong>
                <span className={cn('rounded-full px-2 py-1 text-[10px]', statusClass(item.freshness_status))}>{item.freshness_status}</span>
              </div>
              <p className="mt-2 break-all text-[11px] text-[#667085]">{item.source_type} · {item.source_record_id}</p>
              <p className="mt-1 text-[10px] text-[#858b9c]">
                采集 {formatTime(item.captured_at)} · 到期 {formatTime(item.expires_at)} · 置信度 {item.confidence.toFixed(2)} · {item.rule_version}
              </p>
              <p className="mt-1 break-all text-[10px] text-[#858b9c]">{item.raw_hash}</p>
            </article>)}
          </div>
        </section>
      </div> : <div className="rounded-[18px] border border-dashed p-12 text-center text-[13px] text-[#858b9c]">选择一条渠道资产</div>}
    </main>

    <Dialog open={dialog === 'asset'} onOpenChange={(open) => !open && setDialog(null)}>
      <DialogContent>
        <DialogTitle>新增站外渠道线索</DialogTitle>
        <label className="text-[11px]">授权店铺<select className="mt-1 h-10 w-full rounded-md border px-3" value={form.store_resource_id || ''} onChange={(event) => setForm({ ...form, store_resource_id: event.target.value })}>{stores.map((item) => <option key={item.id} value={item.id}>{item.name} · {item.code}</option>)}</select></label>
        <div className="grid grid-cols-2 gap-2"><Input value={form.brand_key || ''} onChange={(event) => setForm({ ...form, brand_key: event.target.value })} placeholder="品牌键"/><select className="h-10 rounded-md border px-3" value={form.asset_type || ''} onChange={(event) => setForm({ ...form, asset_type: event.target.value })}>{ASSET_TYPES.map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></div>
        <Input value={form.canonical_name || ''} onChange={(event) => setForm({ ...form, canonical_name: event.target.value })} placeholder="渠道规范名称"/>
        <Input value={form.stable_external_ref || ''} onChange={(event) => setForm({ ...form, stable_external_ref: event.target.value })} placeholder="稳定 URL 或外部 ID（不得含 token）"/>
        <div className="grid grid-cols-2 gap-2"><Input value={form.region || ''} onChange={(event) => setForm({ ...form, region: event.target.value })} placeholder="地区，如 US"/><Input value={form.language || ''} onChange={(event) => setForm({ ...form, language: event.target.value })} placeholder="语言，如 en-US"/></div>
        <Input value={form.categories || ''} onChange={(event) => setForm({ ...form, categories: event.target.value })} placeholder="品类，英文逗号分隔"/>
        <p className="text-[11px] text-[#858b9c]">新建后固定为 discovered，仅保存线索，不自动验证或执行。</p>
        <DialogFooter><Button variant="outline" onClick={() => setDialog(null)}>取消</Button><Button disabled={busy || !form.store_resource_id} onClick={() => void createAsset()}>保存线索</Button></DialogFooter>
      </DialogContent>
    </Dialog>

    <Dialog open={dialog === 'evidence'} onOpenChange={(open) => !open && setDialog(null)}>
      <DialogContent>
        <DialogTitle>追加渠道证据</DialogTitle>
        <div className="grid grid-cols-2 gap-2"><select className="h-10 rounded-md border px-3" value={form.evidence_type || ''} onChange={(event) => setForm({ ...form, evidence_type: event.target.value })}>{EVIDENCE_TYPES.map((item) => <option key={item} value={item}>{item}</option>)}</select><select className="h-10 rounded-md border px-3" value={form.evidence_class || ''} onChange={(event) => setForm({ ...form, evidence_class: event.target.value })}><option value="observed_fact">observed_fact</option><option value="source_claim">source_claim</option><option value="human_judgment">human_judgment</option></select></div>
        <select className="h-10 rounded-md border px-3" value={form.source_type || ''} onChange={(event) => setForm({ ...form, source_type: event.target.value })}><option value="authorized_import">authorized_import</option><option value="authorized_api">authorized_api</option><option value="public_web">public_web</option><option value="business_record">business_record</option><option value="human_observation">human_observation</option></select>
        <Input value={form.source_record_id || ''} onChange={(event) => setForm({ ...form, source_record_id: event.target.value })} placeholder="来源记录 ID 或公开 URL"/>
        <Input value={form.ingestion_batch_id || ''} onChange={(event) => setForm({ ...form, ingestion_batch_id: event.target.value })} placeholder="导入批次（可选）"/>
        <Textarea rows={5} value={form.value_json || ''} onChange={(event) => setForm({ ...form, value_json: event.target.value })} placeholder="证据 JSON；不得含邮箱、电话、地址或秘密"/>
        <div className="grid grid-cols-3 gap-2"><Input type="number" min="0" max="1" step="0.01" value={form.confidence || ''} onChange={(event) => setForm({ ...form, confidence: event.target.value })} placeholder="置信度"/><Input type="number" min="1" value={form.valid_days || ''} onChange={(event) => setForm({ ...form, valid_days: event.target.value })} placeholder="有效天数"/><Input value={form.rule_version || ''} onChange={(event) => setForm({ ...form, rule_version: event.target.value })} placeholder="规则版本"/></div>
        <DialogFooter><Button variant="outline" onClick={() => setDialog(null)}>取消</Button><Button disabled={busy || !form.source_record_id} onClick={() => void addEvidence()}>追加并留痕</Button></DialogFooter>
      </DialogContent>
    </Dialog>

    <Dialog open={dialog === 'review'} onOpenChange={(open) => !open && setDialog(null)}>
      <DialogContent>
        <DialogTitle>主管人工复核</DialogTitle>
        <div className="grid grid-cols-2 gap-2"><select className="h-10 rounded-md border px-3" value={form.lifecycle_status || ''} onChange={(event) => setForm({ ...form, lifecycle_status: event.target.value })}>{['candidate','verifying','verified','piloting','active','needs_review','paused','rejected','archived'].map((item) => <option key={item} value={item}>{item}</option>)}</select><select className="h-10 rounded-md border px-3" value={form.tier || ''} onChange={(event) => setForm({ ...form, tier: event.target.value })}>{['unassigned','tier_1','tier_2','tier_3'].map((item) => <option key={item} value={item}>{item}</option>)}</select></div>
        <Textarea rows={4} value={form.reason || ''} onChange={(event) => setForm({ ...form, reason: event.target.value })} placeholder="复核理由（必填，至少 8 个字符）"/>
        <p className="text-[11px] text-[#858b9c]">提交时引用当前全部 fresh 证据；缺少必需类型时后端拒绝 verified/piloting/active。复核不会创建外部动作。</p>
        <DialogFooter><Button variant="outline" onClick={() => setDialog(null)}>取消</Button><Button disabled={busy || (form.reason || '').trim().length < 8} onClick={() => void reviewAsset()}>保存复核</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  </div>;
}
