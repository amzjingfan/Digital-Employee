import { useCallback, useEffect, useMemo, useState } from 'react';

import { api, TENANT_ID } from '@/api/client';
import type { EnterpriseAuthUser } from '@/auth';
import AppHeader from '@/components/AppHeader';
import { notify } from '@/components/ui/app-toast';
import { Button, Dialog, DialogContent, DialogFooter, DialogTitle, Input, Textarea } from '@/components/ui';
import { cn } from '@/lib/utils';

type TaskStatus = 'pending' | 'in_progress' | 'waiting_input' | 'review' | 'completed' | 'failed' | 'cancelled' | 'archived';

type TaskEvidence = {
  id: string;
  source_type: string;
  source_id: string;
  severity: string;
  label: string;
  summary: string;
  source_route: string;
  occurred_at: string;
};

type TaskEvent = {
  id: string;
  event_type: string;
  actor_business_role?: string | null;
  from_status?: string | null;
  to_status?: string | null;
  detail: Record<string, unknown>;
  created_at: string;
};

type TaskRun = {
  id: string;
  attempt_no: number;
  generation: number;
  agent_id: string;
  session_id: string;
  status: 'running' | 'succeeded' | 'retrying' | 'failed' | 'cancelled' | 'stale';
  execution_mode: 'sandbox' | 'live';
  service_identity_id?: string | null;
  execution_snapshot_id?: string | null;
  snapshot_digest?: string | null;
  execution_snapshot?: {
    agent?: { name?: string; profile_digest?: string };
    service_identity?: { application_name?: string; client_id_fingerprint?: string };
    sops?: Array<{ skill_id?: string; name?: string; version?: string }>;
    knowledge_bases?: Array<{ knowledge_base_id?: string; name?: string; version?: string }>;
    tools?: Array<{ tool_id?: string; name?: string }>;
  } | null;
  result_summary?: string | null;
  error_code?: string | null;
  error_message?: string | null;
  trace: Record<string, unknown>;
  started_at: string;
  finished_at?: string | null;
};

type WorkTask = {
  id: string;
  source_type: string;
  source_report_id?: string | null;
  title: string;
  description?: string | null;
  owner_business_role: string;
  owner_role_label: string;
  assignee_agent_id?: string | null;
  assignee_agent_name?: string | null;
  priority: 'low' | 'normal' | 'high' | 'urgent';
  risk_level: 'low' | 'medium' | 'high' | 'critical';
  status: TaskStatus;
  control_mode: 'agent' | 'human';
  cancel_requested: boolean;
  execution_generation: number;
  attempt_count: number;
  max_attempts: number;
  next_attempt_at?: string | null;
  lease_expires_at?: string | null;
  latest_session_id?: string | null;
  taken_over_by_user_id?: string | null;
  taken_over_at?: string | null;
  last_error_code?: string | null;
  last_error_message?: string | null;
  result_summary?: string | null;
  scope: Record<string, unknown>;
  due_at?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  version: number;
  created_at: string;
  updated_at: string;
  evidence: TaskEvidence[];
  events: TaskEvent[];
  runs: TaskRun[];
};

type QueueSummary = {
  business_role: string;
  label: string;
  pending: number;
  in_progress: number;
  waiting_input: number;
  review: number;
  overdue: number;
  total_open: number;
};

type TaskListResponse = { items: WorkTask[]; queues: QueueSummary[] };
type Props = { currentUser: EnterpriseAuthUser; onLogout: () => void };

const ROLE_OPTIONS = [
  ['after_sales_specialist', '跨境售后'],
  ['listing_compliance_specialist', 'Listing 合规'],
  ['logistics_exception_specialist', '物流异常'],
  ['advertising_inspection_specialist', '广告巡检'],
  ['designer', '美工设计'],
  ['procurement_specialist', '采购'],
] as const;

const STATUS_LABELS: Record<TaskStatus, string> = {
  pending: '待处理', in_progress: '处理中', waiting_input: '待补充材料', review: '待复核',
  completed: '已完成', failed: '失败', cancelled: '已取消', archived: '已归档',
};

const STATUS_FILTERS: Array<[string, string]> = [
  ['', '全部状态'], ['pending', '待处理'], ['in_progress', '处理中'], ['waiting_input', '待补充'],
  ['review', '待复核'], ['completed', '已完成'], ['failed', '失败'],
];

function formatTime(value?: string | null): string {
  if (!value) return '-';
  return new Intl.DateTimeFormat(undefined, { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }).format(new Date(value));
}

function shortDigest(value?: string | null): string {
  if (!value) return '-';
  const digest = value.replace(/^sha256:/, '');
  return `${digest.slice(0, 10)}…${digest.slice(-6)}`;
}

function SnapshotReceipt({ run }: { run: TaskRun }) {
  const snapshot = run.execution_snapshot;
  if (!snapshot) return null;
  const identity = snapshot.service_identity;
  return <details className="mt-3 rounded-[10px] bg-[#f7f8fa] px-3 py-2 text-[11px] text-[#667085]">
    <summary className="cursor-pointer font-medium text-[#464c5e]">启动快照 · {shortDigest(run.snapshot_digest)}</summary>
    <div className="mt-2 grid gap-1 sm:grid-cols-2">
      <span>数字员工：{snapshot.agent?.name || run.agent_id}</span>
      <span>身份应用：{identity?.application_name || run.service_identity_id || '-'}</span>
      <span>Client ID 指纹：{shortDigest(identity?.client_id_fingerprint)}</span>
      <span>员工档案：{shortDigest(snapshot.agent?.profile_digest)}</span>
      <span>SOP：{snapshot.sops?.length ?? 0} 个版本</span>
      <span>知识库：{snapshot.knowledge_bases?.length ?? 0} 个版本</span>
      <span>工具：{snapshot.tools?.length ?? 0} 个摘要</span>
    </div>
    {!!snapshot.sops?.length && <p className="mt-2">SOP：{snapshot.sops.map((item) => `${item.name || item.skill_id}@${item.version || '-'}`).join('、')}</p>}
  </details>;
}

function newIdempotencyKey(userId: string): string {
  const random = typeof crypto !== 'undefined' && 'randomUUID' in crypto ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`;
  return `manual:${userId}:${random}`;
}

export default function WorkTasksPage({ currentUser, onLogout }: Props) {
  const manager = currentUser.role === 'admin' || currentUser.business_role === 'operations_supervisor';
  const [items, setItems] = useState<WorkTask[]>([]);
  const [queues, setQueues] = useState<QueueSummary[]>([]);
  const [selected, setSelected] = useState<WorkTask | null>(null);
  const [role, setRole] = useState(manager ? '' : currentUser.business_role || '');
  const [status, setStatus] = useState('');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState('');
  const [createOpen, setCreateOpen] = useState(false);
  const [createKey, setCreateKey] = useState(() => newIdempotencyKey(currentUser.id));
  const [title, setTitle] = useState('');
  const [createRole, setCreateRole] = useState(manager ? 'after_sales_specialist' : currentUser.business_role || 'after_sales_specialist');
  const [priority, setPriority] = useState('normal');
  const [dueAt, setDueAt] = useState('');

  const loadDetail = useCallback(async (taskId: string) => {
    const detail = await api.get<WorkTask>(`/api/enterprise/work-tasks/${encodeURIComponent(taskId)}?tenant_id=${encodeURIComponent(TENANT_ID)}`);
    setSelected(detail);
    setItems((current) => current.map((item) => item.id === detail.id ? detail : item));
  }, []);

  const loadTasks = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ tenant_id: TENANT_ID });
      if (role) params.set('owner_business_role', role);
      if (status) params.set('status', status);
      const result = await api.get<TaskListResponse>(`/api/enterprise/work-tasks?${params.toString()}`);
      setItems(result.items);
      setQueues(result.queues);
      const requested = new URLSearchParams(window.location.search).get('task_id');
      const target = requested || selected?.id || result.items[0]?.id;
      if (target && (result.items.some((item) => item.id === target) || requested)) await loadDetail(target);
      else setSelected(null);
    } catch (error) {
      notify.error(error instanceof Error ? error.message : '加载任务中心失败');
    } finally {
      setLoading(false);
    }
  }, [loadDetail, role, selected?.id, status]);

  useEffect(() => { void loadTasks(); }, [loadTasks]);

  async function transition(action: string) {
    if (!selected) return;
    setBusy(true);
    try {
      const task = await api.post<WorkTask>(`/api/enterprise/work-tasks/${encodeURIComponent(selected.id)}/transitions`, {
        tenant_id: TENANT_ID, action, expected_version: selected.version, note: note.trim(),
      });
      setSelected(task);
      setItems((current) => current.map((item) => item.id === task.id ? task : item));
      setNote('');
      notify.success(`任务已更新为“${STATUS_LABELS[task.status]}”`);
      void loadTasks();
    } catch (error) {
      notify.error(error instanceof Error ? error.message : '更新任务失败');
    } finally { setBusy(false); }
  }

  async function createTask() {
    if (title.trim().length < 4) return notify.warning('请填写任务标题');
    setBusy(true);
    try {
      const task = await api.post<WorkTask>('/api/enterprise/work-tasks', {
        tenant_id: TENANT_ID, idempotency_key: createKey, title: title.trim(), description: note.trim(),
        owner_business_role: createRole, priority, risk_level: 'medium', due_at: dueAt ? new Date(dueAt).toISOString() : null,
      });
      setCreateOpen(false);
      setTitle(''); setNote(''); setDueAt(''); setCreateKey(newIdempotencyKey(currentUser.id));
      setSelected(task);
      notify.success('任务已进入岗位待办队列');
      void loadTasks();
    } catch (error) {
      notify.error(error instanceof Error ? error.message : '创建任务失败');
    } finally { setBusy(false); }
  }

  const actionGroups = useMemo(() => {
    if (!selected) return [] as Array<[string, string, 'default' | 'outline']>;
    const actions: Array<[string, string, 'default' | 'outline']> = [];
    if (selected.status === 'pending') actions.push(['start', '开始处理', 'outline']);
    if ((selected.control_mode ?? 'agent') === 'agent' && ['in_progress', 'waiting_input', 'review'].includes(selected.status)) actions.push(['takeover', '人工接管', 'outline']);
    if (selected.control_mode === 'human' && selected.status === 'in_progress') actions.push(['request_input', '等待材料', 'outline'], ['request_review', '提交复核', 'default']);
    if (selected.control_mode === 'human' && selected.status === 'waiting_input') actions.push(['resume', '恢复处理', 'default']);
    if (selected.status === 'review') actions.push(['rework', '退回人工修改', 'outline'], ['complete', '确认完成', 'default']);
    if (selected.status === 'failed') actions.push(['retry', '数字员工重试', 'default']);
    if (selected.control_mode === 'human' && ['in_progress', 'waiting_input', 'review', 'failed'].includes(selected.status) && selected.assignee_agent_id) actions.push(['return_to_agent', '交回数字员工', 'outline']);
    if (manager && ['pending', 'in_progress', 'waiting_input', 'review'].includes(selected.status)) actions.push(['cancel', '取消任务', 'outline']);
    if (manager && ['completed', 'failed', 'cancelled'].includes(selected.status)) actions.push(['archive', '归档', 'outline']);
    return actions;
  }, [manager, selected]);

  return (
    <div className="min-h-full px-6 pb-12 pt-8 lg:px-12">
      <AppHeader title="统一任务中心" description="报告、人工、API 与跨岗位事件统一进入岗位队列；所有状态变化可追溯。" userName={currentUser.display_name || currentUser.username} onLogout={onLogout} />

      <div className="mt-6 flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap gap-2">
          {manager && <Button variant={role === '' ? 'default' : 'outline'} onClick={() => setRole('')}>全部岗位</Button>}
          {queues.map((queue) => (
            <Button key={queue.business_role} variant={role === queue.business_role ? 'default' : 'outline'} onClick={() => setRole(queue.business_role)}>
              {queue.label} <span className="ml-1 opacity-70">{queue.total_open}</span>
              {queue.overdue > 0 && <span className="ml-1 text-[#c24141]">逾期 {queue.overdue}</span>}
            </Button>
          ))}
        </div>
        <Button onClick={() => { setCreateKey(newIdempotencyKey(currentUser.id)); setCreateOpen(true); }}>新建任务</Button>
      </div>

      <div className="mt-4 flex flex-wrap gap-2">
        {STATUS_FILTERS.map(([value, label]) => <button key={value} type="button" onClick={() => setStatus(value)} className={cn('rounded-full px-3 py-1.5 text-[12px]', status === value ? 'bg-[#263449] text-white' : 'bg-white text-[#667085]')}>{label}</button>)}
      </div>

      <div className="mt-5 grid gap-5 xl:grid-cols-[380px_minmax(0,1fr)]">
        <aside className="rounded-[18px] border border-[#e6e8ee] bg-white p-3">
          <div className="px-2 pb-3 text-[13px] font-semibold text-[#303444]">岗位待办队列</div>
          {loading && <p className="px-2 py-6 text-[13px] text-[#858b9c]">加载中…</p>}
          {!loading && items.length === 0 && <p className="px-2 py-8 text-center text-[13px] text-[#858b9c]">当前筛选条件下没有任务。</p>}
          <div className="space-y-2">
            {items.map((task) => (
              <button key={task.id} type="button" onClick={() => void loadDetail(task.id)} className={cn('w-full rounded-[13px] border px-4 py-3 text-left', selected?.id === task.id ? 'border-[#92c8bc] bg-[#f1faf7]' : 'border-transparent hover:bg-[#f7f8fa]')}>
                <div className="flex items-start justify-between gap-3"><strong className="line-clamp-2 text-[13px] text-[#303444]">{task.title}</strong><span className="shrink-0 rounded-full bg-[#eef1f6] px-2 py-0.5 text-[10px] text-[#667085]">{STATUS_LABELS[task.status]}</span></div>
                <p className="mt-2 text-[11px] text-[#858b9c]">{task.owner_role_label} · {task.priority} · {task.assignee_agent_name || '岗位公共队列'}</p>
                <p className="mt-1 text-[11px] text-[#858b9c]">截止 {formatTime(task.due_at)} · 更新 {formatTime(task.updated_at)}</p>
              </button>
            ))}
          </div>
        </aside>

        <main className="min-w-0">
          {!selected && !loading && <div className="rounded-[18px] border border-dashed border-[#d8dbe4] bg-white p-12 text-center text-[#858b9c]">选择一条任务查看来源、状态和处理记录。</div>}
          {selected && <div className="space-y-5">
            <section className="rounded-[18px] border border-[#e6e8ee] bg-white p-5">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div><div className="flex items-center gap-2"><h2 className="text-[20px] font-semibold text-[#202331]">{selected.title}</h2><span className="rounded-full bg-[#eef3ff] px-2.5 py-1 text-[11px] text-[#315ea8]">{STATUS_LABELS[selected.status]}</span></div>
                  <p className="mt-2 text-[12px] text-[#858b9c]">{selected.owner_role_label} · {selected.assignee_agent_name || '岗位公共队列'} · 优先级 {selected.priority} · 风险 {selected.risk_level}</p>
                  <div className="mt-2 flex flex-wrap gap-2 text-[11px]">
                    <span className={cn('rounded-full px-2 py-1', (selected.control_mode ?? 'agent') === 'agent' ? 'bg-[#eef3ff] text-[#315ea8]' : 'bg-[#fff4e5] text-[#9a5b13]')}>{(selected.control_mode ?? 'agent') === 'agent' ? '数字员工控制' : '人工控制'}</span>
                    <span className="rounded-full bg-[#f2f4f7] px-2 py-1 text-[#667085]">尝试 {selected.attempt_count ?? 0}/{selected.max_attempts ?? 3}</span>
                    {selected.lease_expires_at && <span className="rounded-full bg-[#f2f4f7] px-2 py-1 text-[#667085]">租约至 {formatTime(selected.lease_expires_at)}</span>}
                  </div>
                  {selected.description && <p className="mt-3 text-[13px] text-[#505668]">{selected.description}</p>}
                  {selected.result_summary && <div className="mt-3 rounded-[12px] bg-[#f1faf7] p-3 text-[13px] text-[#355b52]">{selected.result_summary}</div>}
                  {selected.last_error_message && <div className="mt-3 rounded-[12px] bg-[#fff3f2] p-3 text-[12px] text-[#b42318]">{selected.last_error_code || '执行失败'}：{selected.last_error_message}</div>}
                </div>
                {selected.source_report_id && <a href={`/enterprise/operations-reports?report_id=${encodeURIComponent(selected.source_report_id)}`} className="text-[12px] text-[#315ea8]">查看来源报告</a>}
              </div>
              <div className="mt-5 flex flex-wrap gap-2">{actionGroups.map(([action, label, variant]) => <Button key={action} variant={variant} disabled={busy} onClick={() => void transition(action)}>{label}</Button>)}</div>
              {actionGroups.length > 0 && <Textarea className="mt-3" rows={2} value={note} onChange={(event) => setNote(event.target.value)} placeholder="可填写处理说明、退回原因或完成结论" />}
            </section>

            <div className="grid gap-5 lg:grid-cols-2">
              <section className="rounded-[18px] border border-[#e6e8ee] bg-white p-5"><h3 className="text-[15px] font-semibold text-[#303444]">来源证据</h3><div className="mt-3 divide-y divide-[#eceef2]">
                {selected.evidence.length === 0 && <p className="py-4 text-[13px] text-[#858b9c]">该任务未关联外部证据。</p>}
                {selected.evidence.map((item) => <a key={item.id} href={item.source_route} className="block py-3 hover:bg-[#fafbfc]"><span className="rounded-full bg-[#eef3ff] px-2 py-0.5 text-[11px] text-[#315ea8]">{item.label}</span><p className="mt-1 text-[13px] text-[#464c5e]">{item.summary}</p><p className="mt-1 text-[11px] text-[#858b9c]">{formatTime(item.occurred_at)}</p></a>)}
              </div></section>
              <section className="rounded-[18px] border border-[#e6e8ee] bg-white p-5"><h3 className="text-[15px] font-semibold text-[#303444]">任务 Trace</h3><div className="mt-3 space-y-3">
                {selected.events.map((event) => <div key={event.id} className="rounded-[12px] bg-[#f7f8fa] px-4 py-3"><div className="flex justify-between text-[11px] text-[#858b9c]"><span>{event.event_type} · {event.actor_business_role || 'system'}</span><span>{formatTime(event.created_at)}</span></div><p className="mt-1 text-[12px] text-[#464c5e]">{event.from_status || '创建'} → {event.to_status || selected.status}</p>{typeof event.detail.note === 'string' && event.detail.note && <p className="mt-1 text-[12px] text-[#667085]">{event.detail.note}</p>}</div>)}
              </div></section>
            </div>
            <section className="rounded-[18px] border border-[#e6e8ee] bg-white p-5"><h3 className="text-[15px] font-semibold text-[#303444]">数字员工执行记录</h3><div className="mt-3 space-y-3">
              {(selected.runs ?? []).length === 0 && <p className="py-4 text-[13px] text-[#858b9c]">尚未被数字员工领取。</p>}
              {(selected.runs ?? []).map((run) => <div key={run.id} className="rounded-[12px] border border-[#eceef2] p-4"><div className="flex flex-wrap items-center justify-between gap-2"><div className="text-[12px] font-medium text-[#303444]">第 {run.attempt_no} 次 · {run.execution_mode === 'sandbox' ? 'Sandbox 演示' : 'Live Agent'} · {run.status}</div><a href={`/workspace/chat/${encodeURIComponent(run.session_id)}`} className="text-[12px] text-[#315ea8]">打开执行会话</a></div><p className="mt-1 text-[11px] text-[#858b9c]">开始 {formatTime(run.started_at)} · 结束 {formatTime(run.finished_at)}</p><SnapshotReceipt run={run} />{run.result_summary && <p className="mt-2 text-[13px] text-[#505668]">{run.result_summary}</p>}{run.error_message && <p className="mt-2 text-[12px] text-[#b42318]">{run.error_code || 'error'}：{run.error_message}</p>}</div>)}
            </div></section>
          </div>}
        </main>
      </div>

      <Dialog open={createOpen} onOpenChange={setCreateOpen}><DialogContent><DialogTitle>新建统一任务</DialogTitle>
        <Input value={title} onChange={(event) => setTitle(event.target.value)} placeholder="填写可执行的任务标题" />
        <label className="space-y-2 text-[13px]">负责岗位<select className="h-10 w-full rounded-md border border-input bg-background px-3" value={createRole} disabled={!manager} onChange={(event) => setCreateRole(event.target.value)}>{ROLE_OPTIONS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
        <label className="space-y-2 text-[13px]">优先级<select className="h-10 w-full rounded-md border border-input bg-background px-3" value={priority} onChange={(event) => setPriority(event.target.value)}><option value="low">低</option><option value="normal">普通</option><option value="high">高</option><option value="urgent">紧急</option></select></label>
        <label className="space-y-2 text-[13px]">截止时间<Input type="datetime-local" value={dueAt} onChange={(event) => setDueAt(event.target.value)} /></label>
        <Textarea rows={3} value={note} onChange={(event) => setNote(event.target.value)} placeholder="任务说明（可选）" />
        <p className="text-[12px] text-[#858b9c]">创建操作使用稳定幂等键；网络重试不会重复生成任务，也不会触发外部写操作。</p>
        <DialogFooter><Button variant="outline" onClick={() => setCreateOpen(false)}>取消</Button><Button disabled={busy} onClick={() => void createTask()}>进入岗位队列</Button></DialogFooter>
      </DialogContent></Dialog>
    </div>
  );
}
