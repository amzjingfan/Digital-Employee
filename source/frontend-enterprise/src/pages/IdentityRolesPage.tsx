import { useCallback, useEffect, useMemo, useState } from 'react';
import { api } from '../api/client';
import { Button } from '@/components/ui/button';

type RoleMapping = {
  key: string;
  label: string;
  casdoor_groups: string[];
  description: string;
};

type IdentityAccount = {
  id: string;
  username: string;
  display_name?: string;
  account_role: 'admin' | 'member';
  business_role: string;
  business_role_label: string;
  authorization_source: string;
  identity_groups: string[];
  role_synced_at?: string;
};

type IdentityRolePayload = {
  group_claim: string;
  require_mapped_group: boolean;
  casdoor_management: {
    enabled: boolean;
    configured: boolean;
    sync_interval_seconds: number;
  };
  roles: RoleMapping[];
  accounts: IdentityAccount[];
};

export default function IdentityRolesPage() {
  const [payload, setPayload] = useState<IdentityRolePayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [syncing, setSyncing] = useState(false);
  const [syncMessage, setSyncMessage] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      setPayload(await api.get<IdentityRolePayload>('/api/enterprise/identity-role-mappings'));
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : '身份角色加载失败');
    } finally {
      setLoading(false);
    }
  }, []);

  const reconcileManagement = useCallback(async () => {
    setSyncing(true);
    setSyncMessage('');
    try {
      const result = await api.post<{
        status: string;
        scanned_count: number;
        changed_count: number;
      }>('/api/enterprise/identity-role-mappings/reconcile-management');
      setSyncMessage(`对账完成：扫描 ${result.scanned_count} 人，更新 ${result.changed_count} 条`);
      await load();
    } catch (syncError) {
      setSyncMessage(syncError instanceof Error ? syncError.message : 'Casdoor 对账失败');
    } finally {
      setSyncing(false);
    }
  }, [load]);

  useEffect(() => {
    void load();
  }, [load]);

  const syncedCount = useMemo(
    () => payload?.accounts.filter((account) => account.authorization_source.startsWith('oidc')).length ?? 0,
    [payload],
  );

  return (
    <section className="mx-auto flex w-full max-w-[1500px] flex-col gap-5 p-6">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-[#182036]">身份与角色</h1>
          <p className="mt-1 text-sm text-[#6b7280]">
            Casdoor 用户组在登录时映射为九骥 Joukir 业务角色，权限由服务端 Casbin 策略执行。
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" onClick={() => void reconcileManagement()} disabled={syncing || loading || !payload?.casdoor_management.configured}>
            {syncing ? '对账中…' : '立即对账'}
          </Button>
          <Button variant="outline" onClick={() => void load()} disabled={loading || syncing}>
            {loading ? '刷新中…' : '刷新'}
          </Button>
        </div>
      </header>

      {payload ? (
        <div className="flex flex-wrap items-center gap-3 rounded-xl border border-[#e3e7f1] bg-white px-5 py-4 text-sm shadow-sm">
          <span className="font-medium text-[#182036]">Casdoor Management Client</span>
          <span className={payload.casdoor_management.enabled && payload.casdoor_management.configured ? 'text-emerald-700' : 'text-amber-700'}>
            {payload.casdoor_management.enabled && payload.casdoor_management.configured ? '已启用 · 凭据完整' : payload.casdoor_management.enabled ? '已启用 · 配置不完整' : '未启用'}
          </span>
          <span className="text-xs text-[#8991a3]">周期 {Math.round(payload.casdoor_management.sync_interval_seconds / 60)} 分钟</span>
          {syncMessage ? <span className="text-xs text-[#536078]">{syncMessage}</span> : null}
        </div>
      ) : null}

      {error ? (
        <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">{error}</div>
      ) : payload ? (
        <>
          <div className="grid gap-3 sm:grid-cols-3">
            <Metric label="业务角色" value={payload.roles.length} />
            <Metric label="已同步 OIDC 账号" value={syncedCount} />
            <Metric label="未映射用户策略" value={payload.require_mapped_group ? '拒绝登录' : '普通成员'} />
          </div>

          <div className="rounded-xl border border-[#e3e7f1] bg-white p-5 shadow-sm">
            <div className="mb-4">
              <h2 className="font-semibold text-[#182036]">Casdoor 用户组映射</h2>
              <p className="mt-1 text-xs text-[#8991a3]">读取已验证 ID Token 的 {payload.group_claim} 声明；不同岗位组冲突时拒绝登录。</p>
            </div>
            <div className="grid gap-3 lg:grid-cols-2">
              {payload.roles.map((role) => (
                <article key={role.key} className="rounded-xl border border-[#edf0f5] bg-[#fafbfe] p-4">
                  <div className="flex items-center justify-between gap-3">
                    <strong className="text-sm text-[#182036]">{role.label}</strong>
                    <code className="text-[11px] text-[#6b7280]">{role.key}</code>
                  </div>
                  <p className="mt-2 text-xs leading-5 text-[#6b7280]">{role.description}</p>
                  <div className="mt-3 flex flex-wrap gap-2">
                    {role.casdoor_groups.map((group) => (
                      <code key={group} className="rounded-md bg-white px-2 py-1 text-[11px] text-[#1a71ff] ring-1 ring-[#dfe7fb]">{group}</code>
                    ))}
                    {!role.casdoor_groups.length ? <span className="text-xs text-amber-700">尚未配置用户组</span> : null}
                  </div>
                </article>
              ))}
            </div>
          </div>

          <div className="overflow-hidden rounded-xl border border-[#e3e7f1] bg-white shadow-sm">
            <div className="border-b border-[#edf0f5] px-5 py-4">
              <h2 className="font-semibold text-[#182036]">账号有效角色</h2>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[980px] text-left text-sm">
                <thead className="bg-[#f7f9fc] text-xs text-[#6b7280]">
                  <tr>
                    <th className="px-4 py-3">账号</th>
                    <th className="px-4 py-3">业务角色</th>
                    <th className="px-4 py-3">来源</th>
                    <th className="px-4 py-3">Casdoor 用户组</th>
                    <th className="px-4 py-3">最近同步</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#edf0f5]">
                  {payload.accounts.map((account) => (
                    <tr key={account.id} className="text-[#374151] hover:bg-[#fafbfe]">
                      <td className="px-4 py-3">
                        <div className="font-medium">{account.display_name || account.username}</div>
                        <div className="mt-0.5 text-xs text-[#8991a3]">{account.username}</div>
                      </td>
                      <td className="px-4 py-3">
                        <span className="rounded-full bg-blue-50 px-2 py-1 text-xs font-medium text-blue-700">{account.business_role_label}</span>
                      </td>
                      <td className="px-4 py-3 text-xs">{sourceLabel(account.authorization_source)}</td>
                      <td className="px-4 py-3">
                        <div className="flex max-w-[430px] flex-wrap gap-1.5">
                          {account.identity_groups.map((group) => <code key={group} className="text-[11px] text-[#6b7280]">{group}</code>)}
                          {!account.identity_groups.length ? <span className="text-xs text-[#a0a7b5]">—</span> : null}
                        </div>
                      </td>
                      <td className="whitespace-nowrap px-4 py-3 text-xs text-[#6b7280]">
                        {account.role_synced_at ? new Date(account.role_synced_at).toLocaleString() : '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      ) : null}
    </section>
  );
}

function Metric({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="rounded-xl border border-[#e3e7f1] bg-white px-5 py-4 shadow-sm">
      <div className="text-xs text-[#8991a3]">{label}</div>
      <div className="mt-1 text-2xl font-semibold text-[#182036]">{value}</div>
    </div>
  );
}

function sourceLabel(source: string) {
  if (source === 'oidc_admin') return 'Casdoor 管理员';
  if (source === 'oidc_groups') return 'Casdoor 用户组';
  return '本地账号';
}
