import { useCallback, useEffect, useMemo, useState } from 'react';

import { api } from '@/api/client';
import type { EnterpriseAuthUser } from '@/auth';
import { notify } from '@/components/ui/app-toast';
import { Button } from '@/components/ui/button';
import TikTokRecordedValidationForm from './TikTokRecordedValidationForm';
import type { CapabilityEvidence, FieldContract, Workspace } from './dataValidationTypes';

type ScopeDraft = {
  revision: number;
  store_resource_id: string;
  creator_scope_summary: string;
  business_owner_user_id: string;
  data_owner_user_id: string;
  status: 'draft' | 'active' | 'closed';
};

const emptyScope: ScopeDraft = {
  revision: 0,
  store_resource_id: '',
  creator_scope_summary: '',
  business_owner_user_id: '',
  data_owner_user_id: '',
  status: 'draft',
};

const controlClass = 'min-h-9 rounded-lg border border-[#d9deea] bg-white px-2 text-[12px] text-[#252936]';
const sectionClass = 'mt-4 rounded-[16px] border border-[#e5e8ef] bg-white p-5';

function formatDateTimeLocal(value: string | null): string {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  const localTime = new Date(date.getTime() - date.getTimezoneOffset() * 60_000);
  return localTime.toISOString().slice(0, 16);
}

export default function TikTokDataValidationPanel({ currentUser }: { currentUser: EnterpriseAuthUser }) {
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [loading, setLoading] = useState(true);
  const [busyKey, setBusyKey] = useState<string | null>(null);
  const [errorNotice, setErrorNotice] = useState('');
  const [scopeDraft, setScopeDraft] = useState<ScopeDraft>(emptyScope);
  const [fieldDrafts, setFieldDrafts] = useState<Record<string, FieldContract>>({});
  const [evidenceDrafts, setEvidenceDrafts] = useState<Record<string, CapabilityEvidence>>({});
  const isAdmin = currentUser.role === 'admin';

  const applyWorkspace = useCallback((next: Workspace) => {
    setWorkspace(next);
    setScopeDraft(next.scope ? {
      revision: next.scope.revision,
      store_resource_id: next.scope.store_resource_id || '',
      creator_scope_summary: next.scope.creator_scope_summary,
      business_owner_user_id: next.scope.business_owner_user_id || '',
      data_owner_user_id: next.scope.data_owner_user_id || '',
      status: next.scope.status,
    } : emptyScope);
    setFieldDrafts(Object.fromEntries(next.field_contracts.map((row) => [row.field_code, { ...row }])));
    setEvidenceDrafts(Object.fromEntries(next.capability_evidence.map((row) => [row.entry_code, { ...row }])));
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      applyWorkspace(await api.get<Workspace>('/api/enterprise/tiktok/data-validation'));
      setErrorNotice('');
    } catch (error) {
      const message = error instanceof Error ? error.message : '加载数据验证工作台失败';
      setErrorNotice(message);
      notify.error(message);
    } finally {
      setLoading(false);
    }
  }, [applyWorkspace]);

  useEffect(() => { void load(); }, [load]);

  const fieldGroups = useMemo(() => {
    const groups = new Map<string, FieldContract[]>();
    workspace?.field_contracts.forEach((row) => {
      groups.set(row.domain, [...(groups.get(row.domain) || []), row]);
    });
    return [...groups.entries()];
  }, [workspace]);

  async function mutate(key: string, action: () => Promise<unknown>, success: string) {
    setBusyKey(key);
    setErrorNotice('');
    try {
      await action();
      notify.success(success);
      await load();
    } catch (error) {
      const message = error instanceof Error ? error.message : '保存失败';
      setErrorNotice(message);
      notify.error(message);
    } finally {
      setBusyKey(null);
    }
  }

  async function bootstrap() {
    await mutate(
      'bootstrap',
      () => api.post('/api/enterprise/tiktok/data-validation/bootstrap'),
      '验证目录已初始化',
    );
  }

  async function saveScope() {
    await mutate(
      'scope',
      () => api.put('/api/enterprise/tiktok/data-validation/pilot-scope', scopeDraft),
      '试点范围已保存',
    );
  }

  async function saveField(code: string) {
    const row = fieldDrafts[code];
    await mutate(
      `field:${code}`,
      () => api.put(`/api/enterprise/tiktok/data-validation/field-contracts/${code}`, {
        revision: row.revision,
        owner_user_id: row.owner_user_id,
        business_key: row.business_key,
        freshness_sla_seconds: row.freshness_sla_seconds,
        missing_behavior: row.missing_behavior,
        sources: row.sources,
        status: row.status,
      }),
      '字段契约已保存',
    );
  }

  async function saveEvidence(code: string) {
    const row = evidenceDrafts[code];
    await mutate(
      `evidence:${code}`,
      () => api.put(`/api/enterprise/tiktok/data-validation/capability-evidence/${code}`, {
        revision: row.revision,
        subject_key: row.subject_key,
        resource_id: row.resource_id,
        required_scope: row.required_scope,
        endpoint_or_artifact: row.endpoint_or_artifact,
        api_version: row.api_version,
        evidence_level: row.evidence_level,
        evidence_type: row.evidence_type,
        status: row.status,
        decision: row.decision,
        summary: row.summary,
        evidence_ref: row.evidence_ref,
        checked_by_user_id: row.checked_by_user_id,
        checked_at: row.checked_at,
        valid_until: row.valid_until,
      }),
      row.entry_kind === 'provider_decision' ? '供应商决定已保存' : '能力证据已保存',
    );
  }

  async function runMock() {
    await mutate(
      'mock-run',
      () => api.post('/api/enterprise/tiktok/data-validation/runs/mock'),
      'Mock 校验已完成',
    );
  }

  if (loading && !workspace) {
    return <div className="mt-6 text-[13px] text-[#66708a]">正在加载数据验证工作台…</div>;
  }

  if (!workspace) {
    return <div role="alert" className="mt-6 rounded-xl bg-[#fff0f0] p-4 text-[#b42318]">{errorNotice || '数据验证工作台不可用'}</div>;
  }

  const capabilities = workspace.capability_evidence.filter((row) => row.entry_kind === 'capability');
  const providers = workspace.capability_evidence.filter((row) => row.entry_kind === 'provider_decision');

  return (
    <div className="mt-6" aria-label="TikTok 数据验证工作台">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="m-0 text-[20px] text-[#18181a]">数据验证工作台</h1>
          <p className="mt-1 text-[12px] text-[#66708a]">目录版本 {workspace.catalog_version} · Mock 结果不会代表真实数据可用</p>
        </div>
        {!isAdmin && <span className="rounded-full bg-[#eef2f7] px-3 py-1 text-[12px] text-[#4d596f]">只读模式</span>}
        {isAdmin && workspace.field_contracts.length === 0 && (
          <Button onClick={() => void bootstrap()} disabled={busyKey === 'bootstrap'}>初始化验证目录</Button>
        )}
      </div>

      {errorNotice && <div role="alert" className="mt-3 rounded-xl border border-[#f1b5b5] bg-[#fff0f0] px-4 py-3 text-[12px] text-[#b42318]">{errorNotice}</div>}

      <section className={sectionClass} aria-labelledby="validation-readiness-heading">
        <h2 id="validation-readiness-heading" className="m-0 text-[16px]">就绪状态</h2>
        <div className="mt-3 grid gap-3 md:grid-cols-2">
          <ReadinessCard label="工作台配置" ready={workspace.readiness.workbench_ready} readyText="工作台配置就绪" waitingText="工作台配置未就绪" />
          <ReadinessCard label="真实数据" ready={workspace.readiness.real_data_ready} readyText="真实数据就绪" waitingText="真实数据未就绪" />
        </div>
        <ul className="mt-3 grid gap-2 p-0">
          {workspace.readiness.blockers.map((blocker) => (
            <li key={`${blocker.code}:${blocker.target_code}`} className="list-none rounded-lg bg-[#fff8e8] px-3 py-2 text-[12px] text-[#7a5200]">
              <strong>{blocker.code}</strong> · {blocker.detail}
            </li>
          ))}
        </ul>
      </section>

      <section className={sectionClass} aria-labelledby="pilot-scope-heading">
        <h2 id="pilot-scope-heading" className="m-0 text-[16px]">试点范围</h2>
        <div className="mt-3 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          <LabeledSelect label="US 试点店铺" value={scopeDraft.store_resource_id} disabled={!isAdmin} onChange={(value) => setScopeDraft((old) => ({ ...old, store_resource_id: value }))} options={workspace.store_options} />
          <LabeledSelect label="业务 Owner" value={scopeDraft.business_owner_user_id} disabled={!isAdmin} onChange={(value) => setScopeDraft((old) => ({ ...old, business_owner_user_id: value }))} options={workspace.owner_options} />
          <LabeledSelect label="数据 Owner" value={scopeDraft.data_owner_user_id} disabled={!isAdmin} onChange={(value) => setScopeDraft((old) => ({ ...old, data_owner_user_id: value }))} options={workspace.owner_options} />
          <label className="grid gap-1 text-[12px] text-[#4d596f] md:col-span-2">
            达人范围
            <textarea className={`${controlClass} min-h-20 py-2`} value={scopeDraft.creator_scope_summary} disabled={!isAdmin} onChange={(event) => setScopeDraft((old) => ({ ...old, creator_scope_summary: event.target.value }))} />
          </label>
          <label className="grid gap-1 text-[12px] text-[#4d596f]">
            范围状态
            <select className={controlClass} value={scopeDraft.status} disabled={!isAdmin} onChange={(event) => setScopeDraft((old) => ({ ...old, status: event.target.value as ScopeDraft['status'] }))}>
              <option value="draft">草稿</option><option value="active">启用</option><option value="closed">关闭</option>
            </select>
          </label>
        </div>
        {isAdmin && <Button className="mt-3" onClick={() => void saveScope()} disabled={busyKey === 'scope'}>保存试点范围</Button>}
      </section>

      <section className={sectionClass} aria-labelledby="field-contracts-heading">
        <h2 id="field-contracts-heading" className="m-0 text-[16px]">字段契约</h2>
        {fieldGroups.map(([domain, rows]) => (
          <div key={domain} className="mt-4">
            <h3 className="m-0 text-[13px] uppercase text-[#66708a]">{domain}</h3>
            <div className="mt-2 grid gap-2">
              {rows.map((sourceRow) => {
                const row = fieldDrafts[sourceRow.field_code] || sourceRow;
                return (
                  <div key={row.field_code} className="rounded-xl border border-[#edf0f5] p-3">
                    <div className="flex flex-wrap items-center justify-between gap-2"><strong className="text-[13px]">{row.label}</strong><span className="text-[11px] text-[#66708a]">{row.field_code} · {row.status}</span></div>
                    <div className="mt-2 grid gap-2 md:grid-cols-3 xl:grid-cols-6">
                      <label className="grid gap-1 text-[11px]">Owner<select aria-label={`${row.label} Owner`} className={controlClass} value={row.owner_user_id || ''} disabled={!isAdmin} onChange={(event) => setFieldDrafts((old) => ({ ...old, [row.field_code]: { ...row, owner_user_id: event.target.value } }))}><option value="">未选择</option>{workspace.owner_options.map((option) => <option key={option.id} value={option.id}>{option.label}</option>)}</select></label>
                      <label className="grid gap-1 text-[11px]">业务键<input aria-label={`${row.label} 业务键`} className={controlClass} value={row.business_key} disabled={!isAdmin} onChange={(event) => setFieldDrafts((old) => ({ ...old, [row.field_code]: { ...row, business_key: event.target.value } }))} /></label>
                      <label className="grid gap-1 text-[11px]">新鲜度（秒）<input aria-label={`${row.label} 新鲜度`} type="number" className={controlClass} value={row.freshness_sla_seconds || ''} disabled={!isAdmin} onChange={(event) => setFieldDrafts((old) => ({ ...old, [row.field_code]: { ...row, freshness_sla_seconds: Number(event.target.value) } }))} /></label>
                      <label className="grid gap-1 text-[11px]">缺失处理<select aria-label={`${row.label} 缺失处理`} className={controlClass} value={row.missing_behavior} disabled={!isAdmin} onChange={(event) => setFieldDrafts((old) => ({ ...old, [row.field_code]: { ...row, missing_behavior: event.target.value as FieldContract['missing_behavior'] } }))}>{['unknown', 'manual_review', 'block_stage', 'not_applicable'].map((behavior) => <option key={behavior}>{behavior}</option>)}</select></label>
                      <label className="grid gap-1 text-[11px]">契约状态<select aria-label={`${row.label} 契约状态`} className={controlClass} value={row.status} disabled={!isAdmin} onChange={(event) => setFieldDrafts((old) => ({ ...old, [row.field_code]: { ...row, status: event.target.value as FieldContract['status'] } }))}>{['draft', 'confirmed', 'blocked', 'not_applicable'].map((status) => <option key={status}>{status}</option>)}</select></label>
                      <div className="text-[11px] text-[#66708a]">来源摘要：{row.sources.map((source) => `${source.source_key} (${source.usage}/${source.decision})`).join('、')}</div>
                    </div>
                    {isAdmin && <Button className="mt-2" variant="outline" onClick={() => void saveField(row.field_code)} disabled={busyKey === `field:${row.field_code}`}>保存字段契约</Button>}
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </section>

      <section className={sectionClass} aria-labelledby="capability-heading">
        <div className="flex flex-wrap items-center justify-between gap-2"><h2 id="capability-heading" className="m-0 text-[16px]">能力证据与供应商决定</h2><span className="text-[12px] text-[#66708a]">证据等级：E0–E3</span></div>
        <EvidenceGroup title="动作能力" rows={capabilities} drafts={evidenceDrafts} setDrafts={setEvidenceDrafts} owners={workspace.owner_options} isAdmin={isAdmin} busyKey={busyKey} onSave={saveEvidence} />
        <EvidenceGroup title="供应商决定" rows={providers} drafts={evidenceDrafts} setDrafts={setEvidenceDrafts} owners={workspace.owner_options} isAdmin={isAdmin} busyKey={busyKey} onSave={saveEvidence} />
      </section>

      <section className={sectionClass} aria-labelledby="validation-runs-heading">
        <div className="flex flex-wrap items-center justify-between gap-3"><div><h2 id="validation-runs-heading" className="m-0 text-[16px]">验证运行</h2><p className="mt-1 text-[12px] text-[#66708a]">只保存摘要、检查代码和问题元数据，不展示原始记录。</p></div>{isAdmin && <Button onClick={() => void runMock()} disabled={busyKey === 'mock-run'}>运行 Mock 校验</Button>}</div>
        {isAdmin && (
          <TikTokRecordedValidationForm
            currentUserId={currentUser.id}
            scope={workspace.scope}
            ownerOptions={workspace.owner_options}
            onCompleted={load}
          />
        )}
        <div className="mt-3 grid gap-2">
          {workspace.recent_runs.map((run) => <div key={run.id} className="rounded-xl bg-[#f7f8fa] px-3 py-3 text-[12px]"><span className="mr-2 rounded bg-[#eef2ff] px-2 py-0.5 text-[#315efb]">{run.mode === 'recorded' ? '录制回放' : 'Mock'}</span><strong>{run.status === 'passed' ? '通过' : '失败'}</strong> · {run.record_count} 条 · {run.catalog_version}{run.mode === 'recorded' && <div className="mt-1 text-[#66708a]">审批引用：{run.approval_ref || '—'} · 审批有效期：{run.approval_valid_until || '—'}</div>}<div className="mt-1 text-[#66708a]">{run.checks.map((check) => `${check.code}: ${check.passed ? '通过' : '失败'} (${check.checked_count})`).join(' · ')}</div>{run.issues.length > 0 && <div className="mt-1 text-[#b42318]">{run.issues.map((issue) => `${issue.code}/${issue.field_code}`).join(' · ')}</div>}</div>)}
          {workspace.recent_runs.length === 0 && <span className="text-[12px] text-[#858b9c]">尚无运行记录</span>}
        </div>
      </section>
    </div>
  );
}

function ReadinessCard({ label, ready, readyText, waitingText }: { label: string; ready: boolean; readyText: string; waitingText: string }) {
  return <div className={`rounded-xl border p-4 ${ready ? 'border-[#a8dfbd] bg-[#f0faf4]' : 'border-[#f0d59c] bg-[#fff9eb]'}`}><span className="block text-[11px] text-[#66708a]">{label}</span><strong className={ready ? 'text-[#18733d]' : 'text-[#98620a]'}>{ready ? readyText : waitingText}</strong></div>;
}

function LabeledSelect({ label, value, disabled, options, onChange }: { label: string; value: string; disabled: boolean; options: { id: string; label: string }[]; onChange: (value: string) => void }) {
  return <label className="grid gap-1 text-[12px] text-[#4d596f]">{label}<select className={controlClass} value={value} disabled={disabled} onChange={(event) => onChange(event.target.value)}><option value="">未选择</option>{options.map((option) => <option key={option.id} value={option.id}>{option.label}</option>)}</select></label>;
}

function EvidenceGroup({ title, rows, drafts, setDrafts, owners, isAdmin, busyKey, onSave }: { title: string; rows: CapabilityEvidence[]; drafts: Record<string, CapabilityEvidence>; setDrafts: React.Dispatch<React.SetStateAction<Record<string, CapabilityEvidence>>>; owners: { id: string; label: string }[]; isAdmin: boolean; busyKey: string | null; onSave: (code: string) => Promise<void> }) {
  return <div className="mt-4"><h3 className="m-0 text-[13px] text-[#4d596f]">{title}</h3><div className="mt-2 grid gap-2">{rows.map((sourceRow) => {
    const row = drafts[sourceRow.entry_code] || sourceRow;
    const expired = Boolean(row.valid_until && Date.parse(row.valid_until) < Date.now());
    return <div key={row.entry_code} className="rounded-xl border border-[#edf0f5] p-3"><div className="flex flex-wrap items-center gap-2"><strong className="text-[13px]">{row.platform_domain} · {row.action}</strong><span className="rounded bg-[#eef2ff] px-2 py-0.5 text-[11px] text-[#315efb]">{row.evidence_level}</span>{row.status === 'blocked' && <span className="text-[11px] text-[#b42318]">已阻塞</span>}{expired && <span className="text-[11px] text-[#98620a]">已过期</span>}</div><div className="mt-2 grid gap-2 md:grid-cols-3 xl:grid-cols-4"><label className="grid gap-1 text-[11px]">证据等级<select aria-label={`${row.entry_code} 证据等级`} className={controlClass} value={row.evidence_level} disabled={!isAdmin} onChange={(event) => setDrafts((old) => ({ ...old, [row.entry_code]: { ...row, evidence_level: event.target.value as CapabilityEvidence['evidence_level'] } }))}>{['E0', 'E1', 'E2', 'E3'].map((level) => <option key={level}>{level}</option>)}</select></label><label className="grid gap-1 text-[11px]">证据类型<select aria-label={`${row.entry_code} 证据类型`} className={controlClass} value={row.evidence_type} disabled={!isAdmin} onChange={(event) => setDrafts((old) => ({ ...old, [row.entry_code]: { ...row, evidence_type: event.target.value as CapabilityEvidence['evidence_type'] } }))}>{['unverified', 'official_docs', 'contract', 'mock', 'sandbox', 'approved_export', 'real_account'].map((type) => <option key={type}>{type}</option>)}</select></label><label className="grid gap-1 text-[11px]">状态<select aria-label={`${row.entry_code} 状态`} className={controlClass} value={row.status} disabled={!isAdmin} onChange={(event) => setDrafts((old) => ({ ...old, [row.entry_code]: { ...row, status: event.target.value as CapabilityEvidence['status'] } }))}>{['unverified', 'verified', 'blocked', 'not_applicable'].map((status) => <option key={status}>{status}</option>)}</select></label>{row.entry_kind === 'provider_decision' && <label className="grid gap-1 text-[11px]">决定<select aria-label={`${row.entry_code} 决定`} className={controlClass} value={row.decision || ''} disabled={!isAdmin} onChange={(event) => setDrafts((old) => ({ ...old, [row.entry_code]: { ...row, decision: event.target.value as CapabilityEvidence['decision'] } }))}><option value="">未决定</option>{['use', 'defer', 'reject'].map((decision) => <option key={decision}>{decision}</option>)}</select></label>}<label className="grid gap-1 text-[11px] md:col-span-2">摘要<input aria-label={`${row.entry_code} 摘要`} className={controlClass} value={row.summary} disabled={!isAdmin} onChange={(event) => setDrafts((old) => ({ ...old, [row.entry_code]: { ...row, summary: event.target.value } }))} /></label><label className="grid gap-1 text-[11px]">检查人<select aria-label={`${row.entry_code} 检查人`} className={controlClass} value={row.checked_by_user_id || ''} disabled={!isAdmin} onChange={(event) => setDrafts((old) => ({ ...old, [row.entry_code]: { ...row, checked_by_user_id: event.target.value } }))}><option value="">未选择</option>{owners.map((owner) => <option key={owner.id} value={owner.id}>{owner.label}</option>)}</select></label><label className="grid gap-1 text-[11px]">检查时间<input aria-label={`${row.entry_code} 检查时间`} type="datetime-local" className={controlClass} value={formatDateTimeLocal(row.checked_at)} disabled={!isAdmin} onChange={(event) => setDrafts((old) => ({ ...old, [row.entry_code]: { ...row, checked_at: event.target.value ? new Date(event.target.value).toISOString() : null } }))} /></label></div>{isAdmin && <Button className="mt-2" variant="outline" onClick={() => void onSave(row.entry_code)} disabled={busyKey === `evidence:${row.entry_code}`}>{row.entry_kind === 'provider_decision' ? `保存供应商决定 ${row.entry_code}` : `保存能力证据 ${row.entry_code}`}</Button>}</div>;
  })}</div></div>;
}
