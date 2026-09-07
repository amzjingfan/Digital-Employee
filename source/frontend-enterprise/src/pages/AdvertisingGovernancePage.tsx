import { useCallback, useEffect, useMemo, useState } from 'react';

import { api, TENANT_ID } from '@/api/client';
import type { EnterpriseAuthUser } from '@/auth';
import AppHeader from '@/components/AppHeader';
import { notify } from '@/components/ui/app-toast';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

type Props = { currentUser: EnterpriseAuthUser; onLogout: () => void };
type Resource = {
  id: string;
  resource_type: 'store' | 'ad_account';
  code: string;
  name: string;
};
type Overview = {
  recommendations_ready: number;
  recommendations_blocked: number;
  actions_waiting_approval: number;
  effectiveness_reviews_pending: number;
  automation_policies_active: number;
  kill_switches_engaged: number;
};
type Recommendation = {
  id: string;
  recommendation_key: string;
  campaign_id: string;
  product_key: string;
  metrics: Record<string, number>;
  constraints: Record<string, unknown>;
  findings: Array<{ code: string; severity: string; gate: string }>;
  recommendation: { note?: string; external_write_executed?: boolean };
  proposed_action_type?: string | null;
  proposed_action_payload: Record<string, unknown>;
  risk_level: string;
  status: string;
  input_digest: string;
  task_id: string;
  linked_task_ids: string[];
  approval_request_id?: string | null;
  approval_status?: string | null;
  version: number;
};
type EffectFollowUp = {
  id: string;
  horizon_days: 7 | 14 | 30;
  baseline: Record<string, number>;
  task_id: string;
  status: string;
  due_at: string;
};
type Policy = {
  id: string;
  resource_id: string;
  action_type: string;
  status: 'active' | 'paused';
  rollout_percent: number;
  max_single_value: number;
  max_daily_value: number;
  max_risk_level: 'low' | 'medium';
  approval_required: boolean;
  kill_switch_engaged: boolean;
  revision: number;
};
type Usage = {
  id: string;
  policy_revision: number;
  action_type: string;
  cohort_bucket: number;
  quantitative_value: number;
  decision: 'allowed' | 'blocked';
  reason: string;
  created_at: string;
};
type Tab = 'recommendations' | 'effects' | 'automation';

const BASE = '/api/enterprise/work-tasks/advertising';
const STATUS_STYLE: Record<string, string> = {
  ready: 'bg-[#e7f6ed] text-[#237a44]',
  action_approved: 'bg-[#e7f6ed] text-[#237a44]',
  allowed: 'bg-[#e7f6ed] text-[#237a44]',
  active: 'bg-[#e7f6ed] text-[#237a44]',
  action_pending: 'bg-[#fff4db] text-[#946200]',
  pending: 'bg-[#fff4db] text-[#946200]',
  paused: 'bg-[#f2f4f7] text-[#667085]',
  blocked: 'bg-[#fff0ef] text-[#b42318]',
  action_rejected: 'bg-[#fff0ef] text-[#b42318]',
};

function Pill({ value }: { value: string }) {
  return (
    <span
      className={cn(
        'rounded-full px-2 py-1 text-[10px] font-medium',
        STATUS_STYLE[value] || 'bg-[#f2f4f7] text-[#667085]',
      )}
    >
      {value}
    </span>
  );
}

function TaskLink({ taskId, label = '打开任务' }: { taskId: string; label?: string }) {
  return (
    <a
      className="text-[11px] text-[#315ea8]"
      href={`/enterprise/work-tasks?task_id=${encodeURIComponent(taskId)}`}
    >
      {label}
    </a>
  );
}

function number(value: number | undefined, digits = 2): string {
  return typeof value === 'number' ? value.toFixed(digits) : '-';
}

export default function AdvertisingGovernancePage({ currentUser, onLogout }: Props) {
  const [tab, setTab] = useState<Tab>('recommendations');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState('');
  const [overview, setOverview] = useState<Overview | null>(null);
  const [resources, setResources] = useState<Resource[]>([]);
  const [recommendations, setRecommendations] = useState<Recommendation[]>([]);
  const [effects, setEffects] = useState<EffectFollowUp[]>([]);
  const [policies, setPolicies] = useState<Policy[]>([]);
  const [usage, setUsage] = useState<Usage[]>([]);
  const tenantId = currentUser.tenant_id || TENANT_ID;
  const role = currentUser.business_role || '';
  const manager = currentUser.role === 'admin' || role === 'operations_supervisor';
  const canInspect = manager || role === 'advertising_inspection_specialist';
  const adAccount = resources.find((item) => item.resource_type === 'ad_account');
  const store = resources.find((item) => item.resource_type === 'store');
  const readyRecommendation = recommendations.find((item) => item.status === 'ready');

  const loadAll = useCallback(async () => {
    const tenant = encodeURIComponent(tenantId);
    const calls: [
      Promise<Overview>,
      Promise<Resource[]>,
      Promise<Recommendation[]>,
      Promise<EffectFollowUp[]>,
      Promise<Policy[]>,
      Promise<Usage[]>,
    ] = [
      api.get(`${BASE}/overview?tenant_id=${tenant}`),
      api.get(`/api/enterprise/business-resources?tenant_id=${tenant}`),
      api.get(`${BASE}/recommendations?tenant_id=${tenant}`),
      api.get(`${BASE}/effect-follow-ups?tenant_id=${tenant}`),
      api.get(`${BASE}/automation-policies?tenant_id=${tenant}`),
      manager ? api.get(`${BASE}/automation-usage?tenant_id=${tenant}`) : Promise.resolve([]),
    ];
    const [nextOverview, nextResources, nextRecommendations, nextEffects, nextPolicies, nextUsage] =
      await Promise.all(calls);
    setOverview(nextOverview);
    setResources(nextResources.filter((item) => ['store', 'ad_account'].includes(item.resource_type)));
    setRecommendations(nextRecommendations);
    setEffects(nextEffects);
    setPolicies(nextPolicies);
    setUsage(nextUsage);
  }, [manager, tenantId]);

  useEffect(() => {
    void loadAll()
      .catch((error) => notify.error('加载广告治理数据失败', { description: String(error) }))
      .finally(() => setLoading(false));
  }, [loadAll]);

  async function mutate(label: string, action: () => Promise<unknown>) {
    setBusy(label);
    try {
      await action();
      notify.success(`${label}完成`);
      await loadAll();
    } catch (error) {
      notify.error(`${label}失败`, { description: error instanceof Error ? error.message : String(error) });
    } finally {
      setBusy('');
    }
  }

  function createRecommendation() {
    if (!adAccount) {
      notify.warning('请先创建并授权广告账户资源');
      return;
    }
    const suffix = Date.now();
    void mutate('生成广告巡检建议', () =>
      api.post(`${BASE}/recommendations`, {
        tenant_id: tenantId,
        recommendation_key: `AD-DEMO-${suffix}`,
        ad_account_resource_id: adAccount.id,
        store_resource_id: store?.id,
        campaign_id: `CAMPAIGN-DEMO-${String(suffix).slice(-6)}`,
        product_key: 'PRODUCT-DEMO-1001',
        spend: 120,
        attributed_sales: 600,
        impressions: 100000,
        clicks: 250,
        orders: 10,
        price: 40,
        profit_per_order: 12,
        available_units: 1000,
        inbound_units: 0,
        forecast_daily_sales: 10,
        reserve_stock_units: 50,
        minimum_days_of_cover: 21,
        promotion_active: false,
        minimum_ctr: 0.003,
        minimum_conversion_rate: 0.06,
        proposed_action_type: 'change_daily_budget',
        proposed_action_payload: {
          daily_budget: 50,
          previous_daily_budget: 40,
          currency: 'USD',
        },
        recommendation_note: '在利润、价格、库存和促销约束内评估预算调整，并派发低效原因任务。',
      }),
    );
  }

  function requestAction(item: Recommendation) {
    void mutate('提交独立审批', () =>
      api.post(`${BASE}/recommendations/${encodeURIComponent(item.id)}/request-action`, {
        tenant_id: tenantId,
        expected_version: item.version,
        summary: `基于 ${item.recommendation_key} 的约束快照申请调整广告预算`,
      }),
    );
  }

  function saveSafePolicy() {
    if (!adAccount) {
      notify.warning('请先创建并授权广告账户资源');
      return;
    }
    void mutate('保存安全灰度策略', () =>
      api.put(`${BASE}/automation-policies`, {
        tenant_id: tenantId,
        resource_id: adAccount.id,
        action_type: 'change_daily_budget',
        status: 'active',
        rollout_percent: 10,
        max_single_value: 100,
        max_daily_value: 300,
        max_risk_level: 'medium',
        approval_required: true,
        kill_switch_engaged: true,
      }),
    );
  }

  function toggleKillSwitch(policy: Policy) {
    void mutate(policy.kill_switch_engaged ? '解除策略熔断' : '启用策略熔断', () =>
      api.put(`${BASE}/automation-policies`, {
        tenant_id: tenantId,
        resource_id: policy.resource_id,
        action_type: policy.action_type,
        status: policy.status,
        rollout_percent: policy.rollout_percent,
        max_single_value: policy.max_single_value,
        max_daily_value: policy.max_daily_value,
        max_risk_level: policy.max_risk_level,
        approval_required: true,
        kill_switch_engaged: !policy.kill_switch_engaged,
      }),
    );
  }

  const cards = useMemo(
    () =>
      overview
        ? [
            ['可执行建议', overview.recommendations_ready],
            ['门禁阻断', overview.recommendations_blocked],
            ['等待审批', overview.actions_waiting_approval],
            ['效果复盘', overview.effectiveness_reviews_pending],
            ['生效策略', overview.automation_policies_active],
            ['熔断开启', overview.kill_switches_engaged],
          ]
        : [],
    [overview],
  );

  return (
    <div className="min-h-screen bg-[#f6f7f9] text-[#252936]">
      <AppHeader
        title="广告巡检与自动化治理"
        description="利润、价格、库存和促销约束先于广告动作；所有外部写操作必须独立审批。"
        userName={currentUser.display_name || currentUser.username}
        onLogout={onLogout}
      />
      <div className="mx-auto max-w-[1500px] px-5 py-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-[24px] font-semibold">广告巡检与自动化治理</h1>
            <p className="mt-2 text-[13px] text-[#667085]">
              指标巡检 → 经营约束 → 跨岗位任务 → 独立审批 → 受控执行 → 7/14/30 天复盘
            </p>
          </div>
          <div className="rounded-[12px] border border-[#f3d49a] bg-[#fff9eb] px-4 py-3 text-[11px] text-[#805b12]">
            自动化策略不能绕过人工审批；熔断、灰度、单次/单日限额和风险上限共同生效。
          </div>
        </div>

        <div className="mt-5 grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
          {cards.map(([label, value]) => (
            <div key={String(label)} className="rounded-[14px] border border-[#e6e8ee] bg-white p-4">
              <p className="text-[10px] text-[#858b9c]">{label}</p>
              <strong className="mt-2 block text-[22px]">{value}</strong>
            </div>
          ))}
        </div>

        <div className="mt-5 flex flex-wrap gap-2">
          {([
            ['recommendations', '巡检建议'],
            ['effects', '效果复盘'],
            ['automation', '自动化门禁'],
          ] as Array<[Tab, string]>).map(([key, label]) => (
            <button
              key={key}
              type="button"
              onClick={() => setTab(key)}
              className={cn(
                'rounded-full px-4 py-2 text-[12px]',
                tab === key ? 'bg-[#252936] text-white' : 'bg-white text-[#667085]',
              )}
            >
              {label}
            </button>
          ))}
        </div>

        {loading && <p className="py-20 text-center text-[13px] text-[#858b9c]">加载中…</p>}

        {!loading && tab === 'recommendations' && (
          <section className="mt-5 rounded-[18px] border border-[#e6e8ee] bg-white p-5">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h2 className="text-[16px] font-semibold">广告巡检建议</h2>
                <p className="mt-1 text-[11px] text-[#858b9c]">
                  低 CTR 进入美工队列，低转化进入 Listing 队列，库存不足进入采购队列。
                </p>
              </div>
              {canInspect && (
                <Button disabled={Boolean(busy) || !adAccount} onClick={createRecommendation}>
                  生成演示巡检
                </Button>
              )}
            </div>
            <div className="mt-5 grid gap-3 xl:grid-cols-2">
              {recommendations.map((item) => (
                <div key={item.id} className="rounded-[14px] border p-4">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <strong className="text-[13px]">{item.campaign_id}</strong>
                      <p className="mt-1 text-[10px] text-[#858b9c]">{item.product_key}</p>
                    </div>
                    <Pill value={item.status} />
                  </div>
                  <div className="mt-3 grid grid-cols-5 gap-2 text-center text-[10px]">
                    <div className="rounded-[8px] bg-[#f7f8fa] p-2">ACoS<br /><b>{number(item.metrics.acos * 100, 1)}%</b></div>
                    <div className="rounded-[8px] bg-[#f7f8fa] p-2">ROAS<br /><b>{number(item.metrics.roas)}</b></div>
                    <div className="rounded-[8px] bg-[#f7f8fa] p-2">CTR<br /><b>{number(item.metrics.ctr * 100, 2)}%</b></div>
                    <div className="rounded-[8px] bg-[#f7f8fa] p-2">CVR<br /><b>{number(item.metrics.conversion_rate * 100, 1)}%</b></div>
                    <div className="rounded-[8px] bg-[#f7f8fa] p-2">库存天数<br /><b>{number(item.metrics.days_of_cover, 0)}</b></div>
                  </div>
                  <p className="mt-3 text-[11px] text-[#505668]">{item.recommendation.note}</p>
                  {item.findings.length > 0 && (
                    <div className="mt-3 flex flex-wrap gap-2">
                      {item.findings.map((finding) => (
                        <span key={finding.code} className="rounded-full bg-[#fff4db] px-2 py-1 text-[9px] text-[#946200]">
                          {finding.code} · {finding.gate}
                        </span>
                      ))}
                    </div>
                  )}
                  <div className="mt-4 flex flex-wrap items-center gap-4">
                    <TaskLink taskId={item.task_id} />
                    {item.linked_task_ids.map((taskId, index) => (
                      <TaskLink key={taskId} taskId={taskId} label={`联动任务 ${index + 1}`} />
                    ))}
                    {item.approval_request_id && (
                      <a className="text-[11px] text-[#315ea8]" href="/enterprise/business-resources">
                        审批 {item.approval_status || 'pending'}
                      </a>
                    )}
                  </div>
                  {canInspect && item.status === 'ready' && item.proposed_action_type && (
                    <Button
                      className="mt-4"
                      variant="outline"
                      disabled={Boolean(busy)}
                      onClick={() => requestAction(item)}
                    >
                      提交独立审批
                    </Button>
                  )}
                </div>
              ))}
            </div>
            {recommendations.length === 0 && (
              <p className="py-12 text-center text-[12px] text-[#858b9c]">
                暂无巡检建议；先绑定广告账户，再生成首个演示巡检。
              </p>
            )}
          </section>
        )}

        {!loading && tab === 'effects' && (
          <section className="mt-5 rounded-[18px] border border-[#e6e8ee] bg-white p-5">
            <h2 className="text-[16px] font-semibold">7/14/30 天效果复盘</h2>
            <p className="mt-1 text-[11px] text-[#858b9c]">
              仅在外部动作确认成功后建单，基线随执行回执固定，失败或未知状态不建单。
            </p>
            <div className="mt-5 grid gap-3 md:grid-cols-3">
              {effects.map((item) => (
                <div key={item.id} className="rounded-[14px] border p-4">
                  <div className="flex justify-between"><strong>{item.horizon_days} 天复盘</strong><Pill value={item.status} /></div>
                  <p className="mt-3 text-[11px] text-[#667085]">基线 ACoS {number(item.baseline.acos * 100, 1)}% · ROAS {number(item.baseline.roas)}</p>
                  <p className="mt-2 text-[10px] text-[#858b9c]">到期 {new Date(item.due_at).toLocaleString()}</p>
                  <div className="mt-3"><TaskLink taskId={item.task_id} /></div>
                </div>
              ))}
            </div>
            {effects.length === 0 && <p className="py-12 text-center text-[12px] text-[#858b9c]">暂无效果复盘任务。</p>}
          </section>
        )}

        {!loading && tab === 'automation' && (
          <div className="mt-5 grid gap-5 xl:grid-cols-2">
            <section className="rounded-[18px] border border-[#e6e8ee] bg-white p-5">
              <div className="flex flex-wrap justify-between gap-3">
                <div><h2 className="text-[16px] font-semibold">自动化执行门禁</h2><p className="mt-1 text-[11px] text-[#858b9c]">策略只在独立审批后追加校验，不具备免审权限。</p></div>
                {manager && <Button disabled={Boolean(busy) || !adAccount} onClick={saveSafePolicy}>配置安全灰度</Button>}
              </div>
              <div className="mt-4 space-y-3">
                {policies.map((item) => (
                  <div key={item.id} className="rounded-[14px] border p-4">
                    <div className="flex justify-between"><strong className="text-[13px]">{item.action_type} · rev {item.revision}</strong><Pill value={item.status} /></div>
                    <p className="mt-3 text-[11px] text-[#667085]">灰度 {item.rollout_percent}% · 单次 ≤ {item.max_single_value} · 单日 ≤ {item.max_daily_value} · 风险 ≤ {item.max_risk_level}</p>
                    <p className={cn('mt-2 text-[11px]', item.kill_switch_engaged ? 'text-[#b42318]' : 'text-[#237a44]')}>熔断：{item.kill_switch_engaged ? '已开启' : '已解除'} · 独立审批：强制</p>
                    {manager && <Button className="mt-3" variant="outline" disabled={Boolean(busy)} onClick={() => toggleKillSwitch(item)}>{item.kill_switch_engaged ? '解除熔断' : '立即熔断'}</Button>}
                  </div>
                ))}
              </div>
            </section>
            <section className="rounded-[18px] border border-[#e6e8ee] bg-white p-5">
              <h2 className="text-[16px] font-semibold">不可变策略判定账本</h2>
              <p className="mt-1 text-[11px] text-[#858b9c]">记录策略版本、灰度桶、定量值和允许/阻断原因。</p>
              <div className="mt-4 space-y-3">
                {usage.map((item) => (
                  <div key={item.id} className="rounded-[12px] border p-3">
                    <div className="flex justify-between"><strong className="text-[12px]">{item.action_type} · rev {item.policy_revision}</strong><Pill value={item.decision} /></div>
                    <p className="mt-2 text-[10px] text-[#667085]">桶 {item.cohort_bucket} · 数值 {item.quantitative_value} · {item.reason}</p>
                  </div>
                ))}
              </div>
              {usage.length === 0 && <p className="py-12 text-center text-[12px] text-[#858b9c]">暂无策略判定记录。</p>}
            </section>
          </div>
        )}

        {!loading && canInspect && !adAccount && (
          <div className="mt-5 rounded-[12px] border border-[#f3d49a] bg-[#fff9eb] p-4 text-[12px] text-[#805b12]">
            未发现当前岗位可访问的广告账户。请由运营主管在“业务资源与审批”中创建并授权。
          </div>
        )}
        {!loading && readyRecommendation && <span className="sr-only">存在可提交审批的广告建议</span>}
      </div>
    </div>
  );
}
