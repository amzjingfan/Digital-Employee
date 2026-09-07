import { useCallback, useEffect, useMemo, useState } from 'react';

import { api, TENANT_ID } from '@/api/client';
import type { EnterpriseAuthUser } from '@/auth';
import AppHeader from '@/components/AppHeader';
import { Button } from '@/components/ui/button';
import { notify } from '@/components/ui/app-toast';
import { cn } from '@/lib/utils';

type Props = { currentUser: EnterpriseAuthUser; onLogout: () => void };
type Resource = { id: string; resource_type: 'store' | 'supplier'; code: string; name: string };
type Overview = {
  published_rule_sets: number;
  blocked_listing_checks: number;
  creative_assets_waiting_review: number;
  procurement_recommendations_waiting_review: number;
  launch_gates_blocked: number;
  launch_gates_waiting_approval: number;
  open_quality_issues: number;
};
type RuleSet = { id: string; version: string; platform: string; marketplace: string; category: string; status: string; content_digest: string; effective_at: string; expires_at?: string | null };
type Finding = { location: string; risk: string; rule: string; evidence: string; suggestion: string; gate: string };
type ListingCheck = { id: string; check_key: string; product_key: string; sku: string; rule_version: string; sku_fact_version: string; gate_status: string; findings: Finding[]; task_id: string; created_at: string };
type CreativeBrief = { id: string; brief_key: string; product_key: string; language: string; required_assets: string[]; status: string; task_id: string; due_at?: string | null };
type CreativeAsset = { id: string; asset_key: string; version: number; product_key: string; asset_type: string; file_digest: string; status: string; parent_version_id?: string | null; required_human_approval: boolean; checks: Record<string, unknown>; created_at: string };
type ProcurementRecommendation = { id: string; recommendation_key: string; product_key: string; sku: string; recommended_quantity: number; estimated_landed_cost: number; lead_time_days: number; formula: string; risk_level: string; risk_reasons: string[]; status: string; task_id: string };
type LaunchGate = { id: string; launch_key: string; product_key: string; sku: string; status: string; blockers: Array<{ code: string; detail: string }>; evidence_digest: string; approval_request_id?: string | null; approval_status?: string | null; task_id: string; version: number };
type QualityIssue = { id: string; source_case_id: string; product_key: string; category: string; root_cause: string; task_ids: string[]; status: string; created_at: string };
type Tab = 'listing' | 'creative' | 'procurement' | 'launch' | 'quality';

const BASE = '/api/enterprise/work-tasks/product-lifecycle';
const PRODUCT_KEY = 'PRODUCT-DEMO-1001';
const SKU = 'SKU-DEMO-1001';

const STATUS_STYLE: Record<string, string> = {
  pass: 'bg-[#e7f6ed] text-[#237a44]', approved: 'bg-[#e7f6ed] text-[#237a44]', ready: 'bg-[#e7f6ed] text-[#237a44]', published: 'bg-[#e7f6ed] text-[#237a44]', reviewed: 'bg-[#e7f6ed] text-[#237a44]',
  warn: 'bg-[#fff4db] text-[#946200]', pending_review: 'bg-[#fff4db] text-[#946200]', draft: 'bg-[#f2f4f7] text-[#667085]', waiting_approval: 'bg-[#fff4db] text-[#946200]',
  block: 'bg-[#fff0ef] text-[#b42318]', blocked: 'bg-[#fff0ef] text-[#b42318]', rejected: 'bg-[#fff0ef] text-[#b42318]',
};

function Pill({ value }: { value: string }) {
  return <span className={cn('rounded-full px-2 py-1 text-[10px] font-medium', STATUS_STYLE[value] || 'bg-[#f2f4f7] text-[#667085]')}>{value}</span>;
}

function TaskLink({ taskId }: { taskId: string }) {
  return <a className="text-[11px] text-[#315ea8]" href={`/enterprise/work-tasks?task_id=${encodeURIComponent(taskId)}`}>打开任务</a>;
}

export default function ProductLifecyclePage({ currentUser, onLogout }: Props) {
  const [tab, setTab] = useState<Tab>('listing');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState('');
  const [overview, setOverview] = useState<Overview | null>(null);
  const [resources, setResources] = useState<Resource[]>([]);
  const [rules, setRules] = useState<RuleSet[]>([]);
  const [checks, setChecks] = useState<ListingCheck[]>([]);
  const [briefs, setBriefs] = useState<CreativeBrief[]>([]);
  const [assets, setAssets] = useState<CreativeAsset[]>([]);
  const [recommendations, setRecommendations] = useState<ProcurementRecommendation[]>([]);
  const [gates, setGates] = useState<LaunchGate[]>([]);
  const [qualityIssues, setQualityIssues] = useState<QualityIssue[]>([]);
  const manager = currentUser.role === 'admin' || currentUser.business_role === 'operations_supervisor';
  const role = currentUser.business_role || '';
  const canListing = manager || role === 'listing_compliance_specialist';
  const canDesign = manager || role === 'designer';
  const canProcure = manager || role === 'procurement_specialist';
  const store = resources.find((item) => item.resource_type === 'store');
  const supplier = resources.find((item) => item.resource_type === 'supplier');
  const publishedRule = rules.find((item) => item.status === 'published');
  const pendingRule = rules.find((item) => item.status === 'draft');
  const approvedAsset = assets.find((item) => item.status === 'approved' && item.product_key === PRODUCT_KEY);
  const pendingAsset = assets.find((item) => item.status === 'pending_review');
  const reviewedRecommendation = recommendations.find((item) => item.status === 'reviewed' && item.product_key === PRODUCT_KEY);
  const pendingRecommendation = recommendations.find((item) => item.status === 'draft');
  const passedCheck = checks.find((item) => item.gate_status !== 'block' && item.product_key === PRODUCT_KEY);
  const readyGate = gates.find((item) => item.status === 'ready');

  const loadAll = useCallback(async () => {
    const tenant = encodeURIComponent(currentUser.tenant_id || TENANT_ID);
    const [summary, businessResources, nextRules, nextChecks, nextBriefs, nextAssets, nextRecommendations, nextGates, issues] = await Promise.all([
      api.get<Overview>(`${BASE}/overview?tenant_id=${tenant}`),
      api.get<Resource[]>(`/api/enterprise/business-resources?tenant_id=${tenant}`),
      api.get<RuleSet[]>(`${BASE}/listing-rules?tenant_id=${tenant}`),
      api.get<ListingCheck[]>(`${BASE}/listing-checks?tenant_id=${tenant}`),
      api.get<CreativeBrief[]>(`${BASE}/creative-briefs?tenant_id=${tenant}`),
      api.get<CreativeAsset[]>(`${BASE}/creative-assets?tenant_id=${tenant}`),
      api.get<ProcurementRecommendation[]>(`${BASE}/procurement-recommendations?tenant_id=${tenant}`),
      api.get<LaunchGate[]>(`${BASE}/launch-gates?tenant_id=${tenant}`),
      api.get<QualityIssue[]>(`${BASE}/quality-issues?tenant_id=${tenant}`),
    ]);
    setOverview(summary); setResources(businessResources); setRules(nextRules); setChecks(nextChecks); setBriefs(nextBriefs); setAssets(nextAssets); setRecommendations(nextRecommendations); setGates(nextGates); setQualityIssues(issues);
  }, [currentUser.tenant_id]);

  useEffect(() => { void loadAll().catch((error) => notify.error('加载商品治理数据失败', { description: String(error) })).finally(() => setLoading(false)); }, [loadAll]);

  async function run(label: string, operation: () => Promise<unknown>) {
    setBusy(label);
    try { await operation(); await loadAll(); notify.success(`${label}已完成`); }
    catch (error) { notify.error(`${label}失败`, { description: error instanceof Error ? error.message : String(error) }); }
    finally { setBusy(''); }
  }

  function createRule() {
    return run('创建规则草稿', () => api.post(`${BASE}/listing-rules`, {
      tenant_id: currentUser.tenant_id, platform: 'Amazon', marketplace: 'US', category: 'Electronics', version: `demo-${Date.now()}`,
      rules: { banned_terms: ['cure', 'guaranteed results'], restricted_terms: [{ term: 'FDA approved', required_certification: 'FDA', gate: 'block' }], required_certifications: ['FCC'], required_labels: ['Made in China'], intellectual_property_terms: ['Apple AirTag'], optimization_terms: ['wireless'], max_title_chars: 180, required_content_fields: ['title', 'bullets', 'description'] },
      source_references: [{ source_id: 'amazon-electronics-style-guide', title: 'Amazon Electronics reviewed platform guide', url: 'https://sellercentral.amazon.com/help', retrieved_at: new Date().toISOString() }],
      effective_at: new Date(Date.now() - 3600000).toISOString(), expires_at: new Date(Date.now() + 90 * 86400000).toISOString(),
    }));
  }

  function publishRule() { if (!pendingRule) return Promise.resolve(); return run('审核发布规则', () => api.post(`${BASE}/listing-rules/${pendingRule.id}/publish`, { tenant_id: currentUser.tenant_id, expected_digest: pendingRule.content_digest, review_note: '已核对平台原始来源、适用站点、品类和有效期。' })); }
  function createBrief() { if (!store) return Promise.resolve(); return run('创建创意 Brief', () => api.post(`${BASE}/creative-briefs`, { tenant_id: currentUser.tenant_id, brief_key: `BRIEF-${Date.now()}`, store_resource_id: store.id, product_key: PRODUCT_KEY, language: 'en-US', dimensions: { width: 2000, height: 2000, unit: 'px' }, selling_points: ['Wireless control', 'Compact enclosure'], scenes: ['Home office', 'Product detail'], required_assets: ['main_image', 'secondary_image', 'a_plus'], constraints: { white_background: true, safe_area_percent: 5, brand_color: '#315EA8' }, due_at: new Date(Date.now() + 3 * 86400000).toISOString() })); }
  function createAsset() { const brief = briefs[0]; if (!brief) return Promise.resolve(); return run('登记素材版本', () => api.post(`${BASE}/creative-assets`, { tenant_id: currentUser.tenant_id, asset_key: `ASSET-${brief.product_key}-MAIN`, brief_id: brief.id, asset_type: 'main_image', file_reference: `s3://tenant-demo/review/${brief.product_key}-main-v1.png`, file_digest: `sha256:demo-${Date.now()}`, provenance: { source: 'in-house-photo-and-controlled-ai-edit', license: 'tenant-owned', model: 'staffdeck-demo-editor' }, generation_parameters: { background_cleanup: true, seed: 42 }, checks: { dimensions: true, clarity: true, text_safe_area: true, logo: true, brand_colors: true, factual_consistency: true, copyright: true }, contains_sensitive_claims: false })); }
  function reviewAsset() { if (!pendingAsset) return Promise.resolve(); return run('人工审核素材', () => api.post(`${BASE}/creative-assets/${pendingAsset.id}/review`, { tenant_id: currentUser.tenant_id, decision: 'approved', note: '尺寸、清晰度、安全区、品牌、事实与版权证据均已人工核验。' })); }
  function runListingCheck() { if (!store || !publishedRule) return Promise.resolve(); return run('执行 Listing 检查', () => api.post(`${BASE}/listing-checks`, { tenant_id: currentUser.tenant_id, check_key: `CHECK-${Date.now()}`, store_resource_id: store.id, product_key: PRODUCT_KEY, sku: SKU, language: 'en-US', rule_set_id: publishedRule.id, sku_fact_version: 'facts-v3', sku_facts: { material: 'ABS', dimensions: '10x8x3 cm', country_of_origin: 'China', certifications: ['FCC'] }, content: { title: 'Wireless compact controller', bullets: ['Made in China', 'ABS enclosure'], description: 'Wireless controller for home office workflows.', attributes: { battery_required: false }, keywords: ['wireless', 'controller'], image_text: ['Compact controller'], video_script: 'Demonstrate setup without unsupported claims.', declared_facts: { material: 'ABS', dimensions: '10x8x3 cm', country_of_origin: 'China' }, translations: { 'de-DE': { declared_facts: { material: 'ABS', dimensions: '10x8x3 cm', country_of_origin: 'China' } } } }, asset_version_ids: approvedAsset ? [approvedAsset.id] : [] })); }
  function createProcurement() { if (!supplier) return Promise.resolve(); return run('生成采购建议', () => api.post(`${BASE}/procurement-recommendations`, { tenant_id: currentUser.tenant_id, recommendation_key: `PROC-${Date.now()}`, supplier_resource_id: supplier.id, product_key: PRODUCT_KEY, sku: SKU, forecast_daily_sales: 10, planning_horizon_days: 30, available_units: 80, inbound_units: 40, safety_stock_units: 50, promotion_units: 30, advertising_lift_units: 20, moq: 100, lead_time_days: 15, quote_unit_cost: 8, freight_unit_cost: 1, duty_unit_cost: 0.5, quote_observed_at: new Date().toISOString(), qc_failure_rate: 0.01, cash_budget: 5000, currency: 'USD' })); }
  function reviewProcurement() { if (!pendingRecommendation) return Promise.resolve(); return run('审核采购建议', () => api.post(`${BASE}/procurement-recommendations/${pendingRecommendation.id}/review`, { tenant_id: currentUser.tenant_id, decision: 'reviewed', note: '销量、库存、MOQ、交期、报价、质检与现金约束已核验；不创建采购单。' })); }
  function evaluateLaunch() { if (!store || !supplier || !passedCheck || !approvedAsset || !reviewedRecommendation) return Promise.resolve(); return run('评估新品门禁', () => api.post(`${BASE}/launch-gates`, { tenant_id: currentUser.tenant_id, launch_key: `LAUNCH-${Date.now()}`, store_resource_id: store.id, supplier_resource_id: supplier.id, product_key: PRODUCT_KEY, sku: SKU, sku_fact_version: 'facts-v3', bom_version: 'bom-v5', packaging_version: 'pack-v2', certification_ids: ['FCC'], listing_check_id: passedCheck.id, asset_version_ids: [approvedAsset.id], procurement_recommendation_id: reviewedRecommendation.id, supplier_lead_time_confirmed: true })); }
  function submitLaunch() { if (!readyGate) return Promise.resolve(); return run('提交发布审批', () => api.post(`${BASE}/launch-gates/${readyGate.id}/submit`, { tenant_id: currentUser.tenant_id, expected_version: readyGate.version, listing_id: `ASIN-DRAFT-${Date.now()}`, marketplace: 'US', product_type: 'Electronics', attributes: { sku: SKU, material: 'ABS' }, summary: `发布已审核 ${SKU} Listing；必须通过双人审批后由受控连接器执行` })); }

  const cards = useMemo(() => overview ? [
    ['已发布规则', overview.published_rule_sets], ['Listing 阻断', overview.blocked_listing_checks], ['素材待审', overview.creative_assets_waiting_review], ['采购待审', overview.procurement_recommendations_waiting_review], ['新品门禁阻断', overview.launch_gates_blocked], ['发布待审批', overview.launch_gates_waiting_approval], ['质量问题', overview.open_quality_issues],
  ] : [], [overview]);

  return <div className="min-h-screen bg-[#f6f7f9] text-[#252936]">
    <AppHeader
      title="商品与经营治理"
      description="规则、事实、素材和供应链证据统一版本化，并接入高风险发布审批。"
      userName={currentUser.display_name || currentUser.username}
      onLogout={onLogout}
    />
    <div className="mx-auto max-w-[1500px] px-5 py-6">
      <div className="flex flex-wrap items-start justify-between gap-4"><div><h1 className="text-[24px] font-semibold">商品与经营治理</h1><p className="mt-2 text-[13px] text-[#667085]">规则版本 → Listing 检查 → 创意资产 → 采购建议 → 新品门禁 → 人工发布审批</p></div><div className="rounded-[12px] border border-[#f3d49a] bg-[#fff9eb] px-4 py-3 text-[11px] text-[#805b12]">本页只生成证据、建议和审批请求，不直接发布 Listing、素材或采购单。</div></div>
      <div className="mt-5 grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-7">{cards.map(([label, value]) => <div key={String(label)} className="rounded-[14px] border border-[#e6e8ee] bg-white p-4"><p className="text-[10px] text-[#858b9c]">{label}</p><strong className="mt-2 block text-[22px]">{value}</strong></div>)}</div>
      <div className="mt-5 flex flex-wrap gap-2">{([['listing','Listing 合规'],['creative','创意与素材'],['procurement','采购建议'],['launch','新品门禁'],['quality','质量闭环']] as Array<[Tab,string]>).map(([key,label]) => <button key={key} type="button" onClick={() => setTab(key)} className={cn('rounded-full px-4 py-2 text-[12px]', tab === key ? 'bg-[#252936] text-white' : 'bg-white text-[#667085]')}>{label}</button>)}</div>
      {loading && <p className="py-20 text-center text-[13px] text-[#858b9c]">加载中…</p>}

      {!loading && tab === 'listing' && <div className="mt-5 grid gap-5 xl:grid-cols-2"><section className="rounded-[18px] border border-[#e6e8ee] bg-white p-5"><div className="flex items-center justify-between"><div><h2 className="text-[16px] font-semibold">平台规则版本</h2><p className="mt-1 text-[11px] text-[#858b9c]">按平台、站点、类目和版本固化；发布后数据库禁止篡改。</p></div>{canListing && <Button disabled={Boolean(busy)} onClick={() => void createRule()}>创建草稿</Button>}</div><div className="mt-4 space-y-3">{rules.map((item) => <div key={item.id} className="rounded-[12px] border p-3"><div className="flex justify-between"><strong className="text-[12px]">{item.platform} {item.marketplace} · {item.category}</strong><Pill value={item.status}/></div><p className="mt-2 text-[11px] text-[#667085]">v{item.version}</p><p className="mt-1 break-all text-[9px] text-[#98a2b3]">{item.content_digest}</p></div>)}</div>{manager && pendingRule && <Button className="mt-4" variant="outline" disabled={Boolean(busy)} onClick={() => void publishRule()}>主管审核并发布最新草稿</Button>}</section><section className="rounded-[18px] border border-[#e6e8ee] bg-white p-5"><div className="flex justify-between"><div><h2 className="text-[16px] font-semibold">Listing 检查结果</h2><p className="mt-1 text-[11px] text-[#858b9c]">输出位置、风险、规则、证据、建议和门禁级别。</p></div>{canListing && <Button disabled={Boolean(busy) || !publishedRule || !store} onClick={() => void runListingCheck()}>运行检查</Button>}</div><div className="mt-4 space-y-3">{checks.map((item) => <div key={item.id} className="rounded-[12px] border p-3"><div className="flex justify-between"><strong className="text-[12px]">{item.sku} · 规则 {item.rule_version}</strong><Pill value={item.gate_status}/></div><p className="mt-2 text-[10px] text-[#858b9c]">SKU 事实 {item.sku_fact_version} · {item.findings.length} 项发现</p>{item.findings.slice(0,4).map((finding,index) => <div key={`${finding.rule}-${index}`} className="mt-2 rounded-[9px] bg-[#f7f8fa] p-2 text-[10px]"><span className="font-medium">{finding.location} · {finding.rule}</span><p className="mt-1 text-[#667085]">{finding.suggestion}</p></div>)}<div className="mt-2"><TaskLink taskId={item.task_id}/></div></div>)}</div></section></div>}

      {!loading && tab === 'creative' && <div className="mt-5 grid gap-5 xl:grid-cols-2"><section className="rounded-[18px] border border-[#e6e8ee] bg-white p-5"><div className="flex justify-between"><div><h2 className="text-[16px] font-semibold">Creative Brief</h2><p className="mt-1 text-[11px] text-[#858b9c]">尺寸、语言、卖点、场景、必需素材和截止时间。</p></div>{canDesign && <Button disabled={Boolean(busy) || !store} onClick={() => void createBrief()}>创建 Brief</Button>}</div><div className="mt-4 space-y-3">{briefs.map((item) => <div key={item.id} className="rounded-[12px] border p-3"><div className="flex justify-between"><strong className="text-[12px]">{item.product_key} · {item.language}</strong><Pill value={item.status}/></div><p className="mt-2 text-[11px] text-[#667085]">{item.required_assets.join('、')}</p><TaskLink taskId={item.task_id}/></div>)}</div></section><section className="rounded-[18px] border border-[#e6e8ee] bg-white p-5"><div className="flex justify-between"><div><h2 className="text-[16px] font-semibold">不可变素材版本</h2><p className="mt-1 text-[11px] text-[#858b9c]">每次修改创建子版本，保留来源、参数、检查和审批人。</p></div>{canDesign && <Button disabled={Boolean(busy) || briefs.length === 0} onClick={() => void createAsset()}>登记 v1</Button>}</div>{manager && pendingAsset && <Button className="mt-4" variant="outline" disabled={Boolean(busy)} onClick={() => void reviewAsset()}>人工审核待审素材</Button>}<div className="mt-4 space-y-3">{assets.map((item) => <div key={item.id} className="rounded-[12px] border p-3"><div className="flex justify-between"><strong className="text-[12px]">{item.asset_key} · v{item.version}</strong><Pill value={item.status}/></div><p className="mt-2 text-[10px] text-[#667085]">{item.asset_type} · 人审 {item.required_human_approval ? '必须' : '可选'}</p><p className="mt-1 break-all text-[9px] text-[#98a2b3]">{item.file_digest}</p></div>)}</div></section></div>}

      {!loading && tab === 'procurement' && <section className="mt-5 rounded-[18px] border border-[#e6e8ee] bg-white p-5"><div className="flex flex-wrap justify-between gap-3"><div><h2 className="text-[16px] font-semibold">补货与采购建议</h2><p className="mt-1 text-[11px] text-[#858b9c]">销量、可售、在途、广告/促销、MOQ、交期、报价、质检和现金约束均固化在输入快照中。</p></div><div className="flex gap-2">{canProcure && <Button disabled={Boolean(busy) || !supplier} onClick={() => void createProcurement()}>生成建议</Button>}{manager && pendingRecommendation && <Button variant="outline" disabled={Boolean(busy)} onClick={() => void reviewProcurement()}>主管审核</Button>}</div></div><div className="mt-5 grid gap-3 lg:grid-cols-2">{recommendations.map((item) => <div key={item.id} className="rounded-[14px] border p-4"><div className="flex justify-between"><strong className="text-[13px]">{item.sku} · 建议 {item.recommended_quantity} 件</strong><Pill value={item.status}/></div><p className="mt-2 text-[12px]">预计落地成本 {item.estimated_landed_cost.toFixed(2)} · 交期 {item.lead_time_days} 天</p><code className="mt-3 block whitespace-pre-wrap rounded-[9px] bg-[#f7f8fa] p-2 text-[9px] text-[#667085]">{item.formula}</code><p className="mt-2 text-[10px] text-[#b54708]">{item.risk_reasons.join('、') || '未触发额外风险项'}</p><div className="mt-2"><TaskLink taskId={item.task_id}/></div></div>)}</div></section>}

      {!loading && tab === 'launch' && <section className="mt-5 rounded-[18px] border border-[#e6e8ee] bg-white p-5"><div className="flex flex-wrap justify-between gap-3"><div><h2 className="text-[16px] font-semibold">新品发布门禁</h2><p className="mt-1 text-[11px] text-[#858b9c]">绑定供应商、BOM、包装、认证、SKU 事实、Listing 检查、素材和采购建议版本。</p></div><div className="flex gap-2">{canListing && <Button disabled={Boolean(busy) || !passedCheck || !approvedAsset || !reviewedRecommendation} onClick={() => void evaluateLaunch()}>评估门禁</Button>}{canListing && readyGate && <Button variant="outline" disabled={Boolean(busy)} onClick={() => void submitLaunch()}>提交人工发布审批</Button>}</div></div><div className="mt-5 space-y-3">{gates.map((item) => <div key={item.id} className="rounded-[14px] border p-4"><div className="flex justify-between"><strong className="text-[13px]">{item.sku} · {item.launch_key}</strong><Pill value={item.status}/></div>{item.blockers.length > 0 && <div className="mt-3 rounded-[9px] bg-[#fff0ef] p-3 text-[10px] text-[#b42318]">{item.blockers.map((blocker) => <p key={`${blocker.code}-${blocker.detail}`}>{blocker.code}：{blocker.detail}</p>)}</div>}<p className="mt-2 break-all text-[9px] text-[#98a2b3]">证据 {item.evidence_digest}</p><div className="mt-3 flex gap-4"><TaskLink taskId={item.task_id}/>{item.approval_request_id && <a className="text-[11px] text-[#315ea8]" href="/enterprise/business-resources">审批 {item.approval_status || 'pending'}</a>}</div></div>)}</div></section>}

      {!loading && tab === 'quality' && <section className="mt-5 rounded-[18px] border border-[#e6e8ee] bg-white p-5"><h2 className="text-[16px] font-semibold">售后质量闭环</h2><p className="mt-1 text-[11px] text-[#858b9c]">破损和错发工单结案后，自动向采购、美工、Listing 三个岗位分别建单。</p><div className="mt-5 grid gap-3 lg:grid-cols-2">{qualityIssues.map((item) => <div key={item.id} className="rounded-[14px] border p-4"><div className="flex justify-between"><strong className="text-[13px]">{item.product_key} · {item.category}</strong><Pill value={item.status}/></div><p className="mt-3 text-[12px] text-[#505668]">{item.root_cause}</p><p className="mt-2 text-[10px] text-[#858b9c]">已创建 {item.task_ids.length} 个跨岗位任务 · 来源 {item.source_case_id}</p></div>)}</div>{qualityIssues.length === 0 && <p className="py-12 text-center text-[12px] text-[#858b9c]">暂无质量问题；破损或错发售后结案后会自动进入这里。</p>}</section>}
    </div>
  </div>;
}
