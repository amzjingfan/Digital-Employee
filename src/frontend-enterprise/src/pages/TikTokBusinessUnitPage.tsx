import { useCallback, useEffect, useState } from 'react';

import { api } from '@/api/client';
import type { EnterpriseAuthUser } from '@/auth';
import AppHeader from '@/components/AppHeader';
import { notify } from '@/components/ui/app-toast';
import { Button } from '@/components/ui/button';
import TikTokDataValidationPanel from '@/pages/tiktok/TikTokDataValidationPanel';

type Role = { key: string; label: string; casdoor_group: string; description: string };
type Unit = { id: string; parent_id?: string | null; unit_type: string; code: string; name: string; status: string; revision: number; role_key?: string | null };
type Resource = { id: string; resource_type: string; code: string; name: string; status: string; market?: string | null; access_level: string };
type Authorization = { id: string; authorization_type: string; subject_id: string; resource_id?: string | null; scopes: string[]; status: string; expires_at?: string | null };
type Overview = { root?: Unit | null; departments: Unit[]; roles: Role[]; resources: Resource[]; authorizations: Authorization[]; task_counts: Record<string, number> };
type AssetBootstrap = { created_count: number; skill_ids: string[]; agent_ids: string[]; knowledge_base_ids: string[]; tool_ids: string[] };
type ShadowQuality = { reviewed_count: number; adopted_count: number; needs_revision_count: number; rejected_count: number; guardrail_issue_count: number; adoption_rate: number; covered_sop_ids: string[]; missing_sop_ids: string[]; minimum_reviewed_count: number; passed: boolean };
type ShadowRun = { id: string; status: string; started_at: string; ends_at: string; last_heartbeat_at: string; observation_count: number; error_count: number; baseline: Record<string, unknown>; quality: ShadowQuality };
type ProductionGate = { key: string; label: string; status: 'passed' | 'waiting' | 'blocked'; detail: string };
type ProductionReadiness = { ready: boolean; evaluated_at: string; gates: ProductionGate[] };
type ReleasePreflightItem = { slug: string; name: string; business_role: string; agent_id?: string | null; release_state?: string | null; ready: boolean; error?: string | null; snapshot_digest?: string | null };
type ReleasePreflight = { tenant_id: string; ready: boolean; evaluated_at: string; items: ReleasePreflightItem[] };
type MockReplayItem = { sop_id: string; title: string; status: string; agent_slug: string; execution_mode: string; task_id: string; trace_id: string; evidence_count: number; follow_up: { created: boolean; owner_business_role: string; title: string }; checks: { key: string; passed: boolean; detail: string }[] };
type MockReplayReport = { execution_mode: string; status: string; total_count: number; passed_count: number; failed_count: number; external_writes: boolean; persisted?: boolean; persisted_task_count?: number; items: MockReplayItem[] };
type SandboxReplayItem = { sop_id: string; task_id: string; status: string; run_id?: string | null; run_status?: string | null; execution_snapshot_id?: string | null; snapshot_digest?: string | null; trace: Record<string, unknown>; error_code?: string | null; error_message?: string | null };
type SandboxReplayReport = { execution_mode: 'sandbox'; processed_count: number; items: SandboxReplayItem[] };
type ExceptionMatrixItem = { sop_id: string; title: string; scenario: string; expected_error_code: string; expected_disposition: string; status: string; external_writes: boolean };
type ExceptionMatrixReport = { execution_mode: string; status: string; sop_count: number; scenario_count: number; total_count: number; passed_count: number; failed_count: number; external_writes: boolean; items: ExceptionMatrixItem[] };
type M2MVerificationItem = { agent_id?: string | null; application?: string | null; status: 'verified' | 'failed'; subject?: string | null; expires_at?: string | null; error_code?: string | null };
type M2MVerificationReport = { tenant_id: string; verified_count: number; failed_count: number; items: M2MVerificationItem[] };
type TikTokTab = 'overview' | 'employees' | 'assets' | 'tasks' | 'skills' | 'risk' | 'data-validation';

type Props = { currentUser: EnterpriseAuthUser; onLogout: () => void };

const DEPARTMENT_ROLE_LABELS: Record<string, string> = {
  tiktok_bd_specialist: 'BD',
  tiktok_content_specialist: '短视频',
  tiktok_shop_operator: '小店运营',
  tiktok_media_buyer: '投流',
  tiktok_tap_manager: 'TAP 机构',
  tiktok_live_operator: '直播',
};

export default function TikTokBusinessUnitPage({ currentUser, onLogout }: Props) {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [assetResult, setAssetResult] = useState<AssetBootstrap | null>(null);
  const [activeTab, setActiveTab] = useState<TikTokTab>('overview');
  const [shadowRun, setShadowRun] = useState<ShadowRun | null>(null);
  const [readiness, setReadiness] = useState<ProductionReadiness | null>(null);
  const [releasePreflight, setReleasePreflight] = useState<ReleasePreflight | null>(null);
  const [approvalReference, setApprovalReference] = useState('');
  const [mockReplay, setMockReplay] = useState<MockReplayReport | null>(null);
  const [sandboxReplay, setSandboxReplay] = useState<SandboxReplayReport | null>(null);
  const [exceptionMatrix, setExceptionMatrix] = useState<ExceptionMatrixReport | null>(null);
  const [m2mVerification, setM2mVerification] = useState<M2MVerificationReport | null>(null);
  const [shadowTaskId, setShadowTaskId] = useState('');
  const [shadowVerdict, setShadowVerdict] = useState<'adopted' | 'needs_revision' | 'rejected'>('adopted');
  const [shadowIssueCategory, setShadowIssueCategory] = useState('none');
  const [shadowSummary, setShadowSummary] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [nextOverview, nextShadowRun, nextReadiness, nextReleasePreflight] = await Promise.all([
        api.get<Overview>('/api/enterprise/tiktok/overview'),
        api.get<ShadowRun | null>('/api/enterprise/tiktok/shadow/status'),
        currentUser.role === 'admin'
          ? api.get<ProductionReadiness>('/api/enterprise/tiktok/production-readiness')
          : Promise.resolve(null),
        currentUser.role === 'admin'
          ? api.get<ReleasePreflight>('/api/enterprise/tiktok/release-preflight')
          : Promise.resolve(null),
      ]);
      setOverview(nextOverview);
      setShadowRun(nextShadowRun);
      setReadiness(nextReadiness);
      setReleasePreflight(nextReleasePreflight);
    } catch (error) {
      notify.error(error instanceof Error ? error.message : '加载 TikTok 事业部失败');
    } finally {
      setLoading(false);
    }
  }, [currentUser.role]);

  useEffect(() => { void load(); }, [load]);

  async function bootstrap() {
    setBusy(true);
    try {
      const result = await api.post<{ assets?: AssetBootstrap }>('/api/enterprise/tiktok/bootstrap');
      if (result.assets) setAssetResult(result.assets);
      notify.success('TikTok 事业部组织模板已初始化');
      await load();
    } catch (error) {
      notify.error(error instanceof Error ? error.message : '初始化失败');
    } finally {
      setBusy(false);
    }
  }

  async function bootstrapAssets() {
    setBusy(true);
    try {
      const result = await api.post<AssetBootstrap>('/api/enterprise/tiktok/bootstrap-assets');
      setAssetResult(result);
      notify.success(result.created_count ? 'TikTok 生产资产已初始化' : 'TikTok 生产资产已是最新');
    } catch (error) {
      notify.error(error instanceof Error ? error.message : '生产资产初始化失败');
    } finally {
      setBusy(false);
    }
  }

  async function authorizeOfficialShop() {
    setBusy(true);
    try {
      const result = await api.post<{ authorize_url: string }>('/api/enterprise/tiktok/authorizations/official/start', {
        authorization_type: 'seller',
        market: 'US',
        scopes: ['seller.shop.info'],
        return_to: '/enterprise/tiktok',
      });
      window.location.assign(result.authorize_url);
    } catch (error) {
      notify.error(error instanceof Error ? error.message : 'TikTok 官方授权启动失败');
      setBusy(false);
    }
  }

  async function startShadow() {
    setBusy(true);
    try {
      setShadowRun(await api.post<ShadowRun>('/api/enterprise/tiktok/shadow/start'));
      notify.success('已启动 14 天只读影子运行');
    } catch (error) {
      notify.error(error instanceof Error ? error.message : '影子运行启动失败');
    } finally {
      setBusy(false);
    }
  }

  async function recordShadowEvaluation() {
    setBusy(true);
    try {
      await api.post('/api/enterprise/tiktok/shadow/evaluations', {
        task_id: shadowTaskId.trim(),
        verdict: shadowVerdict,
        issue_category: shadowIssueCategory,
        summary: shadowSummary.trim(),
      });
      setShadowTaskId('');
      setShadowSummary('');
      notify.success('人工对照证据已追加到任务 Trace');
      await load();
    } catch (error) {
      notify.error(error instanceof Error ? error.message : '人工对照记录失败');
    } finally {
      setBusy(false);
    }
  }

  async function publishTikTokReleases() {
    setBusy(true);
    try {
      await api.post('/api/enterprise/tiktok/releases/publish', { approval_reference: approvalReference.trim() });
      notify.success('五个 TikTok AgentRelease 已按审批编号发布');
      await load();
    } catch (error) {
      notify.error(error instanceof Error ? error.message : 'AgentRelease 发布失败');
    } finally {
      setBusy(false);
    }
  }

  async function runMockReplays(persist = false) {
    setBusy(true);
    try {
      setMockReplay(await api.post<MockReplayReport>('/api/enterprise/tiktok/mock-sop-replays/run', { persist }));
      notify.success(persist ? '五条 Mock 回放已幂等写入统一任务中心' : '五条 Mock SOP 回放验收已完成');
    } catch (error) {
      notify.error(error instanceof Error ? error.message : 'Mock SOP 回放失败');
    } finally {
      setBusy(false);
    }
  }

  async function executeMockReplays() {
    setBusy(true);
    try {
      setSandboxReplay(await api.post<SandboxReplayReport>('/api/enterprise/tiktok/mock-sop-replays/execute-sandbox'));
      notify.success('Sandbox Worker 已处理 Mock 回放任务');
    } catch (error) {
      notify.error(error instanceof Error ? error.message : 'Sandbox Worker 执行失败');
    } finally {
      setBusy(false);
    }
  }

  async function runExceptionMatrix() {
    setBusy(true);
    try {
      setExceptionMatrix(await api.get<ExceptionMatrixReport>('/api/enterprise/tiktok/mock-sop-replays/exception-matrix'));
      notify.success('五条 SOP 异常矩阵验收已完成');
    } catch (error) {
      notify.error(error instanceof Error ? error.message : 'SOP 异常矩阵验收失败');
    } finally {
      setBusy(false);
    }
  }

  async function verifyM2M() {
    setBusy(true);
    try {
      const result = await api.post<M2MVerificationReport>('/api/enterprise/tiktok/m2m/verify');
      setM2mVerification(result);
      notify.success(`M2M 验证完成：${result.verified_count}/${result.verified_count + result.failed_count} 通过`);
      await load();
    } catch (error) {
      notify.error(error instanceof Error ? error.message : 'M2M 服务身份验证失败');
    } finally {
      setBusy(false);
    }
  }

  const counts = overview?.task_counts || {};
  return (
    <div className="min-h-full box-border px-[48px] pt-[32px] pb-[43px] max-[900px]:px-[16px]">
      <AppHeader
        onLogout={onLogout}
        userName={currentUser.username}
        title="TikTok 事业部"
        description="六个生产岗位共用统一任务中心，资源范围和外部授权按租户与岗位隔离。"
      />

      <div className="mt-6 flex flex-wrap items-center justify-between gap-3 rounded-[16px] border border-[#d9e4ff] bg-[#f5f8ff] px-5 py-4">
        <div>
          <strong className="block text-[15px] text-[#18233d]">生产组织模板</strong>
          <span className="mt-1 block text-[12px] text-[#66708a]">
            {overview?.root ? `已启用 · ${overview.departments.length} 个部门` : '尚未初始化，初始化后才会绑定岗位部门'}
          </span>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => void load()} disabled={loading}>刷新</Button>
          {currentUser.role === 'admin' && <>
            <Button variant="outline" onClick={() => void authorizeOfficialShop()} disabled={busy}>连接 TikTok 官方店铺</Button>
            <Button variant="outline" onClick={() => void startShadow()} disabled={busy}>启动 14 天影子运行</Button>
            <Button variant="outline" onClick={() => void bootstrapAssets()} disabled={busy}>{busy ? '初始化中' : '初始化生产资产'}</Button>
            <Button onClick={() => void bootstrap()} disabled={busy}>{busy ? '初始化中' : '初始化组织模板与资产'}</Button>
          </>}
        </div>
      </div>

      {readiness && (
        <section className="mt-4 rounded-[16px] border border-[#e5e8ef] bg-white p-5">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h2 className="m-0 text-[16px] text-[#18181a]">生产就绪检查</h2>
              <p className="mt-1 text-[12px] text-[#858b9c]">只检查当前租户的真实门禁；Mock 授权不会被计入官方授权。</p>
            </div>
            <span className={`rounded-full px-3 py-1 text-[12px] font-medium ${readiness.ready ? 'bg-[#e9f8ef] text-[#18733d]' : 'bg-[#fff5df] text-[#98620a]'}`}>
              {readiness.ready ? '已满足生产门禁' : '仍有门禁待完成'}
            </span>
          </div>
          <div className="mt-4 grid gap-2 lg:grid-cols-2">
            {readiness.gates.map((gate) => (
              <div key={gate.key} className="flex items-start justify-between gap-3 rounded-[12px] bg-[#f7f8fa] px-4 py-3">
                <div>
                  <strong className="block text-[13px] text-[#252936]">{gate.label}</strong>
                  <span className="mt-1 block text-[12px] text-[#66708a]">{gate.detail}</span>
                </div>
                <span className={`shrink-0 text-[12px] font-medium ${gate.status === 'passed' ? 'text-[#18733d]' : gate.status === 'waiting' ? 'text-[#98620a]' : 'text-[#b42318]'}`}>
                  {gate.status === 'passed' ? '通过' : gate.status === 'waiting' ? '等待' : '阻塞'}
                </span>
              </div>
            ))}
          </div>
        </section>
      )}

      <nav className="mt-5 flex gap-2 overflow-x-auto border-b border-[#e5e8ef]" aria-label="TikTok 事业部导航">
        {([
          ['overview', '概览'],
          ['employees', '员工'],
          ['assets', '资产与授权'],
          ['tasks', '任务中心'],
          ['skills', 'SOP / Skill'],
          ['risk', '风险与 KPI'],
          ['data-validation', '数据验证'],
        ] as const).map(([tab, label]) => (
          <button
            key={tab}
            type="button"
            aria-pressed={activeTab === tab}
            onClick={() => setActiveTab(tab)}
            className={`shrink-0 border-b-2 px-3 py-2 text-[13px] ${activeTab === tab ? 'border-[#315efb] text-[#315efb]' : 'border-transparent text-[#66708a]'}`}
          >
            {label}
          </button>
        ))}
      </nav>

      <div className={activeTab === 'overview' ? '' : 'hidden'}>
        {assetResult && (
        <div className="mt-4 rounded-[16px] border border-[#d8f0e3] bg-[#f3fbf6] px-5 py-4 text-[12px] text-[#27633d]">
          已绑定 {assetResult.agent_ids.length} 个数字员工、{assetResult.skill_ids.length} 个 Skill、{assetResult.knowledge_base_ids.length} 个知识库版本和 {assetResult.tool_ids.length} 个只读工具；本次新增 {assetResult.created_count} 项。
        </div>
        )}

      <div className="mt-6 grid grid-cols-4 gap-3 max-[900px]:grid-cols-2">
        {[
          ['待处理', counts.pending || 0],
          ['执行中', counts.in_progress || 0],
          ['待复核', counts.review || 0],
          ['已完成', counts.completed || 0],
        ].map(([label, count]) => (
          <div key={label} className="rounded-[16px] border border-[#e5e8ef] bg-white px-4 py-3">
            <span className="block text-[12px] text-[#858b9c]">{label}</span>
            <strong className="mt-1 block text-[24px] text-[#18181a]">{count}</strong>
          </div>
        ))}
      </div>

      <div className="mt-6 grid grid-cols-2 gap-4 max-[1000px]:grid-cols-1">
        <section className="rounded-[16px] border border-[#e5e8ef] bg-white p-5">
          <h2 className="m-0 text-[16px] text-[#18181a]">部门与岗位</h2>
          <div className="mt-4 grid gap-2">
            {overview?.departments.map((department) => (
              <div key={department.id} className="flex items-center justify-between rounded-[12px] bg-[#f7f8fa] px-4 py-3">
                <span className="text-[13px] text-[#252936]">{department.name}</span>
                <span className="text-[12px] text-[#66708a]">{DEPARTMENT_ROLE_LABELS[department.role_key || ''] || department.role_key}</span>
              </div>
            ))}
            {!loading && !overview?.departments.length && <p className="text-[13px] text-[#858b9c]">请先初始化组织模板。</p>}
          </div>
        </section>

        <section className="rounded-[16px] border border-[#e5e8ef] bg-white p-5">
          <h2 className="m-0 text-[16px] text-[#18181a]">岗位能力与 Casdoor 组</h2>
          <div className="mt-4 grid gap-3">
            {overview?.roles.map((role) => (
              <div key={role.key}>
                <strong className="block text-[13px] text-[#252936]">{role.label}</strong>
                <span className="mt-1 block break-all text-[11px] text-[#858b9c]">{role.casdoor_group} · {role.description}</span>
              </div>
            ))}
          </div>
        </section>
      </div>

      <div className="mt-4 grid grid-cols-2 gap-4 max-[1000px]:grid-cols-1">
        <section className="rounded-[16px] border border-[#e5e8ef] bg-white p-5">
          <h2 className="m-0 text-[16px] text-[#18181a]">可见业务资源</h2>
          <p className="mt-1 text-[12px] text-[#858b9c]">只展示当前用户已授权的 TikTok 店铺、广告账户、达人和直播资源。</p>
          <div className="mt-4 grid gap-2">
            {overview?.resources.map((resource) => (
              <div key={resource.id} className="flex items-center justify-between rounded-[12px] bg-[#f7f8fa] px-4 py-3 text-[12px]">
                <span className="text-[#252936]">{resource.name} · {resource.code}</span>
                <span className="text-[#66708a]">{resource.market || resource.resource_type} · {resource.access_level === 'operator' ? '可操作' : '只读'}</span>
              </div>
            ))}
            {!loading && !overview?.resources.length && <p className="text-[13px] text-[#858b9c]">当前岗位暂无 TikTok 资源范围。</p>}
          </div>
        </section>

        <section className="rounded-[16px] border border-[#e5e8ef] bg-white p-5">
          <h2 className="m-0 text-[16px] text-[#18181a]">外部授权状态</h2>
          <p className="mt-1 text-[12px] text-[#858b9c]">页面只显示授权元数据，不返回令牌或密钥。</p>
          <div className="mt-4 grid gap-2">
            {overview?.authorizations.map((authorization) => (
              <div key={authorization.id} className="rounded-[12px] bg-[#f7f8fa] px-4 py-3 text-[12px]">
                <strong className="text-[#252936]">{authorization.authorization_type} · {authorization.status}</strong>
                <span className="mt-1 block text-[#66708a]">主体 {authorization.subject_id} · {authorization.scopes.join(', ') || '未登记 scope'}</span>
              </div>
            ))}
            {!loading && !overview?.authorizations.length && <p className="text-[13px] text-[#858b9c]">尚未登记 TikTok 外部授权。</p>}
          </div>
        </section>
      </div>
      </div>

      {activeTab === 'employees' && (
        <section className="mt-6 rounded-[16px] border border-[#e5e8ef] bg-white p-5">
          <h2 className="m-0 text-[16px] text-[#18181a]">TikTok 生产员工</h2>
          <p className="mt-1 text-[12px] text-[#858b9c]">Casdoor Group 决定主岗位，业务资源 Scope 决定可见范围。</p>
          <div className="mt-4 grid gap-2 sm:grid-cols-2">
            {overview?.roles.map((role) => (
              <div key={role.key} className="rounded-[12px] bg-[#f7f8fa] px-4 py-3">
                <strong className="block text-[13px] text-[#252936]">{role.label}</strong>
                <span className="mt-1 block text-[11px] text-[#66708a]">{role.casdoor_group}</span>
              </div>
            ))}
          </div>
        </section>
      )}

      {activeTab === 'assets' && (
        <section className="mt-6 rounded-[16px] border border-[#e5e8ef] bg-white p-5">
          <h2 className="m-0 text-[16px] text-[#18181a]">资产与外部授权</h2>
          <p className="mt-1 text-[12px] text-[#858b9c]">只读 Connector 严格绑定 TikTok 资源、授权类型和已批准 Scope。</p>
          <div className="mt-4 grid gap-2">
            {overview?.resources.map((resource) => <div key={resource.id} className="rounded-[12px] bg-[#f7f8fa] px-4 py-3 text-[12px]">{resource.name} · {resource.market || resource.resource_type} · {resource.access_level}</div>)}
            {!loading && !overview?.resources.length && <p className="text-[13px] text-[#858b9c]">当前没有可见 TikTok 资产。</p>}
          </div>
        </section>
      )}

      {activeTab === 'tasks' && (
        <section className="mt-6 rounded-[16px] border border-[#e5e8ef] bg-white p-5">
          <h2 className="m-0 text-[16px] text-[#18181a]">统一任务中心</h2>
          <p className="mt-1 text-[12px] text-[#858b9c]">TikTok 跟进事项按岗位进入现有任务队列；执行前仍需通过权限和审批门禁。</p>
          <div className="mt-4 grid grid-cols-4 gap-3 max-[900px]:grid-cols-2">
            {Object.entries(counts).map(([status, count]) => <div key={status} className="rounded-[12px] bg-[#f7f8fa] px-4 py-3"><span className="block text-[12px] text-[#858b9c]">{status}</span><strong className="mt-1 block text-[22px] text-[#18181a]">{count}</strong></div>)}
          </div>
        </section>
      )}

      {activeTab === 'skills' && (
        <section className="mt-6 rounded-[16px] border border-[#e5e8ef] bg-white p-5">
          <h2 className="m-0 text-[16px] text-[#18181a]">SOP / Skill 绑定</h2>
          <p className="mt-1 text-[12px] text-[#858b9c]">种子资产在业务负责人复核后才能发布 AgentRelease；当前不自动发布。</p>
          {assetResult && <div className="mt-4 grid gap-2 text-[13px] text-[#27633d]"><span>{assetResult.skill_ids.length} 个 Skill 已绑定</span><span>{assetResult.knowledge_base_ids.length} 个知识库版本已绑定</span><span>{assetResult.tool_ids.length} 个只读工具已绑定</span></div>}
          {releasePreflight && (
            <div className="mt-5 rounded-[12px] border border-[#d9e4ff] bg-[#f5f8ff] p-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <strong className="text-[13px] text-[#18233d]">五个 AgentRelease 预检</strong>
                <span className={`text-[12px] font-medium ${releasePreflight.ready ? 'text-[#18733d]' : 'text-[#98620a]'}`}>{releasePreflight.ready ? '全部通过' : '存在阻塞项'}</span>
              </div>
              <div className="mt-3 grid gap-2">
                {releasePreflight.items.map((item) => (
                  <div key={item.slug} className="flex flex-wrap items-start justify-between gap-2 rounded-[10px] bg-white px-3 py-2 text-[12px]">
                    <div><strong className="text-[#252936]">{item.name}</strong><span className="ml-2 text-[#858b9c]">{item.release_state || '未发布'}</span>{item.error && <span className="mt-1 block text-[#b42318]">{item.error}</span>}</div>
                    <span className={item.ready ? 'text-[#18733d]' : 'text-[#b42318]'}>{item.ready ? '可发布' : '不可发布'}</span>
                  </div>
                ))}
              </div>
              <div className="mt-4 flex flex-wrap gap-2">
                <input value={approvalReference} onChange={(event) => setApprovalReference(event.target.value)} placeholder="业务负责人审批编号" className="h-9 min-w-[220px] rounded-[8px] border border-[#d7dce8] px-3 text-[12px] outline-none focus:border-[#315efb]" aria-label="业务负责人审批编号" />
                <Button onClick={() => void publishTikTokReleases()} disabled={busy || !releasePreflight.ready || approvalReference.trim().length < 3}>按审批编号发布五个 AgentRelease</Button>
                <Button variant="outline" onClick={() => void verifyM2M()} disabled={busy}>验证五个 Casdoor M2M</Button>
              </div>
              {m2mVerification && <div className="mt-3 rounded-[10px] border border-[#e5e8ef] bg-[#f7f8fa] p-3 text-[12px]">
                <strong className="block text-[13px] text-[#252936]">M2M 验证结果 · {m2mVerification.verified_count}/{m2mVerification.verified_count + m2mVerification.failed_count} 通过</strong>
                <div className="mt-2 grid gap-1 sm:grid-cols-2">{m2mVerification.items.map((item) => <div key={item.agent_id || item.application} className="flex items-center justify-between rounded-[8px] bg-white px-2 py-1"><span>{item.application || item.agent_id || '未绑定身份'}</span><span className={item.status === 'verified' ? 'text-[#18733d]' : 'text-[#b42318]'}>{item.status === 'verified' ? '已验证' : item.error_code || '验证失败'}</span></div>)}</div>
              </div>}
            </div>
          )}
            <div className="mt-5 rounded-[12px] border border-[#e5e8ef] p-4">
            <div className="flex flex-wrap items-center justify-between gap-2"><div><strong className="text-[13px] text-[#252936]">五条 Mock SOP 回放验收</strong><p className="mt-1 text-[12px] text-[#858b9c]">验证任务 → 知识 → 只读工具 → Trace → Evidence → 待办链路，不写入 TikTok 外部系统。</p></div><div className="flex flex-wrap gap-2"><Button variant="outline" onClick={() => void runMockReplays()} disabled={busy}>运行契约回放</Button><Button variant="outline" onClick={() => void runMockReplays(true)} disabled={busy}>写入任务中心（Mock）</Button><Button variant="outline" onClick={() => void executeMockReplays()} disabled={busy}>运行 Sandbox Worker</Button><Button variant="outline" onClick={() => void runExceptionMatrix()} disabled={busy}>验收异常矩阵</Button></div></div>
            {mockReplay && <div className="mt-3 grid gap-2">{mockReplay.items.map((item) => <div key={item.sop_id} className="flex flex-wrap items-center justify-between gap-2 rounded-[10px] bg-[#f7f8fa] px-3 py-2 text-[12px]"><span className="text-[#252936]"><strong>{item.sop_id}</strong> · {item.title}</span><span className="text-[#18733d]">回放通过 · Trace {item.trace_id.slice(-8)} · {mockReplay.persisted ? '任务已落库' : '待办契约通过'}</span></div>)}</div>}
            {sandboxReplay && <div className="mt-3 rounded-[10px] border border-[#d8f0e3] bg-[#f3fbf6] p-3 text-[12px] text-[#27633d]"><strong className="block text-[13px]">Sandbox 执行结果 · 已处理 {sandboxReplay.processed_count} 条</strong>{sandboxReplay.items.map((item) => <div key={item.sop_id} className="mt-2 flex flex-wrap items-center justify-between gap-2"><span>{item.sop_id} · {item.task_id}</span><span>{item.run_status || '未生成 Run'} · {item.execution_snapshot_id ? 'Snapshot 已生成' : '等待发布/快照'} · {item.error_code || 'Trace 已返回'}</span></div>)}</div>}
            {exceptionMatrix && <div className="mt-3 rounded-[10px] border border-[#d9e4ff] bg-[#f5f8ff] p-3 text-[12px] text-[#30456f]"><strong className="block text-[13px]">异常矩阵 · {exceptionMatrix.passed_count}/{exceptionMatrix.total_count} 通过</strong><span className="mt-1 block">{exceptionMatrix.sop_count} 条 SOP × {exceptionMatrix.scenario_count} 类异常 · 仅验证失败关闭、错误码和人工跟进契约。</span><div className="mt-2 grid gap-1 sm:grid-cols-2">{exceptionMatrix.items.map((item) => <div key={`${item.sop_id}-${item.scenario}`} className="flex items-center justify-between rounded-[8px] bg-white px-2 py-1"><span>{item.sop_id} · {item.scenario}</span><span className="text-[#18733d]">{item.status} · {item.expected_error_code}</span></div>)}</div></div>}
          </div>
          {!assetResult && !releasePreflight && <p className="mt-4 text-[13px] text-[#858b9c]">请先初始化生产资产。</p>}
        </section>
      )}

      {activeTab === 'risk' && (
        <section className="mt-6 rounded-[16px] border border-[#f2dfbd] bg-[#fffaf0] p-5">
          <h2 className="m-0 text-[16px] text-[#7a4b00]">风险与 KPI</h2>
          <p className="mt-2 text-[13px] leading-6 text-[#7a4b00]">当前 P3-A 仅支持读取、分析、草稿和内部派单。发布内容、修改商品、广告变更、佣金、消息和直播写操作均未注册；缺少证据时必须转人工。</p>
          <div className="mt-4 rounded-[12px] border border-[#ead6aa] bg-white/70 p-4 text-[12px] text-[#6f4500]">
            <strong className="block text-[13px]">14 天影子运行门禁</strong>
            {shadowRun ? <>
              <span className="mt-1 block">状态：{shadowRun.status} · 结束：{new Date(shadowRun.ends_at).toLocaleString()} · 人工对照 {shadowRun.quality.reviewed_count}/{shadowRun.quality.minimum_reviewed_count} · 采纳率 {(shadowRun.quality.adoption_rate * 100).toFixed(1)}% · 严重护栏问题 {shadowRun.quality.guardrail_issue_count}</span>
              <span className="mt-1 block">主 SOP 覆盖：{shadowRun.quality.covered_sop_ids.length}/5{shadowRun.quality.missing_sop_ids.length ? ` · 待覆盖 ${shadowRun.quality.missing_sop_ids.join('、')}` : ''}</span>
            </> : <span className="mt-1 block">尚未启动。启动后只记录读取与分析结果，不执行 TikTok 外部写操作。</span>}
          </div>
          {currentUser.role === 'admin' && shadowRun?.status === 'running' && (
            <div className="mt-4 rounded-[12px] border border-[#ead6aa] bg-white/70 p-4 text-[12px] text-[#6f4500]">
              <strong className="block text-[13px]">追加任务级人工对照</strong>
              <p className="mt-1">仅记录脱敏结论；证据追加后不可覆盖，任务必须处于复核或完成状态且明确关闭外部写入。</p>
              <div className="mt-3 grid gap-2 lg:grid-cols-2">
                <input value={shadowTaskId} onChange={(event) => setShadowTaskId(event.target.value)} placeholder="TikTok 任务 ID" aria-label="TikTok 任务 ID" className="h-9 rounded-[8px] border border-[#d7dce8] bg-white px-3 outline-none focus:border-[#315efb]" />
                <select value={shadowVerdict} onChange={(event) => setShadowVerdict(event.target.value as typeof shadowVerdict)} aria-label="人工采纳结论" className="h-9 rounded-[8px] border border-[#d7dce8] bg-white px-3">
                  <option value="adopted">采纳</option><option value="needs_revision">修改后采纳</option><option value="rejected">拒绝</option>
                </select>
                <select value={shadowIssueCategory} onChange={(event) => setShadowIssueCategory(event.target.value)} aria-label="问题分类" className="h-9 rounded-[8px] border border-[#d7dce8] bg-white px-3">
                  <option value="none">无护栏问题</option><option value="severe_miss">严重漏检</option><option value="unauthorized_access">越权访问</option><option value="false_claim">虚假声明</option><option value="unapproved_external_write">未审批外部写入</option><option value="other">其他问题</option>
                </select>
                <input value={shadowSummary} onChange={(event) => setShadowSummary(event.target.value)} placeholder="脱敏人工对照摘要" aria-label="脱敏人工对照摘要" className="h-9 rounded-[8px] border border-[#d7dce8] bg-white px-3 outline-none focus:border-[#315efb]" />
              </div>
              <Button className="mt-3" onClick={() => void recordShadowEvaluation()} disabled={busy || shadowTaskId.trim().length < 3 || shadowSummary.trim().length < 3}>追加不可变对照证据</Button>
            </div>
          )}
        </section>
      )}

      {activeTab === 'data-validation' && (
        <TikTokDataValidationPanel currentUser={currentUser} />
      )}
    </div>
  );
}
