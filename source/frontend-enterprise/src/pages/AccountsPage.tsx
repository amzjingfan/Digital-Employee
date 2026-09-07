import { useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { LogOut, MailPlus, ShieldCheck, User, UserRoundCheck, UserRoundX } from 'lucide-react';

import AppHeader from '@/components/AppHeader';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import { DataTable, type DataTableColumn } from '@/components/DataTable';
import { Paginator } from '@/components/Paginator';
import {
  Dialog,
  DialogContent,
  DialogTitle,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
  Input,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui';
import { Button as UIButton } from '@/components/ui/button';
import { notify } from '@/components/ui/app-toast';
import { cn } from '@/lib/utils';
import { MENU_CONTENT_CLASS, MENU_ITEM_CLASS, MENU_ITEM_DANGER_CLASS, MOBILE_CARD_CLASS, formatDateTime } from '@/lib/enterprise-ui';

import { api, TENANT_ID } from '../api/client';
import IconAccounts from '../assets/icons/sys-accounts.svg?react';
import IconAdd from '../assets/icons/add.svg?react';
import IconClear from '../assets/icons/field-clear.svg?react';
import IconEdit from '../assets/icons/edit.svg?react';
import IconMore from '../assets/icons/more.svg?react';
import IconRefresh from '../assets/icons/refresh.svg?react';
import IconSearch from '../assets/icons/search.svg?react';
import IconTrash from '../assets/icons/trash.svg?react';
import type { EnterpriseAuthUser } from '../auth';
import { useClientPagination } from '../hooks/useClientPagination';
import { StatusBadge } from './scheduled-tasks/StatusBadge';

type EmployeeAccount = {
  id: string;
  tenant_id: string;
  username: string;
  display_name?: string;
  role: 'admin' | 'member';
  business_role?: string;
  authorization_source?: string;
  source?: string;
  status: 'active' | 'suspended';
  session_version: number;
  identity_sync_status?: string;
  created_at?: string;
  updated_at?: string;
};

type UserInvitation = {
  id: string;
  tenant_id: string;
  username: string;
  display_name?: string;
  role: string;
  business_role: string;
  auth_source: 'local' | 'oidc';
  status: 'pending' | 'accepted' | 'cancelled' | 'expired';
  expires_at: string;
  created_at: string;
};

type UserInvitationCreated = UserInvitation & {
  invite_token: string;
  accept_path: string;
};

type LifecycleEvent = {
  id: string;
  event_type: string;
  subject_ref: string;
  outcome: 'allowed' | 'denied' | 'degraded';
  reason: string;
  occurred_at: string;
};

type Preferences = {
  user_locale?: 'zh-CN' | 'en';
  user_timezone?: string;
  tenant_default_locale: 'zh-CN' | 'en';
  tenant_default_timezone: string;
  tenant_default_currency: string;
  effective_locale: 'zh-CN' | 'en';
  effective_timezone: string;
};

type InviteDraft = {
  username: string;
  displayName: string;
  role: 'admin' | 'member';
  businessRole: string;
  authSource: 'local' | 'oidc';
};

type LifecycleTarget = {
  account: EmployeeAccount;
  action: 'suspend' | 'activate' | 'force_logout';
};

type AccountDraft = {
  displayName: string;
  password: string;
  role: 'admin' | 'member';
};

type AccountCreateDraft = {
  username: string;
  displayName: string;
  password: string;
  role: 'admin' | 'member';
};

const ACCOUNT_PAGE_SIZE = 10;

export function AccountRoleBadge({ role }: { role: EmployeeAccount['role'] }) {
  return (
    <StatusBadge tone={role === 'admin' ? 'blue' : 'gray'}>
      {role === 'admin' ? '管理员' : '普通成员'}
    </StatusBadge>
  );
}

export function AccountStatusBadge({ status }: { status: EmployeeAccount['status'] }) {
  return (
    <StatusBadge tone={status === 'active' ? 'green' : 'red'}>
      {status === 'active' ? '已启用' : '已停用'}
    </StatusBadge>
  );
}

export default function AccountsPage({
  currentUser,
  onLogout,
}: {
  currentUser?: EnterpriseAuthUser;
  onLogout?: () => void;
} = {}) {
  const [rows, setRows] = useState<EmployeeAccount[]>([]);
  const [loading, setLoading] = useState(false);
  const [searchText, setSearchText] = useState('');
  const [editing, setEditing] = useState<EmployeeAccount | null>(null);
  const [draft, setDraft] = useState<AccountDraft>({ displayName: '', password: '', role: 'member' });
  const [saving, setSaving] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [createDraft, setCreateDraft] = useState<AccountCreateDraft>({
    username: '',
    displayName: '',
    password: '',
    role: 'member',
  });
  const [creating, setCreating] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<EmployeeAccount | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [invitations, setInvitations] = useState<UserInvitation[]>([]);
  const [events, setEvents] = useState<LifecycleEvent[]>([]);
  const [inviteOpen, setInviteOpen] = useState(false);
  const [inviteDraft, setInviteDraft] = useState<InviteDraft>({
    username: '',
    displayName: '',
    role: 'member',
    businessRole: 'member',
    authSource: 'local',
  });
  const [inviting, setInviting] = useState(false);
  const [createdInvitation, setCreatedInvitation] = useState<UserInvitationCreated | null>(null);
  const [lifecycleTarget, setLifecycleTarget] = useState<LifecycleTarget | null>(null);
  const [lifecycleReason, setLifecycleReason] = useState('管理员执行账号生命周期操作');
  const [lifecycleSaving, setLifecycleSaving] = useState(false);
  const [preferences, setPreferences] = useState<Preferences | null>(null);
  const [preferenceSaving, setPreferenceSaving] = useState(false);

  async function load() {
    setLoading(true);
    try {
      const [result, inviteRows, auditRows, preferenceRow] = await Promise.all([
        api.get<EmployeeAccount[]>(`/api/auth/users?tenant_id=${TENANT_ID}`),
        api.get<UserInvitation[]>(`/api/auth/users/invitations?tenant_id=${TENANT_ID}`),
        api.get<LifecycleEvent[]>(`/api/auth/users/lifecycle-events?tenant_id=${TENANT_ID}&limit=20`),
        api.get<Preferences>('/api/auth/preferences'),
      ]);
      setRows(result);
      setInvitations(inviteRows);
      setEvents(auditRows);
      setPreferences(preferenceRow);
    } catch (error) {
      notify.error(error instanceof Error ? error.message : '加载账号失败');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  const filteredRows = useMemo(() => {
    const keyword = searchText.trim().toLowerCase();
    if (!keyword) return rows;
    return rows.filter((row) =>
      [row.username, row.display_name || '', row.role === 'admin' ? '管理员' : '普通成员']
        .some((value) => value.toLowerCase().includes(keyword)),
    );
  }, [rows, searchText]);

  const pagination = useClientPagination(filteredRows, ACCOUNT_PAGE_SIZE, searchText);

  function openEdit(row: EmployeeAccount) {
    setEditing(row);
    setDraft({ displayName: row.display_name || row.username, password: '', role: row.role });
  }

  function openCreate() {
    setCreateDraft({ username: '', displayName: '', password: '', role: 'member' });
    setCreateOpen(true);
  }

  function openInvite() {
    setInviteDraft({
      username: '',
      displayName: '',
      role: 'member',
      businessRole: 'member',
      authSource: 'local',
    });
    setCreatedInvitation(null);
    setInviteOpen(true);
  }

  async function saveInvite() {
    const username = inviteDraft.username.trim();
    if (!username) {
      notify.error('请填写账号');
      return;
    }
    setInviting(true);
    try {
      const created = await api.post<UserInvitationCreated>('/api/auth/users/invitations', {
        tenant_id: TENANT_ID,
        username,
        display_name: inviteDraft.displayName.trim() || username,
        role: inviteDraft.role,
        business_role: inviteDraft.businessRole,
        auth_source: inviteDraft.authSource,
      });
      setCreatedInvitation(created);
      notify.success('邀请已创建，请安全发送一次性链接');
      await load();
    } catch (error) {
      notify.error(error instanceof Error ? error.message : '创建邀请失败');
    } finally {
      setInviting(false);
    }
  }

  async function applyLifecycleAction() {
    if (!lifecycleTarget || !lifecycleReason.trim()) {
      notify.error('请填写操作原因');
      return;
    }
    const { account, action } = lifecycleTarget;
    setLifecycleSaving(true);
    try {
      if (action === 'force_logout') {
        await api.post(`/api/auth/users/${account.id}/force-logout`, {
          tenant_id: TENANT_ID,
          reason: lifecycleReason.trim(),
        });
      } else {
        await api.post(`/api/auth/users/${account.id}/status`, {
          tenant_id: TENANT_ID,
          status: action === 'suspend' ? 'suspended' : 'active',
          reason: lifecycleReason.trim(),
        });
      }
      notify.success(action === 'force_logout' ? '全部九骥 Joukir 会话已失效' : '账号状态已更新');
      setLifecycleTarget(null);
      await load();
    } catch (error) {
      notify.error(error instanceof Error ? error.message : '账号操作失败');
    } finally {
      setLifecycleSaving(false);
    }
  }

  async function saveTenantPreferences() {
    if (!preferences) return;
    setPreferenceSaving(true);
    try {
      const updated = await api.put<Preferences>('/api/auth/tenant-preferences', {
        tenant_id: TENANT_ID,
        default_locale: preferences.tenant_default_locale,
        default_timezone: preferences.tenant_default_timezone,
        default_currency: preferences.tenant_default_currency,
      });
      setPreferences(updated);
      notify.success('租户区域偏好已保存');
    } catch (error) {
      notify.error(error instanceof Error ? error.message : '保存租户区域偏好失败');
    } finally {
      setPreferenceSaving(false);
    }
  }

  async function saveCreate() {
    const username = createDraft.username.trim();
    const password = createDraft.password.trim();
    if (!username || !password) {
      notify.error('请填写账号和密码');
      return;
    }
    setCreating(true);
    try {
      await api.post('/api/auth/users', {
        tenant_id: TENANT_ID,
        username,
        password,
        display_name: createDraft.displayName.trim() || username,
        role: createDraft.role,
      });
      notify.success('账号已创建');
      setCreateOpen(false);
      await load();
    } catch (error) {
      notify.error(error instanceof Error ? error.message : '创建账号失败');
    } finally {
      setCreating(false);
    }
  }

  async function saveEdit() {
    if (!editing) return;
    setSaving(true);
    try {
      await api.put(`/api/auth/users/${editing.id}`, {
        tenant_id: TENANT_ID,
        display_name: draft.displayName.trim() || editing.username,
        password: draft.password.trim() || undefined,
        role: draft.role,
      });
      notify.success('账号已更新');
      setEditing(null);
      await load();
    } catch (error) {
      notify.error(error instanceof Error ? error.message : '保存账号失败');
    } finally {
      setSaving(false);
    }
  }

  async function confirmDelete() {
    const row = deleteTarget;
    if (!row) return;
    setDeleting(true);
    try {
      await api.delete(`/api/auth/users/${row.id}?tenant_id=${TENANT_ID}`);
      notify.success('账号已删除');
      setDeleteTarget(null);
      await load();
    } catch (error) {
      notify.error(error instanceof Error ? error.message : '删除账号失败');
    } finally {
      setDeleting(false);
    }
  }

  function renderActions(row: EmployeeAccount) {
    const isProtected = row.role === 'admin';
    return (
      <DropdownMenu>
        <DropdownMenuTrigger
          aria-label="账号操作"
          className="ml-auto grid size-7 place-items-center rounded-[8px] text-[#1a71ff] transition-colors outline-none hover:bg-black/5 hover:text-[#4a8dff] focus-visible:bg-black/5"
        >
          <IconMore className="size-3.5" />
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className={MENU_CONTENT_CLASS}>
          <DropdownMenuItem className={MENU_ITEM_CLASS} onSelect={() => openEdit(row)}>
            <IconEdit />
            编辑
          </DropdownMenuItem>
          <DropdownMenuItem
            className={MENU_ITEM_CLASS}
            disabled={row.id === currentUser?.id}
            onSelect={() => {
              setLifecycleReason(row.status === 'active' ? '暂停账号访问' : '恢复账号访问');
              setLifecycleTarget({ account: row, action: row.status === 'active' ? 'suspend' : 'activate' });
            }}
          >
            {row.status === 'active' ? <UserRoundX /> : <UserRoundCheck />}
            {row.status === 'active' ? '停用账号' : '恢复账号'}
          </DropdownMenuItem>
          <DropdownMenuItem
            className={MENU_ITEM_CLASS}
            onSelect={() => {
              setLifecycleReason('安全要求强制下线');
              setLifecycleTarget({ account: row, action: 'force_logout' });
            }}
          >
            <LogOut />
            强制下线
          </DropdownMenuItem>
          <DropdownMenuSeparator className="my-[2px] bg-[#eef0f4]" />
          <DropdownMenuItem
            variant="destructive"
            className={MENU_ITEM_DANGER_CLASS}
            disabled={isProtected}
            onSelect={() => setDeleteTarget(row)}
          >
            <IconTrash />
            删除
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    );
  }

  const columns: DataTableColumn<EmployeeAccount>[] = [
    {
      key: 'username',
      title: '用户名',
      width: 220,
      className: 'text-[#18181a]',
      render: (row) => (
        <span className="flex min-w-0 items-center gap-[8px]">
          <span className="grid size-[24px] shrink-0 place-items-center rounded-full bg-[#eef1fb] text-[#7e96dc]">
            <User className="size-[14px]" />
          </span>
          <span className="truncate font-medium">{row.username}</span>
        </span>
      ),
    },
    {
      key: 'display_name',
      title: '显示名',
      width: 200,
      render: (row) => <span className="block truncate">{row.display_name || row.username}</span>,
    },
    {
      key: 'role',
      title: '角色',
      width: 120,
      render: (row) => <AccountRoleBadge role={row.role} />,
    },
    {
      key: 'status',
      title: '状态',
      width: 110,
      render: (row) => <AccountStatusBadge status={row.status} />,
    },
    {
      key: 'source',
      title: '身份来源',
      width: 150,
      render: (row) => (
        <span className="text-[12px] text-[#596174]">
          {row.source === 'oidc' ? 'Casdoor OIDC' : '本地账号'}
          {row.identity_sync_status === 'pending' ? ' · 待同步' : ''}
        </span>
      ),
    },
    { key: 'created', title: '创建时间', width: 180, render: (row) => formatDateTime(row.created_at) },
    { key: 'updated', title: '最近更新', width: 180, render: (row) => formatDateTime(row.updated_at) },
    {
      key: 'actions',
      title: '操作',
      width: 70,
      align: 'right',
      render: (row) => renderActions(row),
    },
  ];

  const renderMobileCard = (row: EmployeeAccount) => (
    <article className={MOBILE_CARD_CLASS} key={row.id}>
      <div className="flex min-w-0 items-start justify-between gap-[10px]">
        <span className="flex min-w-0 items-center gap-[8px]">
          <span className="grid size-[28px] shrink-0 place-items-center rounded-full bg-[#eef1fb] text-[#7e96dc]">
            <User className="size-[15px]" />
          </span>
          <span className="min-w-0">
            <strong className="block truncate text-[14px] font-semibold text-[#18181a]">{row.username}</strong>
            <span className="mt-[2px] block truncate text-[12px] text-[#858b9c]">{row.display_name || row.username}</span>
            <span className="mt-[6px] block">
              <span className="flex gap-[6px]">
                <AccountRoleBadge role={row.role} />
                <AccountStatusBadge status={row.status} />
              </span>
            </span>
          </span>
        </span>
        {renderActions(row)}
      </div>
      <div className="mt-[10px] flex items-center justify-between gap-[10px] text-[12px] text-[#858b9c]">
        <span>创建 {formatDateTime(row.created_at)}</span>
        <span>更新 {formatDateTime(row.updated_at)}</span>
      </div>
    </article>
  );

  return (
    <div className="min-h-full box-border px-[48px] pt-[32px] pb-[43px] max-[900px]:px-[16px]" aria-busy={loading}>
      <AppHeader onLogout={onLogout} userName={currentUser?.username} title="账号管理" />

      <div className="mt-[20px] mb-[16px] flex items-center justify-end gap-[12px]">
        <UIButton
          variant="outline"
          onClick={() => void load()}
          disabled={loading}
          className="h-[34px] gap-[4px] rounded-[10px] border-[0.5px] border-[#e3e7f1] bg-white px-[20px] text-[12px] font-normal text-[#757f9c] hover:border-[#cbd3e6] hover:bg-white hover:text-[#18181a]"
        >
          <IconRefresh className={cn('size-[14px]', loading && 'animate-spin')} />
          刷新
        </UIButton>
        <UIButton
          variant="outline"
          onClick={openInvite}
          className="h-[34px] gap-[4px] rounded-[10px] border-[0.5px] border-[#e3e7f1] bg-white px-[20px] text-[12px] font-normal text-[#464c5e] hover:bg-[#f6f6f6]"
        >
          <MailPlus className="size-[14px]" />
          邀请账号
        </UIButton>
        <UIButton
          onClick={openCreate}
          className="h-[34px] gap-[4px] rounded-[10px] bg-[#18181a] px-[20px] text-[12px] font-normal text-white hover:bg-[#303030]"
        >
          <IconAdd className="size-[14px]" />
          新建账号
        </UIButton>
      </div>

      <div className="mt-[16px] grid gap-[16px] xl:grid-cols-3">
        <section className="rounded-[16px] bg-white p-[18px] shadow-[0_2px_12px_rgba(0,0,0,0.04)]">
          <div className="mb-[12px] flex items-center gap-[6px] text-[13px] text-[#596174]">
            <MailPlus className="size-[14px]" />
            最近邀请
          </div>
          <div className="space-y-[8px]">
            {invitations.slice(0, 6).map((row) => (
              <div key={row.id} className="flex items-center justify-between gap-[12px] rounded-[10px] border border-[#eef0f4] px-[12px] py-[9px] text-[12px]">
                <span className="min-w-0">
                  <strong className="block truncate text-[#18181a]">{row.display_name || row.username}</strong>
                  <span className="text-[#858b9c]">{row.username} · {row.auth_source === 'oidc' ? 'Casdoor' : '本地激活'}</span>
                </span>
                <StatusBadge tone={row.status === 'pending' ? 'blue' : row.status === 'accepted' ? 'green' : 'gray'}>
                  {row.status === 'pending' ? '待接受' : row.status === 'accepted' ? '已接受' : row.status === 'cancelled' ? '已取消' : '已过期'}
                </StatusBadge>
              </div>
            ))}
            {!invitations.length && <p className="py-[18px] text-center text-[12px] text-[#858b9c]">暂无邀请</p>}
          </div>
        </section>

        <section className="rounded-[16px] bg-white p-[18px] shadow-[0_2px_12px_rgba(0,0,0,0.04)]">
          <div className="mb-[12px] flex items-center gap-[6px] text-[13px] text-[#596174]">
            租户默认区域偏好
          </div>
          {preferences ? (
            <div className="space-y-[10px]">
              <LabeledField label="默认语言">
                <Select value={preferences.tenant_default_locale} onValueChange={(value) => setPreferences({ ...preferences, tenant_default_locale: value as Preferences['tenant_default_locale'] })}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="zh-CN">简体中文</SelectItem>
                    <SelectItem value="en">English</SelectItem>
                  </SelectContent>
                </Select>
              </LabeledField>
              <LabeledField label="默认时区">
                <Input value={preferences.tenant_default_timezone} onChange={(event) => setPreferences({ ...preferences, tenant_default_timezone: event.target.value })} />
              </LabeledField>
              <LabeledField label="默认币种">
                <Input maxLength={3} value={preferences.tenant_default_currency} onChange={(event) => setPreferences({ ...preferences, tenant_default_currency: event.target.value.toUpperCase() })} />
              </LabeledField>
              <UIButton disabled={preferenceSaving} onClick={() => void saveTenantPreferences()} className="w-full">保存租户偏好</UIButton>
            </div>
          ) : <p className="py-[18px] text-center text-[12px] text-[#858b9c]">加载中…</p>}
        </section>

        <section className="rounded-[16px] bg-white p-[18px] shadow-[0_2px_12px_rgba(0,0,0,0.04)]">
          <div className="mb-[12px] flex items-center gap-[6px] text-[13px] text-[#596174]">
            <ShieldCheck className="size-[14px]" />
            账号安全审计
          </div>
          <div className="space-y-[8px]">
            {events.slice(0, 6).map((row) => (
              <div key={row.id} className="flex items-center justify-between gap-[12px] rounded-[10px] border border-[#eef0f4] px-[12px] py-[9px] text-[12px]">
                <span className="min-w-0">
                  <strong className="block truncate text-[#18181a]">{eventLabel(row.event_type)} · {row.subject_ref || '未知主体'}</strong>
                  <span className="text-[#858b9c]">{row.reason || '已记录'} · {formatDateTime(row.occurred_at)}</span>
                </span>
                <StatusBadge tone={row.outcome === 'allowed' ? 'green' : row.outcome === 'degraded' ? 'orange' : 'red'}>
                  {row.outcome === 'allowed' ? '成功' : row.outcome === 'degraded' ? '降级' : '拒绝'}
                </StatusBadge>
              </div>
            ))}
            {!events.length && <p className="py-[18px] text-center text-[12px] text-[#858b9c]">暂无审计事件</p>}
          </div>
        </section>
      </div>

      <div className="flex flex-col gap-[24px] rounded-[20px_20px_0_0] bg-white p-[18px_18px_24px_18px] shadow-[0_-4px_16px_0_rgba(0,0,0,0.05)]">
        <div className="flex flex-col gap-[18px]">
          <div className="flex items-center gap-[6px] px-[12px] text-[#757f9c]">
            <IconAccounts className="size-[14px] shrink-0" />
            <span className="text-[14px] font-normal leading-none">账号列表</span>
          </div>

          <label className="flex h-[34px] w-[300px] items-center gap-[8px] overflow-hidden rounded-[10px] border-[0.5px] border-[#e3e7f1] bg-white px-[12px] transition-colors focus-within:border-[#18181a] max-[900px]:w-full">
            <IconSearch className="size-[14px] shrink-0 text-[#858b9c]" />
            <input
              autoComplete="off"
              data-1p-ignore="true"
              data-lpignore="true"
              data-bwignore="true"
              value={searchText}
              placeholder="搜索用户名或显示名"
              onChange={(event) => setSearchText(event.target.value)}
              className="h-full min-w-0 flex-1 bg-transparent text-[12px] text-[#17191f] outline-none placeholder:text-[#c0c6d4]"
            />
            {searchText && (
              <button
                type="button"
                aria-label="清除搜索"
                onClick={() => setSearchText('')}
                className="grid size-[16px] shrink-0 place-items-center text-[#c0c6d4] hover:text-[#858b9c]"
              >
                <IconClear className="size-[14px]" />
              </button>
            )}
          </label>

          <div className="grid gap-[10px] md:hidden">
            {filteredRows.length ? (
              pagination.pagedItems.map(renderMobileCard)
            ) : (
              <div className="py-[40px] text-center text-[13px] text-[#858b9c]">暂无账号</div>
            )}
          </div>

          <div className="hidden md:block">
            <DataTable
              aria-label="账号列表"
              columns={columns}
              data={pagination.pagedItems}
              rowKey={(row) => row.id}
              loading={loading}
              emptyText="暂无账号"
            />
          </div>

          {filteredRows.length > 0 && (
            <Paginator
              aria-label="账号分页"
              className="mt-0 mb-[6px]"
              page={pagination.page}
              pageCount={pagination.pageCount}
              onChange={pagination.setPage}
            />
          )}
        </div>
      </div>

      <AccountDialog
        open={createOpen}
        title="新建账号"
        loading={creating}
        submitText="创建"
        username={{ value: createDraft.username, onChange: (value) => setCreateDraft((prev) => ({ ...prev, username: value })) }}
        displayName={createDraft.displayName}
        onDisplayNameChange={(value) => setCreateDraft((prev) => ({ ...prev, displayName: value }))}
        password={createDraft.password}
        onPasswordChange={(value) => setCreateDraft((prev) => ({ ...prev, password: value }))}
        role={createDraft.role}
        onRoleChange={(value) => setCreateDraft((prev) => ({ ...prev, role: value }))}
        passwordLabel="初始密码"
        onClose={() => setCreateOpen(false)}
        onSubmit={() => void saveCreate()}
      />

      <InvitationDialog
        open={inviteOpen}
        loading={inviting}
        draft={inviteDraft}
        created={createdInvitation}
        onChange={setInviteDraft}
        onClose={() => setInviteOpen(false)}
        onSubmit={() => void saveInvite()}
      />

      <Dialog open={Boolean(lifecycleTarget)} onOpenChange={(open) => !open && setLifecycleTarget(null)}>
        <DialogContent aria-describedby={undefined} className="w-[calc(100%-2rem)] rounded-[14px] sm:max-w-[440px]">
          <DialogTitle className="text-[15px]">
            {lifecycleTarget?.action === 'force_logout' ? '强制下线' : lifecycleTarget?.action === 'suspend' ? '停用账号' : '恢复账号'}
          </DialogTitle>
          <p className="text-[12px] text-[#757f9c]">目标账号：{lifecycleTarget?.account.username}</p>
          <LabeledField label="操作原因（写入不可变审计）">
            <Input value={lifecycleReason} onChange={(event) => setLifecycleReason(event.target.value)} />
          </LabeledField>
          <div className="flex justify-end gap-[8px]">
            <UIButton variant="outline" disabled={lifecycleSaving} onClick={() => setLifecycleTarget(null)}>取消</UIButton>
            <UIButton disabled={lifecycleSaving || !lifecycleReason.trim()} onClick={() => void applyLifecycleAction()}>确认</UIButton>
          </div>
        </DialogContent>
      </Dialog>

      <AccountDialog
        open={Boolean(editing)}
        title={editing ? `编辑账号：${editing.username}` : '编辑账号'}
        loading={saving}
        submitText="保存"
        username={null}
        displayName={draft.displayName}
        onDisplayNameChange={(value) => setDraft((prev) => ({ ...prev, displayName: value }))}
        password={draft.password}
        onPasswordChange={(value) => setDraft((prev) => ({ ...prev, password: value }))}
        role={draft.role}
        onRoleChange={(value) => setDraft((prev) => ({ ...prev, role: value }))}
        roleDisabled={editing?.id === currentUser?.id}
        passwordLabel="新密码"
        passwordPlaceholder="不修改请留空"
        onClose={() => setEditing(null)}
        onSubmit={() => void saveEdit()}
      />

      <ConfirmDialog
        open={Boolean(deleteTarget)}
        onOpenChange={(open) => !open && setDeleteTarget(null)}
        loading={deleting}
        title={deleteTarget ? `删除账号「${deleteTarget.username}」？` : ''}
        description="删除后该账号无法登录，但其创建的数字员工仍然保留。"
        onConfirm={() => void confirmDelete()}
      />

    </div>
  );
}

function AccountDialog({
  open,
  title,
  loading,
  submitText,
  username,
  displayName,
  onDisplayNameChange,
  password,
  onPasswordChange,
  role,
  onRoleChange,
  roleDisabled = false,
  passwordLabel,
  passwordPlaceholder,
  onClose,
  onSubmit,
}: {
  open: boolean;
  title: string;
  loading: boolean;
  submitText: string;
  username: { value: string; onChange: (value: string) => void } | null;
  displayName: string;
  onDisplayNameChange: (value: string) => void;
  password: string;
  onPasswordChange: (value: string) => void;
  role: 'admin' | 'member';
  onRoleChange: (value: 'admin' | 'member') => void;
  roleDisabled?: boolean;
  passwordLabel: string;
  passwordPlaceholder?: string;
  onClose: () => void;
  onSubmit: () => void;
}) {
  return (
    <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
      <DialogContent
        aria-describedby={undefined}
        className="flex w-[calc(100%-2rem)] flex-col gap-[16px] overflow-hidden rounded-[14px] px-[20px] py-[16px] sm:max-w-[440px]"
      >
        <div className="flex items-center gap-[6px] px-[12px] text-[#757f9c]">
          <IconAccounts className="size-[14px] shrink-0" />
          <DialogTitle className="text-[14px] font-normal leading-none text-[#757f9c]">
            {title}
          </DialogTitle>
        </div>

        <div className="flex flex-col gap-[14px] px-[12px]">
          {username && (
            <LabeledField label="用户名">
              <Input
                value={username.value}
                placeholder="例如 zhang_san"
                onChange={(event) => username.onChange(event.target.value)}
              />
            </LabeledField>
          )}
          <LabeledField label="显示名">
            <Input
              value={displayName}
              placeholder="例如 张三"
              onChange={(event) => onDisplayNameChange(event.target.value)}
            />
          </LabeledField>
          <LabeledField label={passwordLabel}>
            <Input
              type="password"
              value={password}
              placeholder={passwordPlaceholder}
              onChange={(event) => onPasswordChange(event.target.value)}
            />
          </LabeledField>
          <LabeledField label="账号角色">
            <Select
              value={role}
              disabled={roleDisabled}
              onValueChange={(value) => onRoleChange(value as 'admin' | 'member')}
            >
              <SelectTrigger className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="member">普通成员</SelectItem>
                <SelectItem value="admin">管理员</SelectItem>
              </SelectContent>
            </Select>
          </LabeledField>
        </div>

        <div className="flex items-center justify-end gap-[8px] px-[12px]">
          <UIButton
            variant="outline"
            disabled={loading}
            onClick={onClose}
            className="h-[32px] w-[80px] rounded-[10px] border-[#e3e7f1] bg-white px-[12px] text-[14px] font-normal text-[#464c5e] hover:border-[#e3e7f1] hover:bg-[#f6f6f6] hover:text-[#18181a]"
          >
            取消
          </UIButton>
          <UIButton
            disabled={loading}
            onClick={onSubmit}
            className="h-[32px] w-[80px] rounded-[10px] bg-[#18181a] px-[12px] text-[14px] font-normal text-white hover:bg-[#303030]"
          >
            {submitText}
          </UIButton>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function LabeledField({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="flex flex-col gap-[6px]">
      <span className="text-[12px] font-medium text-[#464c5e]">{label}</span>
      {children}
    </label>
  );
}

const BUSINESS_ROLE_OPTIONS = [
  ['member', '普通成员'],
  ['operations_supervisor', '运营主管'],
  ['after_sales_specialist', '跨境售后专员'],
  ['listing_compliance_specialist', 'Listing 合规专员'],
  ['logistics_exception_specialist', '物流异常专员'],
  ['advertising_inspection_specialist', '广告巡检专员'],
  ['designer', '美工设计'],
  ['procurement_specialist', '采购专员'],
] as const;

function InvitationDialog({
  open,
  loading,
  draft,
  created,
  onChange,
  onClose,
  onSubmit,
}: {
  open: boolean;
  loading: boolean;
  draft: InviteDraft;
  created: UserInvitationCreated | null;
  onChange: (draft: InviteDraft) => void;
  onClose: () => void;
  onSubmit: () => void;
}) {
  const invitationUrl = created ? `${window.location.origin}${created.accept_path}` : '';
  return (
    <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
      <DialogContent aria-describedby={undefined} className="w-[calc(100%-2rem)] rounded-[14px] sm:max-w-[520px]">
        <DialogTitle className="text-[15px]">邀请账号</DialogTitle>
        {created ? (
          <div className="space-y-[12px]">
            <p className="rounded-[10px] bg-[#f4f8ff] px-[12px] py-[10px] text-[12px] leading-5 text-[#4c6387]">
              {created.auth_source === 'oidc'
                ? 'Casdoor 用户需使用相同用户名登录；九骥 Joukir 会在 OIDC 回调中接受邀请并绑定岗位。'
                : '此链接包含一次性邀请密钥，只显示本次。请通过安全渠道发送。'}
            </p>
            <LabeledField label={created.auth_source === 'oidc' ? 'Casdoor 登录入口' : '一次性激活链接'}>
              <div className="flex gap-[8px]">
                <Input readOnly value={invitationUrl} />
                <UIButton
                  variant="outline"
                  onClick={() => void navigator.clipboard.writeText(invitationUrl).then(() => notify.success('已复制'))}
                >
                  复制
                </UIButton>
              </div>
            </LabeledField>
            <div className="flex justify-end">
              <UIButton onClick={onClose}>完成</UIButton>
            </div>
          </div>
        ) : (
          <div className="space-y-[12px]">
            <LabeledField label="用户名">
              <Input value={draft.username} onChange={(event) => onChange({ ...draft, username: event.target.value })} />
            </LabeledField>
            <LabeledField label="显示名">
              <Input value={draft.displayName} onChange={(event) => onChange({ ...draft, displayName: event.target.value })} />
            </LabeledField>
            <LabeledField label="身份来源">
              <Select value={draft.authSource} onValueChange={(value) => onChange({ ...draft, authSource: value as InviteDraft['authSource'] })}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="oidc">Casdoor OIDC（生产推荐）</SelectItem>
                  <SelectItem value="local">本地激活（演示/应急）</SelectItem>
                </SelectContent>
              </Select>
            </LabeledField>
            <LabeledField label="账号角色">
              <Select value={draft.role} onValueChange={(value) => onChange({ ...draft, role: value as InviteDraft['role'], businessRole: value === 'admin' ? 'member' : draft.businessRole })}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="member">普通成员</SelectItem>
                  <SelectItem value="admin">租户管理员</SelectItem>
                </SelectContent>
              </Select>
            </LabeledField>
            {draft.role === 'member' && (
              <LabeledField label="业务岗位">
                <Select value={draft.businessRole} onValueChange={(value) => onChange({ ...draft, businessRole: value })}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {BUSINESS_ROLE_OPTIONS.map(([value, label]) => <SelectItem key={value} value={value}>{label}</SelectItem>)}
                  </SelectContent>
                </Select>
              </LabeledField>
            )}
            <div className="flex justify-end gap-[8px]">
              <UIButton variant="outline" disabled={loading} onClick={onClose}>取消</UIButton>
              <UIButton disabled={loading || !draft.username.trim()} onClick={onSubmit}>创建邀请</UIButton>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

function eventLabel(eventType: string): string {
  const labels: Record<string, string> = {
    login_succeeded: '登录成功',
    login_denied: '登录拒绝',
    logout: '退出登录',
    user_created: '创建账号',
    user_updated: '更新账号',
    user_deleted: '删除账号',
    user_invited: '邀请账号',
    invitation_accepted: '接受邀请',
    invitation_cancelled: '取消邀请',
    invitation_expired: '邀请过期',
    user_status_changed: '状态变更',
    sessions_revoked: '强制下线',
  };
  return labels[eventType] || eventType;
}
