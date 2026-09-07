import { useCallback, useEffect, useState } from 'react';
import { api, TENANT_ID } from '../api/client';
import { getEnterpriseAuthSession } from '@/auth';
import { Button } from '@/components/ui/button';

type AuthorizationDecision = {
  id: string;
  subject_id: string;
  subject_type?: 'human' | 'service';
  role: string;
  department_id?: string;
  store_id?: string;
  resource_type?: string;
  object: string;
  action: string;
  effect: 'allow' | 'deny';
  reason: string;
  policy_version: string;
  request_id: string;
  occurred_at: string;
};

type PolicyRelease = {
  id: string;
  tenant_id: string;
  version: number;
  status: 'draft' | 'published' | 'superseded';
  policy_text: string;
  policy_digest: string;
  description: string;
  source_release_id?: string;
  publish_reason: string;
  created_at: string;
  published_at?: string;
};

function roleLabel(role: string) {
  if (role === 'tenant_admin') return '管理员';
  if (role === 'tenant_member') return '成员';
  if (role === 'operations_supervisor') return '运营主管';
  if (role === 'after_sales_specialist') return '跨境售后专员';
  if (role === 'listing_compliance_specialist') return 'Listing 合规专员';
  if (role === 'logistics_exception_specialist') return '物流异常专员';
  if (role === 'advertising_inspection_specialist') return '广告巡检专员';
  if (role === 'designer') return '美工设计';
  if (role === 'procurement_specialist') return '采购专员';
  return role;
}

export default function AuthorizationPage() {
  const [rows, setRows] = useState<AuthorizationDecision[]>([]);
  const [policies, setPolicies] = useState<PolicyRelease[]>([]);
  const [editing, setEditing] = useState<PolicyRelease | null>(null);
  const [policyText, setPolicyText] = useState('');
  const [description, setDescription] = useState('');
  const [releaseReason, setReleaseReason] = useState('');
  const [effect, setEffect] = useState<'all' | 'allow' | 'deny'>('all');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const tenantId = getEnterpriseAuthSession()?.user.tenant_id || TENANT_ID;

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const query = effect === 'all' ? '' : `?effect=${effect}`;
      const [decisions, policyReleases] = await Promise.all([
        api.get<AuthorizationDecision[]>(`/api/enterprise/authorization-decisions${query}`),
        api.get<PolicyRelease[]>(
          `/api/enterprise/authorization-policies?tenant_id=${encodeURIComponent(tenantId)}`,
        ),
      ]);
      setRows(decisions);
      setPolicies(policyReleases);
      const currentDraft = policyReleases.find((row) => row.status === 'draft');
      if (currentDraft && editing?.id !== currentDraft.id) {
        setEditing(currentDraft);
        setPolicyText(currentDraft.policy_text);
        setDescription(currentDraft.description);
      }
    } catch (loadError) {
      setRows([]);
      setError(loadError instanceof Error ? loadError.message : '权限审计加载失败');
    } finally {
      setLoading(false);
    }
  }, [editing?.id, effect, tenantId]);

  useEffect(() => {
    void load();
  }, [load]);

  const allowCount = rows.filter((row) => row.effect === 'allow').length;
  const denyCount = rows.filter((row) => row.effect === 'deny').length;

  const createDraft = async () => {
    setError('');
    try {
      const row = await api.post<PolicyRelease>('/api/enterprise/authorization-policies', {
        tenant_id: tenantId,
        description: '基于当前生效版本创建',
      });
      setEditing(row);
      setPolicyText(row.policy_text);
      setDescription(row.description);
      await load();
    } catch (actionError) {
      setError(actionError instanceof Error ? actionError.message : '策略草稿创建失败');
    }
  };

  const saveDraft = async () => {
    if (!editing || editing.status !== 'draft') return;
    setError('');
    try {
      const row = await api.put<PolicyRelease>(
        `/api/enterprise/authorization-policies/${editing.id}`,
        {
          tenant_id: tenantId,
          expected_digest: editing.policy_digest,
          policy_text: policyText,
          description,
        },
      );
      setEditing(row);
      setPolicyText(row.policy_text);
      await load();
    } catch (actionError) {
      setError(actionError instanceof Error ? actionError.message : '策略草稿保存失败');
    }
  };

  const publishDraft = async () => {
    if (!editing || editing.status !== 'draft' || releaseReason.trim().length < 3) return;
    setError('');
    try {
      await api.post(`/api/enterprise/authorization-policies/${editing.id}/publish`, {
        tenant_id: tenantId,
        reason: releaseReason.trim(),
      });
      setEditing(null);
      setReleaseReason('');
      await load();
    } catch (actionError) {
      setError(actionError instanceof Error ? actionError.message : '策略发布失败');
    }
  };

  const rollbackTo = async (row: PolicyRelease) => {
    if (releaseReason.trim().length < 3) {
      setError('回滚前请输入至少 3 个字符的变更原因');
      return;
    }
    setError('');
    try {
      await api.post(`/api/enterprise/authorization-policies/${row.id}/rollback`, {
        tenant_id: tenantId,
        reason: releaseReason.trim(),
      });
      setEditing(null);
      setReleaseReason('');
      await load();
    } catch (actionError) {
      setError(actionError instanceof Error ? actionError.message : '策略回滚失败');
    }
  };

  return (
    <section className="mx-auto flex w-full max-w-[1500px] flex-col gap-5 p-6">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-[#182036]">权限审计</h1>
          <p className="mt-1 text-sm text-[#6b7280]">
            查看 Casbin 对企业 API 的允许与拒绝记录，并用请求 ID 回溯具体调用。
          </p>
        </div>
        <Button variant="outline" onClick={() => void load()} disabled={loading}>
          {loading ? '刷新中…' : '刷新'}
        </Button>
      </header>

      <div className="grid gap-3 sm:grid-cols-3">
        <Metric label="当前记录" value={rows.length} tone="neutral" />
        <Metric label="允许" value={allowCount} tone="allow" />
        <Metric label="拒绝" value={denyCount} tone="deny" />
      </div>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.35fr)_minmax(360px,0.65fr)]">
        <div className="rounded-xl border border-[#e3e7f1] bg-white p-5 shadow-sm">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 className="font-semibold text-[#182036]">Casbin 策略发布</h2>
              <p className="mt-1 text-xs text-[#6b7280]">
                草稿保存采用摘要并发控制；发布后正文不可修改，只能新建版本或回滚。
              </p>
            </div>
            {!editing ? (
              <Button onClick={() => void createDraft()}>新建策略草稿</Button>
            ) : null}
          </div>
          {editing ? (
            <div className="mt-4 space-y-3">
              <div className="flex items-center justify-between text-xs text-[#6b7280]">
                <span>草稿 v{editing.version}</span>
                <span className="font-mono">{editing.policy_digest.slice(0, 16)}</span>
              </div>
              <input
                value={description}
                onChange={(event) => setDescription(event.target.value)}
                placeholder="版本说明"
                className="h-9 w-full rounded-lg border border-[#dfe4ee] px-3 text-sm outline-none focus:border-[#1a71ff]"
              />
              <textarea
                aria-label="Casbin 策略正文"
                value={policyText}
                onChange={(event) => setPolicyText(event.target.value)}
                spellCheck={false}
                className="min-h-[280px] w-full rounded-lg border border-[#dfe4ee] bg-[#0f172a] p-3 font-mono text-xs leading-5 text-[#e2e8f0] outline-none focus:border-[#1a71ff]"
              />
              <div className="flex flex-wrap gap-2">
                <Button variant="outline" onClick={() => void saveDraft()}>校验并保存</Button>
                <Button
                  onClick={() => void publishDraft()}
                  disabled={releaseReason.trim().length < 3}
                >
                  发布策略
                </Button>
              </div>
            </div>
          ) : (
            <div className="mt-4 rounded-lg bg-[#f7f9fc] p-4 text-sm text-[#6b7280]">
              当前没有待编辑草稿。新草稿会从正在生效的版本复制；首次使用则复制仓库基线策略。
            </div>
          )}
        </div>

        <div className="rounded-xl border border-[#e3e7f1] bg-white p-5 shadow-sm">
          <h2 className="font-semibold text-[#182036]">发布历史与回滚</h2>
          <input
            value={releaseReason}
            onChange={(event) => setReleaseReason(event.target.value)}
            placeholder="发布或回滚原因（至少 3 个字符）"
            className="mt-3 h-9 w-full rounded-lg border border-[#dfe4ee] px-3 text-sm outline-none focus:border-[#1a71ff]"
          />
          <div className="mt-3 max-h-[360px] space-y-2 overflow-y-auto">
            {policies.map((row) => (
              <div key={row.id} className="rounded-lg border border-[#edf0f5] p-3 text-xs">
                <div className="flex items-center justify-between gap-3">
                  <div className="font-medium text-[#374151]">v{row.version} · {row.description || '无说明'}</div>
                  <span className={`rounded-full px-2 py-0.5 ${
                    row.status === 'published'
                      ? 'bg-emerald-50 text-emerald-700'
                      : row.status === 'draft'
                        ? 'bg-amber-50 text-amber-700'
                        : 'bg-slate-100 text-slate-600'
                  }`}>
                    {row.status === 'published' ? '生效中' : row.status === 'draft' ? '草稿' : '历史版本'}
                  </span>
                </div>
                <div className="mt-1 font-mono text-[#8991a3]">{row.policy_digest.slice(0, 16)}</div>
                {row.status === 'superseded' ? (
                  <button
                    type="button"
                    onClick={() => void rollbackTo(row)}
                    className="mt-2 text-[#1a71ff] hover:underline"
                  >
                    回滚到此版本（生成新版本）
                  </button>
                ) : null}
              </div>
            ))}
            {!loading && policies.length === 0 ? (
              <div className="rounded-lg bg-[#f7f9fc] p-4 text-sm text-[#8991a3]">尚未发布数据库策略</div>
            ) : null}
          </div>
        </div>
      </div>

      <div className="flex items-center gap-2">
        {(['all', 'allow', 'deny'] as const).map((value) => (
          <button
            type="button"
            key={value}
            onClick={() => setEffect(value)}
            className={`rounded-lg px-3 py-1.5 text-sm transition-colors ${
              effect === value
                ? 'bg-[#1a71ff] text-white'
                : 'border border-[#dfe4ee] bg-white text-[#4b5563] hover:bg-[#f6f8fc]'
            }`}
          >
            {value === 'all' ? '全部' : value === 'allow' ? '允许' : '拒绝'}
          </button>
        ))}
      </div>

      {error ? (
        <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">{error}</div>
      ) : (
        <div className="overflow-hidden rounded-xl border border-[#e3e7f1] bg-white shadow-sm">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[1080px] text-left text-sm">
              <thead className="bg-[#f7f9fc] text-xs font-medium uppercase tracking-wide text-[#6b7280]">
                <tr>
                  <th className="px-4 py-3">时间</th>
                  <th className="px-4 py-3">结果</th>
                  <th className="px-4 py-3">角色 / 主体</th>
                  <th className="px-4 py-3">部门 / 店铺</th>
                  <th className="px-4 py-3">动作</th>
                  <th className="px-4 py-3">资源</th>
                  <th className="px-4 py-3">请求 ID</th>
                  <th className="px-4 py-3">策略版本</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#edf0f5]">
                {rows.map((row) => (
                  <tr key={row.id} className="text-[#374151] hover:bg-[#fafbfe]">
                    <td className="whitespace-nowrap px-4 py-3 text-xs">
                      {new Date(row.occurred_at).toLocaleString()}
                    </td>
                    <td className="px-4 py-3">
                      <span className={`rounded-full px-2 py-1 text-xs font-medium ${
                        row.effect === 'allow'
                          ? 'bg-emerald-50 text-emerald-700'
                          : 'bg-red-50 text-red-700'
                      }`}>
                        {row.effect === 'allow' ? '允许' : '拒绝'}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <div>{roleLabel(row.role)}</div>
                      <div className="mt-0.5 font-mono text-xs text-[#8991a3]">{row.subject_id}</div>
                    </td>
                    <td className="px-4 py-3 text-xs">
                      <div>{row.department_id || '—'}</div>
                      <div className="mt-0.5 font-mono text-[#8991a3]">{row.store_id || '全部店铺'}</div>
                    </td>
                    <td className="px-4 py-3 font-mono text-xs">{row.action}</td>
                    <td className="max-w-[360px] truncate px-4 py-3 font-mono text-xs" title={row.object}>
                      {row.object}
                    </td>
                    <td className="px-4 py-3 font-mono text-xs" title={row.reason}>{row.request_id}</td>
                    <td className="px-4 py-3 font-mono text-xs">{row.policy_version}</td>
                  </tr>
                ))}
                {!loading && rows.length === 0 ? (
                  <tr><td colSpan={8} className="px-4 py-10 text-center text-[#8991a3]">暂无授权记录</td></tr>
                ) : null}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </section>
  );
}

function Metric({ label, value, tone }: { label: string; value: number; tone: 'neutral' | 'allow' | 'deny' }) {
  const color = tone === 'allow' ? 'text-emerald-700' : tone === 'deny' ? 'text-red-700' : 'text-[#182036]';
  return (
    <div className="rounded-xl border border-[#e3e7f1] bg-white px-5 py-4 shadow-sm">
      <div className="text-xs text-[#8991a3]">{label}</div>
      <div className={`mt-1 text-2xl font-semibold ${color}`}>{value}</div>
    </div>
  );
}
