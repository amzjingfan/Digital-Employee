import { useCallback, useEffect, useState } from 'react';

import { api } from '@/api/client';
import type { EnterpriseAuthUser } from '@/auth';
import { notify } from '@/components/ui/app-toast';
import { Button } from '@/components/ui/button';
import TikTokCommissionPreflight from '@/pages/tiktok/TikTokCommissionPreflight';

type Entry = {
  id: string; creator_id: string; identity_id: string;
  creator_name: string; public_handle: string; market: string;
  source_ref: string; sla_rule_version: string; follow_up_window_hours: number;
  state: 'public' | 'claimed' | 'reflow_candidate';
  owner_user_id: string | null; follow_up_due_at: string | null; revision: number;
  fulfillment_user_id: string | null; maintenance_user_id: string | null;
};
type Workspace = {
  entries: Entry[]; can_manage: boolean; can_claim: boolean;
  assignable_bds: { id: string; username: string }[];
  assignable_users: { id: string; username: string }[];
};
type SocialCreator = {
  id: string; canonical_name: string; status: string;
  identities: { id: string; platform: string; public_handle: string; verified: boolean; status: string; latest_evidence: { id: string } | null }[];
};
type Candidate = { creatorId: string; identityId: string; sourceRef: string; label: string };

const inputClass = 'min-h-9 rounded-lg border border-[#d9deea] bg-white px-3 text-[12px]';

export default function TikTokCreatorPoolPanel({ currentUser }: { currentUser: EnterpriseAuthUser }) {
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [busy, setBusy] = useState(false);
  const [creatorId, setCreatorId] = useState('');
  const [identityId, setIdentityId] = useState('');
  const [sourceRef, setSourceRef] = useState('');
  const [ruleVersion, setRuleVersion] = useState('');
  const [windowHours, setWindowHours] = useState('');
  const [evidenceRefs, setEvidenceRefs] = useState<Record<string, string>>({});
  const [assignmentTargets, setAssignmentTargets] = useState<Record<string, string>>({});
  const [assignmentReasons, setAssignmentReasons] = useState<Record<string, 'staff_change' | 'assignment_correction'>>({});
  const [fulfillmentTargets, setFulfillmentTargets] = useState<Record<string, string>>({});
  const [maintenanceTargets, setMaintenanceTargets] = useState<Record<string, string>>({});

  const load = useCallback(async () => {
    try {
      const current = await api.get<Workspace>('/api/enterprise/tiktok/creator-pool');
      setWorkspace(current);
      if (current.can_manage) {
        const creators = await api.get<SocialCreator[]>('/api/v1/social/creators?platform=tiktok&include_stale=false&limit=100');
        const inPool = new Set(current.entries.map((entry) => entry.creator_id));
        setCandidates(creators.filter((creator) => creator.status === 'active' && !inPool.has(creator.id))
          .flatMap((creator) => creator.identities
            .filter((identity) => identity.platform === 'tiktok' && identity.status === 'active' && identity.verified && identity.latest_evidence)
            .map((identity) => ({
              creatorId: creator.id, identityId: identity.id, sourceRef: identity.latest_evidence!.id,
              label: `${creator.canonical_name} · @${identity.public_handle}`,
            }))));
      }
    } catch (error) {
      notify.error(error instanceof Error ? error.message : '加载达人池失败');
    }
  }, []);
  useEffect(() => { void load(); }, [load]);

  async function mutate(path: string, payload: Record<string, unknown>, success: string) {
    setBusy(true);
    let succeeded = false;
    try {
      await api.post(path, payload);
      notify.success(success);
      setFulfillmentTargets({});
      setMaintenanceTargets({});
      succeeded = true;
    } catch (error) {
      notify.error(error instanceof Error ? error.message : '达人池操作失败');
    } finally {
      await load();
      setBusy(false);
    }
    return succeeded;
  }

  async function intake() {
    const succeeded = await mutate('/api/enterprise/tiktok/creator-pool', {
      creator_id: creatorId.trim(), identity_id: identityId.trim(),
      source_ref: sourceRef.trim(), sla_rule_version: ruleVersion.trim(),
      follow_up_window_hours: Number(windowHours),
    }, '达人已加入内部公海池');
    if (succeeded) {
      setCreatorId(''); setIdentityId(''); setSourceRef('');
    }
  }

  async function followUp(entry: Entry) {
    const succeeded = await mutate(`/api/enterprise/tiktok/creator-follow-ups/${entry.id}`, {
      expected_revision: entry.revision, evidence_ref: evidenceRefs[entry.id].trim(),
    }, '有效跟进已记录');
    if (succeeded) setEvidenceRefs((current) => ({ ...current, [entry.id]: '' }));
  }

  return <section className="mt-6 space-y-4" aria-label="P3-B2 内部达人池">
    <div className="rounded-2xl border border-[#e5e8ef] bg-white p-5">
      <h2 className="m-0 text-[16px] font-semibold">P3-B2 内部达人认领</h2>
      <p className="mt-1 text-[12px] text-[#66708a]">仅记录内部归属和人工跟进证据；不会发送达人消息或执行分佣。</p>
      <p className="mt-1 text-[12px] text-[#66708a]">跟进证据使用 evidence: 加 32 位十六进制编号；不要填写联系人或消息正文。</p>
    </div>

    {workspace?.can_manage && <div className="rounded-2xl border border-[#e5e8ef] bg-white p-5">
      <h3 className="m-0 text-[14px] font-semibold">加入已核验达人</h3>
      <p className="mt-1 text-[12px] text-[#66708a]">从同租户目录选择已核验 TikTok 达人，并指定明确的 SLA 规则版本。</p>
      <select className={`${inputClass} mt-3 w-full`} aria-label="选择已核验达人" value={identityId} onChange={(event) => {
        const candidate = candidates.find((item) => item.identityId === event.target.value);
        setCreatorId(candidate?.creatorId ?? '');
        setIdentityId(candidate?.identityId ?? '');
        setSourceRef(candidate?.sourceRef ?? '');
      }}>
        <option value="">选择已核验达人</option>
        {candidates.map((candidate) => <option key={candidate.identityId} value={candidate.identityId}>{candidate.label}</option>)}
      </select>
      {sourceRef && <p className="mt-2 text-[12px] text-[#66708a]">来源证据：{sourceRef}</p>}
      <div className="mt-3 grid gap-2 sm:grid-cols-2">
        <input className={inputClass} aria-label="SLA 规则版本" value={ruleVersion} onChange={(event) => setRuleVersion(event.target.value)} />
        <input className={inputClass} aria-label="跟进窗口小时数" type="number" min="1" max="720" value={windowHours} onChange={(event) => setWindowHours(event.target.value)} />
      </div>
      <Button className="mt-3" disabled={busy || !creatorId.trim() || !identityId.trim() || sourceRef.trim().length < 3 || !ruleVersion.trim() || Number(windowHours) < 1 || Number(windowHours) > 720} onClick={() => void intake()}>加入公海池</Button>
    </div>}

    <div className="rounded-2xl border border-[#e5e8ef] bg-white p-5">
      <h3 className="m-0 text-[14px] font-semibold">达人归属</h3>
      <div className="mt-3 space-y-2">
        {workspace?.entries.map((entry) => <div key={entry.id} className="rounded-xl bg-[#f7f8fa] p-3 text-[12px]">
          <div><strong>{entry.creator_name}</strong> · @{entry.public_handle} · {entry.market} · {entry.state}</div>
          <div className="mt-1 text-[#66708a]">来源 {entry.source_ref} · {entry.sla_rule_version} · {entry.follow_up_window_hours} 小时 · 版本 {entry.revision}</div>
          {entry.owner_user_id && <div className="mt-1 text-[#66708a]">Owner {entry.owner_user_id}</div>}
          {entry.fulfillment_user_id && <div className="mt-1 text-[#66708a]">履约负责人 {entry.fulfillment_user_id}</div>}
          {entry.maintenance_user_id && <div className="mt-1 text-[#66708a]">维护负责人 {entry.maintenance_user_id}</div>}
          {entry.follow_up_due_at && <div className="mt-1 text-[#66708a]">下次有效跟进截止 {new Date(entry.follow_up_due_at).toLocaleString()}</div>}
          <div className="mt-2 flex flex-wrap gap-2">
            {workspace.can_claim && entry.state === 'public' && <Button variant="outline" disabled={busy} onClick={() => void mutate(`/api/enterprise/tiktok/creator-claims/${entry.id}`, { expected_revision: entry.revision }, '达人已认领')}>认领</Button>}
            {workspace.can_claim && entry.owner_user_id === currentUser.id && entry.state !== 'public' && <>
              <input className={inputClass} aria-label={`有效跟进证据 ${entry.creator_name}`} value={evidenceRefs[entry.id] ?? ''} onChange={(event) => setEvidenceRefs((current) => ({ ...current, [entry.id]: event.target.value }))} placeholder="有效跟进证据编号" />
              <Button variant="outline" disabled={busy || !/^evidence:[0-9a-f]{32}$/.test((evidenceRefs[entry.id] ?? '').trim())} onClick={() => void followUp(entry)}>记录有效跟进</Button>
            </>}
            {workspace.can_manage && entry.state === 'claimed' && <Button variant="outline" disabled={busy} onClick={() => void mutate(`/api/enterprise/tiktok/creator-reflow-proposals/${entry.id}`, { expected_revision: entry.revision }, '已标记回流候选')}>提出回流</Button>}
            {workspace.can_manage && entry.state === 'reflow_candidate' && <Button variant="outline" disabled={busy} onClick={() => void mutate(`/api/enterprise/tiktok/creator-reflow-approvals/${entry.id}`, { expected_revision: entry.revision }, '回流已确认')}>确认回流</Button>}
            {workspace.can_manage && entry.owner_user_id && entry.state !== 'public' && <>
              <select className={inputClass} aria-label={`转交给 ${entry.creator_name}`} value={assignmentTargets[entry.id] ?? ''} onChange={(event) => setAssignmentTargets((current) => ({ ...current, [entry.id]: event.target.value }))}>
                <option value="">选择接手 BD</option>
                {(workspace.assignable_bds ?? []).filter((candidate) => candidate.id !== entry.owner_user_id).map((candidate) => <option key={candidate.id} value={candidate.id}>{candidate.username}</option>)}
              </select>
              <select className={inputClass} aria-label={`转交原因 ${entry.creator_name}`} value={assignmentReasons[entry.id] ?? 'staff_change'} onChange={(event) => setAssignmentReasons((current) => ({ ...current, [entry.id]: event.target.value as 'staff_change' | 'assignment_correction' }))}>
                <option value="staff_change">人员变动</option>
                <option value="assignment_correction">归属纠正</option>
              </select>
              <Button variant="outline" disabled={busy || !assignmentTargets[entry.id]} onClick={() => void mutate(`/api/enterprise/tiktok/creator-assignments/${entry.id}`, {
                expected_revision: entry.revision, target_user_id: assignmentTargets[entry.id],
                reason: assignmentReasons[entry.id] ?? 'staff_change',
              }, '达人归属已转交')}>转交归属</Button>
              <Button variant="outline" disabled={busy} onClick={() => void mutate(`/api/enterprise/tiktok/creator-assignments/${entry.id}`, {
                expected_revision: entry.revision, target_user_id: null, reason: 'manual_release',
              }, '达人已释放到公海')}>释放到公海</Button>
            </>}
          </div>
          {workspace.can_manage && entry.state !== 'public' && <div className="mt-3 flex flex-wrap gap-2">
            <select className={inputClass} aria-label={`履约负责人 ${entry.creator_name}`} value={fulfillmentTargets[entry.id] ?? entry.fulfillment_user_id ?? ''} onChange={(event) => setFulfillmentTargets((current) => ({ ...current, [entry.id]: event.target.value }))}>
              <option value="">未指定履约负责人</option>
              {(workspace.assignable_users ?? []).map((candidate) => <option key={candidate.id} value={candidate.id}>{candidate.username}</option>)}
            </select>
            <select className={inputClass} aria-label={`维护负责人 ${entry.creator_name}`} value={maintenanceTargets[entry.id] ?? entry.maintenance_user_id ?? ''} onChange={(event) => setMaintenanceTargets((current) => ({ ...current, [entry.id]: event.target.value }))}>
              <option value="">未指定维护负责人</option>
              {(workspace.assignable_users ?? []).map((candidate) => <option key={candidate.id} value={candidate.id}>{candidate.username}</option>)}
            </select>
            <Button variant="outline" disabled={busy} onClick={() => void mutate(`/api/enterprise/tiktok/creator-responsibilities/${entry.id}`, {
              expected_revision: entry.revision,
              fulfillment_user_id: fulfillmentTargets[entry.id] !== undefined ? fulfillmentTargets[entry.id] || null : entry.fulfillment_user_id,
              maintenance_user_id: maintenanceTargets[entry.id] !== undefined ? maintenanceTargets[entry.id] || null : entry.maintenance_user_id,
            }, '履约与维护责任已更新')}>保存分责</Button>
          </div>}
          {workspace.can_manage && <TikTokCommissionPreflight key={entry.revision} entryId={entry.id} creatorName={entry.creator_name} entryRevision={entry.revision} canPropose={entry.state !== 'public'} />}
        </div>)}
        {workspace?.entries.length === 0 && <p className="text-[12px] text-[#66708a]">当前没有可见的达人池记录。</p>}
      </div>
    </div>
  </section>;
}
