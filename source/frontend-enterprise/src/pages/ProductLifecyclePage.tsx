import { useCallback, useEffect, useMemo, useState } from 'react';

import { api, TENANT_ID, uploadCreativeAsset } from '@/api/client';
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
type CreativeBrief = { id: string; brief_key: string; product_key: string; language: string; required_assets: string[]; status: string; task_id: string; snapshot_digest?: string; due_at?: string | null };
type CreativeAsset = { id: string; asset_key: string; version: number; product_key: string; asset_type: string; file_reference?: string; file_digest: string; status: string; parent_version_id?: string | null; required_human_approval: boolean; checks: Record<string, unknown>; created_at: string };
type CreativeAssetUpload = { upload_id: string; filename: string; content_type: string; size: number; file_reference: string; file_digest: string };
type DesignQCFinding = { check_key: string; status: string; severity: string; rule: string; evidence: string; checker_version: string };
type DesignQCReport = { id: string; asset_version_id: string; overall_status: string; findings: DesignQCFinding[]; snapshot_digest: string; checker_version: string; created_at: string };
type CreativeEvidence = { id: string; evidence_type: string; source_ref: string; version: string; status: string; expires_at?: string | null; content_digest: string };
type CreativeDelivery = { id: string; brief_id: string; status: string; blockers: Array<{ code: string; detail: string }>; delivery_digest: string; created_at: string };
type CreativeGeneration = { id: string; brief_id: string; provider_key: string; status: string; external_request_id?: string | null; error_message?: string | null; created_at: string };
type ProcurementRecommendation = { id: string; recommendation_key: string; product_key: string; sku: string; recommended_quantity: number; estimated_landed_cost: number; lead_time_days: number; formula: string; risk_level: string; risk_reasons: string[]; status: string; task_id: string };
type LaunchGate = { id: string; launch_key: string; product_key: string; sku: string; status: string; blockers: Array<{ code: string; detail: string }>; evidence_digest: string; approval_request_id?: string | null; approval_status?: string | null; task_id: string; version: number };
type QualityIssue = { id: string; source_case_id: string; product_key: string; category: string; root_cause: string; task_ids: string[]; status: string; created_at: string };
type Tab = 'listing' | 'creative' | 'procurement' | 'launch' | 'quality';

const BASE = '/api/enterprise/work-tasks/product-lifecycle';
const ASSET_CHECK_KEYS = ['dimensions', 'clarity', 'text_safe_area', 'logo', 'brand_colors', 'factual_consistency', 'copyright'] as const;

type BriefForm = {
  productKey: string;
  language: string;
  width: string;
  height: string;
  sellingPoints: string;
  scenes: string;
  requiredAssets: string;
  constraints: string;
  factSnapshot: string;
  brandSnapshot: string;
  platformSpecSnapshot: string;
};

type AssetForm = {
  assetKey: string;
  assetType: CreativeAsset['asset_type'];
  fileReference: string;
  fileDigest: string;
  source: string;
  license: string;
};

const EMPTY_CHECKS = Object.fromEntries(ASSET_CHECK_KEYS.map((key) => [key, false])) as Record<string, boolean>;

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
  const [qcReports, setQcReports] = useState<DesignQCReport[]>([]);
  const [evidenceRecords, setEvidenceRecords] = useState<CreativeEvidence[]>([]);
  const [deliveries, setDeliveries] = useState<CreativeDelivery[]>([]);
  const [generations, setGenerations] = useState<CreativeGeneration[]>([]);
  const [recommendations, setRecommendations] = useState<ProcurementRecommendation[]>([]);
  const [gates, setGates] = useState<LaunchGate[]>([]);
  const [qualityIssues, setQualityIssues] = useState<QualityIssue[]>([]);
  const [productContext, setProductContext] = useState({ productKey: '', sku: '' });
  const [briefForm, setBriefForm] = useState<BriefForm>({
    productKey: '', language: 'en-US', width: '', height: '', sellingPoints: '', scenes: '', requiredAssets: '',
    constraints: '{\n  "background": "white",\n  "safe_area_percent": 5\n}',
    factSnapshot: '{\n  "source_ref": "",\n  "version": "",\n  "status": "verified",\n  "facts": {}\n}',
    brandSnapshot: '{\n  "source_ref": "",\n  "version": "",\n  "status": "verified",\n  "logo": {},\n  "colors": [],\n  "fonts": []\n}',
    platformSpecSnapshot: '{\n  "source_ref": "",\n  "version": "",\n  "status": "verified",\n  "market": "US",\n  "module": "main_image",\n  "width": 2000,\n  "height": 2000\n}',
  });
  const [assetForm, setAssetForm] = useState<AssetForm>({
    assetKey: '', assetType: 'main_image', fileReference: '', fileDigest: '', source: '', license: '',
  });
  const [selectedAssetFile, setSelectedAssetFile] = useState<File | null>(null);
  const [assetChecks, setAssetChecks] = useState<Record<string, boolean>>(EMPTY_CHECKS);
  const manager = currentUser.role === 'admin' || currentUser.business_role === 'operations_supervisor';
  const role = currentUser.business_role || '';
  const canListing = manager || role === 'listing_compliance_specialist';
  const canDesign = manager || role === 'designer';
  const canProcure = manager || role === 'procurement_specialist';
  const store = resources.find((item) => item.resource_type === 'store');
  const supplier = resources.find((item) => item.resource_type === 'supplier');
  const workflowProductKey = productContext.productKey.trim() || briefs[0]?.product_key || '';
  const workflowSku = productContext.sku.trim();
  const publishedRule = rules.find((item) => item.status === 'published');
  const pendingRule = rules.find((item) => item.status === 'draft');
  const approvedAsset = assets.find((item) => item.status === 'approved' && item.product_key === workflowProductKey);
  const pendingAsset = assets.find((item) => item.status === 'pending_review');
  const qcTarget = assets.find((item) => item.product_key === workflowProductKey) || assets[0];
  const reviewedRecommendation = recommendations.find((item) => item.status === 'reviewed' && item.product_key === workflowProductKey);
  const pendingRecommendation = recommendations.find((item) => item.status === 'draft');
  const passedCheck = checks.find((item) => item.gate_status !== 'block' && item.product_key === workflowProductKey && item.sku === workflowSku);
  const readyGate = gates.find((item) => item.status === 'ready');

  const loadAll = useCallback(async () => {
    const tenant = encodeURIComponent(currentUser.tenant_id || TENANT_ID);
    const [summary, businessResources, nextRules, nextChecks, nextBriefs, nextAssets, nextQcReports, nextEvidence, nextDeliveries, nextGenerations, nextRecommendations, nextGates, issues] = await Promise.all([
      api.get<Overview>(`${BASE}/overview?tenant_id=${tenant}`),
      api.get<Resource[]>(`/api/enterprise/business-resources?tenant_id=${tenant}`),
      api.get<RuleSet[]>(`${BASE}/listing-rules?tenant_id=${tenant}`),
      api.get<ListingCheck[]>(`${BASE}/listing-checks?tenant_id=${tenant}`),
      api.get<CreativeBrief[]>(`${BASE}/creative-briefs?tenant_id=${tenant}`),
      api.get<CreativeAsset[]>(`${BASE}/creative-assets?tenant_id=${tenant}`),
      api.get<DesignQCReport[]>(`${BASE}/creative-qc?tenant_id=${tenant}`),
      api.get<CreativeEvidence[]>(`${BASE}/creative-evidence?tenant_id=${tenant}`),
      api.get<CreativeDelivery[]>(`${BASE}/creative-deliveries?tenant_id=${tenant}`),
      api.get<CreativeGeneration[]>(`${BASE}/creative-generations?tenant_id=${tenant}`),
      api.get<ProcurementRecommendation[]>(`${BASE}/procurement-recommendations?tenant_id=${tenant}`),
      api.get<LaunchGate[]>(`${BASE}/launch-gates?tenant_id=${tenant}`),
      api.get<QualityIssue[]>(`${BASE}/quality-issues?tenant_id=${tenant}`),
    ]);
    setOverview(summary); setResources(businessResources); setRules(nextRules); setChecks(nextChecks); setBriefs(nextBriefs); setAssets(nextAssets); setQcReports(nextQcReports); setEvidenceRecords(nextEvidence); setDeliveries(nextDeliveries); setGenerations(nextGenerations); setRecommendations(nextRecommendations); setGates(nextGates); setQualityIssues(issues);
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
      tenant_id: currentUser.tenant_id, platform: 'Amazon', marketplace: 'US', category: 'Electronics', version: `draft-${Date.now()}`,
      rules: { banned_terms: ['cure', 'guaranteed results'], restricted_terms: [{ term: 'FDA approved', required_certification: 'FDA', gate: 'block' }], required_certifications: ['FCC'], required_labels: ['Made in China'], intellectual_property_terms: ['Apple AirTag'], optimization_terms: ['wireless'], max_title_chars: 180, required_content_fields: ['title', 'bullets', 'description'] },
      source_references: [{ source_id: 'amazon-electronics-style-guide', title: 'Amazon Electronics reviewed platform guide', url: 'https://sellercentral.amazon.com/help', retrieved_at: new Date().toISOString() }],
      effective_at: new Date(Date.now() - 3600000).toISOString(), expires_at: new Date(Date.now() + 90 * 86400000).toISOString(),
    }));
  }

  function publishRule() { if (!pendingRule) return Promise.resolve(); return run('审核发布规则', () => api.post(`${BASE}/listing-rules/${pendingRule.id}/publish`, { tenant_id: currentUser.tenant_id, expected_digest: pendingRule.content_digest, review_note: '已核对平台原始来源、适用站点、品类和有效期。' })); }
  function splitLines(value: string) { return value.split(/[\n,]/).map((item) => item.trim()).filter(Boolean); }
  function parseConstraints(value: string) {
    try { return JSON.parse(value || '{}') as Record<string, unknown>; }
    catch { notify.error('Brief 约束格式错误', { description: '请填写有效的 JSON 对象。' }); return null; }
  }
  function hasEvidenceMetadata(value: Record<string, unknown>) {
    return Object.keys(value).length === 0 || ['source_ref', 'version', 'status'].every((key) => String(value[key] || '').trim());
  }
  function createBrief() {
    if (!store) return Promise.resolve();
    const productKey = briefForm.productKey.trim() || productContext.productKey.trim();
    const width = Number(briefForm.width);
    const height = Number(briefForm.height);
    const sellingPoints = splitLines(briefForm.sellingPoints);
    const scenes = splitLines(briefForm.scenes);
    const requiredAssets = splitLines(briefForm.requiredAssets);
    const constraints = parseConstraints(briefForm.constraints);
    const factSnapshot = parseConstraints(briefForm.factSnapshot);
    const brandSnapshot = parseConstraints(briefForm.brandSnapshot);
    const platformSpecSnapshot = parseConstraints(briefForm.platformSpecSnapshot);
    if (!productKey || !Number.isInteger(width) || width <= 0 || !Number.isInteger(height) || height <= 0 || !briefForm.language.trim() || !sellingPoints.length || !scenes.length || !requiredAssets.length || !constraints || !factSnapshot || !brandSnapshot || !platformSpecSnapshot || !hasEvidenceMetadata(factSnapshot) || !hasEvidenceMetadata(brandSnapshot) || !hasEvidenceMetadata(platformSpecSnapshot)) {
      notify.error('请补齐 Brief 必填字段', { description: '产品标识、尺寸、卖点、场景、必需素材、约束以及快照的来源/版本/状态均不能为空。' });
      return Promise.resolve();
    }
    return run('创建创意 Brief', () => api.post(`${BASE}/creative-briefs`, {
      tenant_id: currentUser.tenant_id, brief_key: `BRIEF-${productKey}-${Date.now()}`, store_resource_id: store.id,
      product_key: productKey, language: briefForm.language.trim(),
      dimensions: { width, height, unit: 'px' },
      selling_points: sellingPoints, scenes, required_assets: requiredAssets, constraints,
      fact_snapshot: factSnapshot, brand_snapshot: brandSnapshot, platform_spec_snapshot: platformSpecSnapshot,
      due_at: new Date(Date.now() + 3 * 86400000).toISOString(),
    }));
  }
  function uploadAssetFile() {
    const brief = briefs.find((item) => item.product_key === workflowProductKey) || briefs[0];
    if (!brief || !selectedAssetFile) {
      notify.error('请先选择素材文件和目标 Brief');
      return Promise.resolve();
    }
    return run('上传并校验素材', async () => {
      const uploaded = await uploadCreativeAsset<CreativeAssetUpload>(currentUser.tenant_id, brief.id, selectedAssetFile);
      setAssetForm((value) => ({ ...value, fileReference: uploaded.file_reference, fileDigest: uploaded.file_digest }));
      setSelectedAssetFile(null);
    });
  }
  function createAsset() {
    const brief = briefs.find((item) => item.product_key === workflowProductKey) || briefs[0];
    if (!brief) return Promise.resolve();
    if (!assetForm.assetKey.trim() || !assetForm.fileReference.trim() || !assetForm.fileDigest.trim() || !assetForm.source.trim() || !assetForm.license.trim()) {
      notify.error('请补齐素材登记字段', { description: '素材键、文件引用、SHA-256 摘要、来源和授权信息均不能为空。' });
      return Promise.resolve();
    }
    return run('登记素材版本', () => api.post(`${BASE}/creative-assets`, {
      tenant_id: currentUser.tenant_id, asset_key: assetForm.assetKey.trim(), brief_id: brief.id, asset_type: assetForm.assetType,
      file_reference: assetForm.fileReference.trim(), file_digest: assetForm.fileDigest.trim(),
      provenance: { source: assetForm.source.trim(), license: assetForm.license.trim() },
      generation_parameters: {}, checks: assetChecks, contains_sensitive_claims: false,
    }));
  }
  function runAssetQC() {
    if (!qcTarget) return Promise.resolve();
    return run('运行设计 QC', () => api.post(`${BASE}/creative-assets/${qcTarget.id}/qc`, { tenant_id: currentUser.tenant_id, asset_version_id: qcTarget.id, checker_version: 'joukir-design-qc-v1' }));
  }
  function createDeliveryChecklist() {
    const brief = briefs.find((item) => item.product_key === workflowProductKey) || briefs[0];
    const selectedAssets = assets.filter((item) => item.product_key === workflowProductKey && item.status === 'approved');
    if (!brief || !selectedAssets.length) return Promise.resolve();
    return run('生成交付清单', () => api.post(`${BASE}/creative-deliveries/checklist`, { tenant_id: currentUser.tenant_id, brief_id: brief.id, asset_version_ids: selectedAssets.map((item) => item.id) }));
  }
  function submitGeneration() {
    const brief = briefs.find((item) => item.product_key === workflowProductKey) || briefs[0];
    if (!brief) return Promise.resolve();
    return run('提交生成任务', () => api.post(`${BASE}/creative-generations`, { tenant_id: currentUser.tenant_id, brief_id: brief.id, provider_key: 'http', idempotency_key: `creative-${brief.id}-${Date.now()}`, instructions: { output: 'production-candidate' } }));
  }
  function reviewAsset() { if (!pendingAsset) return Promise.resolve(); return run('人工审核素材', () => api.post(`${BASE}/creative-assets/${pendingAsset.id}/review`, { tenant_id: currentUser.tenant_id, decision: 'approved', note: '尺寸、清晰度、安全区、品牌、事实与版权证据均已人工核验。' })); }
  function runListingCheck() {
    if (!store || !publishedRule || !workflowProductKey || !workflowSku) { notify.error('请先填写商品标识和 SKU'); return Promise.resolve(); }
    return run('执行 Listing 检查', () => api.post(`${BASE}/listing-checks`, { tenant_id: currentUser.tenant_id, check_key: `CHECK-${Date.now()}`, store_resource_id: store.id, product_key: workflowProductKey, sku: workflowSku, language: 'en-US', rule_set_id: publishedRule.id, sku_fact_version: 'facts-v3', sku_facts: { material: 'ABS', dimensions: '10x8x3 cm', country_of_origin: 'China', certifications: ['FCC'] }, content: { title: 'Wireless compact controller', bullets: ['Made in China', 'ABS enclosure'], description: 'Wireless controller for home office workflows.', attributes: { battery_required: false }, keywords: ['wireless', 'controller'], image_text: ['Compact controller'], video_script: 'Demonstrate setup without unsupported claims.', declared_facts: { material: 'ABS', dimensions: '10x8x3 cm', country_of_origin: 'China' }, translations: { 'de-DE': { declared_facts: { material: 'ABS', dimensions: '10x8x3 cm', country_of_origin: 'China' } } } }, asset_version_ids: approvedAsset ? [approvedAsset.id] : [] }));
  }
  function createProcurement() {
    if (!supplier || !workflowProductKey || !workflowSku) { notify.error('请先填写商品标识和 SKU'); return Promise.resolve(); }
    return run('生成采购建议', () => api.post(`${BASE}/procurement-recommendations`, { tenant_id: currentUser.tenant_id, recommendation_key: `PROC-${Date.now()}`, supplier_resource_id: supplier.id, product_key: workflowProductKey, sku: workflowSku, forecast_daily_sales: 10, planning_horizon_days: 30, available_units: 80, inbound_units: 40, safety_stock_units: 50, promotion_units: 30, advertising_lift_units: 20, moq: 100, lead_time_days: 15, quote_unit_cost: 8, freight_unit_cost: 1, duty_unit_cost: 0.5, quote_observed_at: new Date().toISOString(), qc_failure_rate: 0.01, cash_budget: 5000, currency: 'USD' }));
  }
  function reviewProcurement() { if (!pendingRecommendation) return Promise.resolve(); return run('审核采购建议', () => api.post(`${BASE}/procurement-recommendations/${pendingRecommendation.id}/review`, { tenant_id: currentUser.tenant_id, decision: 'reviewed', note: '销量、库存、MOQ、交期、报价、质检与现金约束已核验；不创建采购单。' })); }
  function evaluateLaunch() { if (!store || !supplier || !passedCheck || !approvedAsset || !reviewedRecommendation) return Promise.resolve(); return run('评估新品门禁', () => api.post(`${BASE}/launch-gates`, { tenant_id: currentUser.tenant_id, launch_key: `LAUNCH-${Date.now()}`, store_resource_id: store.id, supplier_resource_id: supplier.id, product_key: workflowProductKey, sku: workflowSku, sku_fact_version: 'facts-v3', bom_version: 'bom-v5', packaging_version: 'pack-v2', certification_ids: ['FCC'], listing_check_id: passedCheck.id, asset_version_ids: [approvedAsset.id], procurement_recommendation_id: reviewedRecommendation.id, supplier_lead_time_confirmed: true })); }
  function submitLaunch() { if (!readyGate) return Promise.resolve(); return run('提交发布审批', () => api.post(`${BASE}/launch-gates/${readyGate.id}/submit`, { tenant_id: currentUser.tenant_id, expected_version: readyGate.version, listing_id: `ASIN-DRAFT-${Date.now()}`, marketplace: 'US', product_type: 'Electronics', attributes: { sku: workflowSku, material: 'ABS' }, summary: `发布已审核 ${workflowSku} Listing；必须通过双人审批后由受控连接器执行` })); }

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
      <section className="mt-5 rounded-[16px] border border-[#dfe5f0] bg-white p-4">
        <div className="flex flex-wrap items-center justify-between gap-3"><div><h2 className="text-[14px] font-semibold">当前商品上下文</h2><p className="mt-1 text-[11px] text-[#858b9c]">后续 Listing、采购和新品门禁都会使用这里的商品标识与 SKU，不再使用演示商品。</p></div><span className="text-[10px] text-[#858b9c]">店铺：{store?.name || '暂无可用店铺'}</span></div>
        <div className="mt-3 grid gap-3 md:grid-cols-2"><label className="text-[11px] text-[#667085]">产品标识<input value={productContext.productKey} onChange={(event) => setProductContext((value) => ({ ...value, productKey: event.target.value }))} placeholder="例如：P-USB-C-HUB-001" className="mt-1 w-full rounded-[9px] border border-[#dfe3ea] px-3 py-2 text-[12px] text-[#252936] outline-none focus:border-[#315ea8]" /></label><label className="text-[11px] text-[#667085]">SKU<input value={productContext.sku} onChange={(event) => setProductContext((value) => ({ ...value, sku: event.target.value }))} placeholder="例如：US-HUB-001-BLK" className="mt-1 w-full rounded-[9px] border border-[#dfe3ea] px-3 py-2 text-[12px] text-[#252936] outline-none focus:border-[#315ea8]" /></label></div>
      </section>
      <div className="mt-5 grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-7">{cards.map(([label, value]) => <div key={String(label)} className="rounded-[14px] border border-[#e6e8ee] bg-white p-4"><p className="text-[10px] text-[#858b9c]">{label}</p><strong className="mt-2 block text-[22px]">{value}</strong></div>)}</div>
      <div className="mt-5 flex flex-wrap gap-2">{([['listing','Listing 合规'],['creative','创意与素材'],['procurement','采购建议'],['launch','新品门禁'],['quality','质量闭环']] as Array<[Tab,string]>).map(([key,label]) => <button key={key} type="button" onClick={() => setTab(key)} className={cn('rounded-full px-4 py-2 text-[12px]', tab === key ? 'bg-[#252936] text-white' : 'bg-white text-[#667085]')}>{label}</button>)}</div>
      {loading && <p className="py-20 text-center text-[13px] text-[#858b9c]">加载中…</p>}

      {!loading && tab === 'listing' && <div className="mt-5 grid gap-5 xl:grid-cols-2"><section className="rounded-[18px] border border-[#e6e8ee] bg-white p-5"><div className="flex items-center justify-between"><div><h2 className="text-[16px] font-semibold">平台规则版本</h2><p className="mt-1 text-[11px] text-[#858b9c]">按平台、站点、类目和版本固化；发布后数据库禁止篡改。</p></div>{canListing && <Button disabled={Boolean(busy)} onClick={() => void createRule()}>创建草稿</Button>}</div><div className="mt-4 space-y-3">{rules.map((item) => <div key={item.id} className="rounded-[12px] border p-3"><div className="flex justify-between"><strong className="text-[12px]">{item.platform} {item.marketplace} · {item.category}</strong><Pill value={item.status}/></div><p className="mt-2 text-[11px] text-[#667085]">v{item.version}</p><p className="mt-1 break-all text-[9px] text-[#98a2b3]">{item.content_digest}</p></div>)}</div>{manager && pendingRule && <Button className="mt-4" variant="outline" disabled={Boolean(busy)} onClick={() => void publishRule()}>主管审核并发布最新草稿</Button>}</section><section className="rounded-[18px] border border-[#e6e8ee] bg-white p-5"><div className="flex justify-between"><div><h2 className="text-[16px] font-semibold">Listing 检查结果</h2><p className="mt-1 text-[11px] text-[#858b9c]">输出位置、风险、规则、证据、建议和门禁级别。</p></div>{canListing && <Button disabled={Boolean(busy) || !publishedRule || !store} onClick={() => void runListingCheck()}>运行检查</Button>}</div><div className="mt-4 space-y-3">{checks.map((item) => <div key={item.id} className="rounded-[12px] border p-3"><div className="flex justify-between"><strong className="text-[12px]">{item.sku} · 规则 {item.rule_version}</strong><Pill value={item.gate_status}/></div><p className="mt-2 text-[10px] text-[#858b9c]">SKU 事实 {item.sku_fact_version} · {item.findings.length} 项发现</p>{item.findings.slice(0,4).map((finding,index) => <div key={`${finding.rule}-${index}`} className="mt-2 rounded-[9px] bg-[#f7f8fa] p-2 text-[10px]"><span className="font-medium">{finding.location} · {finding.rule}</span><p className="mt-1 text-[#667085]">{finding.suggestion}</p></div>)}<div className="mt-2"><TaskLink taskId={item.task_id}/></div></div>)}</div></section></div>}

      {!loading && tab === 'creative' && <div className="mt-5 grid gap-5 xl:grid-cols-2">
        <section className="rounded-[18px] border border-[#e6e8ee] bg-white p-5">
          <div className="flex justify-between gap-3"><div><h2 className="text-[16px] font-semibold">Creative Brief</h2><p className="mt-1 text-[11px] text-[#858b9c]">把真实商品需求固化为可执行的尺寸、语言、卖点、场景和必需素材。</p></div>{canDesign && <Button disabled={Boolean(busy) || !store} onClick={() => void createBrief()}>创建 Brief</Button>}</div>
          <div className="mt-4 grid gap-3 md:grid-cols-2">
            <label className="text-[11px] text-[#667085]">产品标识<input value={briefForm.productKey} onChange={(event) => setBriefForm((value) => ({ ...value, productKey: event.target.value }))} placeholder="必填；可使用上方商品上下文" className="mt-1 w-full rounded-[9px] border border-[#dfe3ea] px-3 py-2 text-[12px]" /></label>
            <label className="text-[11px] text-[#667085]">语言<input value={briefForm.language} onChange={(event) => setBriefForm((value) => ({ ...value, language: event.target.value }))} placeholder="en-US" className="mt-1 w-full rounded-[9px] border border-[#dfe3ea] px-3 py-2 text-[12px]" /></label>
            <label className="text-[11px] text-[#667085]">宽度（px）<input value={briefForm.width} onChange={(event) => setBriefForm((value) => ({ ...value, width: event.target.value }))} inputMode="numeric" placeholder="例如：2000" className="mt-1 w-full rounded-[9px] border border-[#dfe3ea] px-3 py-2 text-[12px]" /></label>
            <label className="text-[11px] text-[#667085]">高度（px）<input value={briefForm.height} onChange={(event) => setBriefForm((value) => ({ ...value, height: event.target.value }))} inputMode="numeric" placeholder="例如：2000" className="mt-1 w-full rounded-[9px] border border-[#dfe3ea] px-3 py-2 text-[12px]" /></label>
            <label className="text-[11px] text-[#667085]">卖点（每行一个）<textarea value={briefForm.sellingPoints} onChange={(event) => setBriefForm((value) => ({ ...value, sellingPoints: event.target.value }))} placeholder="轻量化\n可折叠" className="mt-1 min-h-[70px] w-full rounded-[9px] border border-[#dfe3ea] px-3 py-2 text-[12px]" /></label>
            <label className="text-[11px] text-[#667085]">场景（每行一个）<textarea value={briefForm.scenes} onChange={(event) => setBriefForm((value) => ({ ...value, scenes: event.target.value }))} placeholder="白底主图\n桌面使用" className="mt-1 min-h-[70px] w-full rounded-[9px] border border-[#dfe3ea] px-3 py-2 text-[12px]" /></label>
            <label className="text-[11px] text-[#667085] md:col-span-2">必需素材（每行一个）<input value={briefForm.requiredAssets} onChange={(event) => setBriefForm((value) => ({ ...value, requiredAssets: event.target.value }))} placeholder="main_image, secondary_image, a_plus" className="mt-1 w-full rounded-[9px] border border-[#dfe3ea] px-3 py-2 text-[12px]" /></label>
            <label className="text-[11px] text-[#667085] md:col-span-2">约束 JSON<textarea value={briefForm.constraints} onChange={(event) => setBriefForm((value) => ({ ...value, constraints: event.target.value }))} className="mt-1 min-h-[86px] w-full rounded-[9px] border border-[#dfe3ea] px-3 py-2 font-mono text-[11px]" /></label>
            <label className="text-[11px] text-[#667085] md:col-span-2">商品事实快照 JSON<textarea value={briefForm.factSnapshot} onChange={(event) => setBriefForm((value) => ({ ...value, factSnapshot: event.target.value }))} className="mt-1 min-h-[96px] w-full rounded-[9px] border border-[#dfe3ea] px-3 py-2 font-mono text-[11px]" /></label>
            <label className="text-[11px] text-[#667085] md:col-span-2">品牌规范快照 JSON<textarea value={briefForm.brandSnapshot} onChange={(event) => setBriefForm((value) => ({ ...value, brandSnapshot: event.target.value }))} className="mt-1 min-h-[96px] w-full rounded-[9px] border border-[#dfe3ea] px-3 py-2 font-mono text-[11px]" /></label>
            <label className="text-[11px] text-[#667085] md:col-span-2">平台规格快照 JSON<textarea value={briefForm.platformSpecSnapshot} onChange={(event) => setBriefForm((value) => ({ ...value, platformSpecSnapshot: event.target.value }))} className="mt-1 min-h-[96px] w-full rounded-[9px] border border-[#dfe3ea] px-3 py-2 font-mono text-[11px]" /></label>
          </div>
          <div className="mt-5 space-y-3">{briefs.map((item) => <div key={item.id} className="rounded-[12px] border p-3"><div className="flex justify-between"><strong className="text-[12px]">{item.product_key} · {item.language}</strong><Pill value={item.status}/></div><p className="mt-2 text-[11px] text-[#667085]">必需素材：{item.required_assets.join('、')}</p>{item.snapshot_digest && <p className="mt-1 break-all text-[9px] text-[#98a2b3]">事实/品牌/规格快照：{item.snapshot_digest}</p>}<TaskLink taskId={item.task_id}/></div>)}</div>
        </section>
        <section className="rounded-[18px] border border-[#e6e8ee] bg-white p-5">
          <div className="flex flex-wrap justify-between gap-3"><div><h2 className="text-[16px] font-semibold">不可变素材版本</h2><p className="mt-1 text-[11px] text-[#858b9c]">先在对象存储或设计工具中准备文件，再登记真实引用、摘要、来源和授权；服务端会按店铺范围校验。</p></div><div className="flex gap-2">{canDesign && <Button disabled={Boolean(busy) || briefs.length === 0} onClick={() => void createAsset()}>登记素材版本</Button>}{canDesign && <Button variant="outline" disabled={Boolean(busy) || !qcTarget} onClick={() => void runAssetQC()}>运行服务端 QC</Button>}</div></div>
          <div className="mt-4 grid gap-3">
            <label className="text-[11px] text-[#667085]">素材键<input value={assetForm.assetKey} onChange={(event) => setAssetForm((value) => ({ ...value, assetKey: event.target.value }))} placeholder="例如：P-001-MAIN" className="mt-1 w-full rounded-[9px] border border-[#dfe3ea] px-3 py-2 text-[12px]" /></label>
            <label className="text-[11px] text-[#667085]">文件类型<select value={assetForm.assetType} onChange={(event) => setAssetForm((value) => ({ ...value, assetType: event.target.value as CreativeAsset['asset_type'] }))} className="mt-1 w-full rounded-[9px] border border-[#dfe3ea] bg-white px-3 py-2 text-[12px]"><option value="main_image">主图</option><option value="secondary_image">辅图</option><option value="a_plus">A+ 模块</option><option value="brand_story">品牌故事</option><option value="video">视频</option><option value="ad_creative">广告素材</option><option value="packaging">包装</option></select></label>
            <div className="rounded-[10px] border border-dashed border-[#b9c6dd] bg-[#f8faff] p-3"><p className="text-[11px] font-medium text-[#315ea8]">受控上传</p><p className="mt-1 text-[10px] text-[#667085]">上传后由服务端保存文件并重新计算 SHA-256；不要手工修改引用和摘要。</p><div className="mt-2 flex flex-wrap items-center gap-2"><input type="file" onChange={(event) => setSelectedAssetFile(event.target.files?.[0] || null)} className="max-w-full text-[11px]" /><Button type="button" variant="outline" disabled={Boolean(busy) || !selectedAssetFile || briefs.length === 0} onClick={() => void uploadAssetFile()}>上传并校验</Button></div>{assetForm.fileReference && <p className="mt-2 break-all text-[10px] text-[#667085]">引用：{assetForm.fileReference} · {assetForm.fileDigest}</p>}</div>
            <div className="grid gap-3 md:grid-cols-2"><label className="text-[11px] text-[#667085]">来源<input value={assetForm.source} onChange={(event) => setAssetForm((value) => ({ ...value, source: event.target.value }))} placeholder="摄影原图 / 授权素材 / AI 编辑" className="mt-1 w-full rounded-[9px] border border-[#dfe3ea] px-3 py-2 text-[12px]" /></label><label className="text-[11px] text-[#667085]">授权<input value={assetForm.license} onChange={(event) => setAssetForm((value) => ({ ...value, license: event.target.value }))} placeholder="tenant-owned / supplier-license" className="mt-1 w-full rounded-[9px] border border-[#dfe3ea] px-3 py-2 text-[12px]" /></label></div>
            <div><p className="text-[11px] text-[#667085]">已完成的质检项（未勾选会进入 draft，不能直接审核通过）</p><div className="mt-2 grid grid-cols-2 gap-2">{ASSET_CHECK_KEYS.map((key) => <label key={key} className="flex items-center gap-2 rounded-[8px] bg-[#f7f8fa] px-2 py-2 text-[10px] text-[#667085]"><input type="checkbox" checked={assetChecks[key] === true} onChange={(event) => setAssetChecks((value) => ({ ...value, [key]: event.target.checked }))} />{key}</label>)}</div></div>
          </div>
          {manager && pendingAsset && <Button className="mt-4" variant="outline" disabled={Boolean(busy)} onClick={() => void reviewAsset()}>人工审核待审素材</Button>}
          <div className="mt-4 space-y-3">{assets.map((item) => { const report = qcReports.find((candidate) => candidate.asset_version_id === item.id); return <div key={item.id} className="rounded-[12px] border p-3"><div className="flex justify-between"><strong className="text-[12px]">{item.asset_key} · v{item.version}</strong><div className="flex gap-2"><Pill value={item.status}/>{report && <Pill value={report.overall_status}/>}</div></div><p className="mt-2 text-[10px] text-[#667085]">{item.asset_type} · 人审 {item.required_human_approval ? '必须' : '可选'}</p><p className="mt-1 break-all text-[9px] text-[#98a2b3]">{item.file_reference || '未提供文件引用'} · {item.file_digest}</p>{report && <div className="mt-2 rounded-[9px] bg-[#f7f8fa] p-2 text-[10px] text-[#667085]"><p>QC {report.checker_version} · {report.findings.filter((finding) => finding.status !== 'pass' && finding.status !== 'not_applicable').length} 项待处理发现</p>{report.findings.filter((finding) => finding.status !== 'pass' && finding.status !== 'not_applicable').slice(0, 3).map((finding) => <p key={finding.check_key} className="mt-1"><span className="font-medium">{finding.check_key} · {finding.status}</span>：{finding.evidence}</p>)}</div>}</div>; })}</div>
        </section>
        <section className="rounded-[18px] border border-[#e6e8ee] bg-white p-5 xl:col-span-2"><div className="flex flex-wrap items-center justify-between gap-3"><div><h2 className="text-[16px] font-semibold">生产证据、交付与生成</h2><p className="mt-1 text-[11px] text-[#858b9c]">独立证据过期会自动阻断生成与交付；生成供应商返回的结果仍需重新上传、QC 和人工审核。</p></div><div className="flex gap-2">{canDesign && <Button variant="outline" disabled={Boolean(busy) || !approvedAsset} onClick={() => void createDeliveryChecklist()}>生成交付清单</Button>}{canDesign && <Button variant="outline" disabled={Boolean(busy) || !briefs.length} onClick={() => void submitGeneration()}>提交生成任务</Button>}</div></div><div className="mt-4 grid gap-3 md:grid-cols-3"><div className="rounded-[10px] bg-[#f7f8fa] p-3"><p className="text-[10px] font-medium">独立证据</p>{evidenceRecords.slice(0, 4).map((item) => <p key={item.id} className="mt-2 text-[10px] text-[#667085]">{item.evidence_type} · v{item.version} · <Pill value={item.status}/></p>)}{evidenceRecords.length === 0 && <p className="mt-2 text-[10px] text-[#858b9c]">等待证据同步</p>}</div><div className="rounded-[10px] bg-[#f7f8fa] p-3"><p className="text-[10px] font-medium">交付清单</p>{deliveries.slice(0, 3).map((item) => <p key={item.id} className="mt-2 text-[10px] text-[#667085]">{item.brief_id} · <Pill value={item.status}/>{item.blockers.length ? ` · 阻断 ${item.blockers.length}` : ''}</p>)}{deliveries.length === 0 && <p className="mt-2 text-[10px] text-[#858b9c]">尚未生成</p>}</div><div className="rounded-[10px] bg-[#f7f8fa] p-3"><p className="text-[10px] font-medium">生成供应商</p>{generations.slice(0, 3).map((item) => <p key={item.id} className="mt-2 text-[10px] text-[#667085]">{item.provider_key} · <Pill value={item.status}/>{item.error_message ? ` · ${item.error_message}` : ''}</p>)}{generations.length === 0 && <p className="mt-2 text-[10px] text-[#858b9c]">尚未提交</p>}</div></div></section>
      </div>}

      {!loading && tab === 'procurement' && <section className="mt-5 rounded-[18px] border border-[#e6e8ee] bg-white p-5"><div className="flex flex-wrap justify-between gap-3"><div><h2 className="text-[16px] font-semibold">补货与采购建议</h2><p className="mt-1 text-[11px] text-[#858b9c]">销量、可售、在途、广告/促销、MOQ、交期、报价、质检和现金约束均固化在输入快照中。</p></div><div className="flex gap-2">{canProcure && <Button disabled={Boolean(busy) || !supplier} onClick={() => void createProcurement()}>生成建议</Button>}{manager && pendingRecommendation && <Button variant="outline" disabled={Boolean(busy)} onClick={() => void reviewProcurement()}>主管审核</Button>}</div></div><div className="mt-5 grid gap-3 lg:grid-cols-2">{recommendations.map((item) => <div key={item.id} className="rounded-[14px] border p-4"><div className="flex justify-between"><strong className="text-[13px]">{item.sku} · 建议 {item.recommended_quantity} 件</strong><Pill value={item.status}/></div><p className="mt-2 text-[12px]">预计落地成本 {item.estimated_landed_cost.toFixed(2)} · 交期 {item.lead_time_days} 天</p><code className="mt-3 block whitespace-pre-wrap rounded-[9px] bg-[#f7f8fa] p-2 text-[9px] text-[#667085]">{item.formula}</code><p className="mt-2 text-[10px] text-[#b54708]">{item.risk_reasons.join('、') || '未触发额外风险项'}</p><div className="mt-2"><TaskLink taskId={item.task_id}/></div></div>)}</div></section>}

      {!loading && tab === 'launch' && <section className="mt-5 rounded-[18px] border border-[#e6e8ee] bg-white p-5"><div className="flex flex-wrap justify-between gap-3"><div><h2 className="text-[16px] font-semibold">新品发布门禁</h2><p className="mt-1 text-[11px] text-[#858b9c]">绑定供应商、BOM、包装、认证、SKU 事实、Listing 检查、素材和采购建议版本。</p></div><div className="flex gap-2">{canListing && <Button disabled={Boolean(busy) || !passedCheck || !approvedAsset || !reviewedRecommendation} onClick={() => void evaluateLaunch()}>评估门禁</Button>}{canListing && readyGate && <Button variant="outline" disabled={Boolean(busy)} onClick={() => void submitLaunch()}>提交人工发布审批</Button>}</div></div><div className="mt-5 space-y-3">{gates.map((item) => <div key={item.id} className="rounded-[14px] border p-4"><div className="flex justify-between"><strong className="text-[13px]">{item.sku} · {item.launch_key}</strong><Pill value={item.status}/></div>{item.blockers.length > 0 && <div className="mt-3 rounded-[9px] bg-[#fff0ef] p-3 text-[10px] text-[#b42318]">{item.blockers.map((blocker) => <p key={`${blocker.code}-${blocker.detail}`}>{blocker.code}：{blocker.detail}</p>)}</div>}<p className="mt-2 break-all text-[9px] text-[#98a2b3]">证据 {item.evidence_digest}</p><div className="mt-3 flex gap-4"><TaskLink taskId={item.task_id}/>{item.approval_request_id && <a className="text-[11px] text-[#315ea8]" href="/enterprise/business-resources">审批 {item.approval_status || 'pending'}</a>}</div></div>)}</div></section>}

      {!loading && tab === 'quality' && <section className="mt-5 rounded-[18px] border border-[#e6e8ee] bg-white p-5"><h2 className="text-[16px] font-semibold">售后质量闭环</h2><p className="mt-1 text-[11px] text-[#858b9c]">破损和错发工单结案后，自动向采购、美工、Listing 三个岗位分别建单。</p><div className="mt-5 grid gap-3 lg:grid-cols-2">{qualityIssues.map((item) => <div key={item.id} className="rounded-[14px] border p-4"><div className="flex justify-between"><strong className="text-[13px]">{item.product_key} · {item.category}</strong><Pill value={item.status}/></div><p className="mt-3 text-[12px] text-[#505668]">{item.root_cause}</p><p className="mt-2 text-[10px] text-[#858b9c]">已创建 {item.task_ids.length} 个跨岗位任务 · 来源 {item.source_case_id}</p></div>)}</div>{qualityIssues.length === 0 && <p className="py-12 text-center text-[12px] text-[#858b9c]">暂无质量问题；破损或错发售后结案后会自动进入这里。</p>}</section>}
    </div>
  </div>;
}
