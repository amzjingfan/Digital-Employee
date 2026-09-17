import { useCallback, useEffect, useMemo, useState } from 'react';

import { api, TENANT_ID } from '@/api/client';
import type { EnterpriseAuthUser } from '@/auth';
import AppHeader from '@/components/AppHeader';
import { notify } from '@/components/ui/app-toast';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogTitle,
  Input,
  Textarea,
} from '@/components/ui';
import { cn } from '@/lib/utils';

type ReportType = 'daily' | 'weekly';
type ReportStatus = 'draft' | 'confirmed' | 'rejected';

type ReportSource = {
  id: string;
  source_type: string;
  source_id: string;
  business_key: string;
  severity: string;
  label: string;
  summary: string;
  source_route: string;
  occurred_at: string;
};

type ReportComment = {
  id: string;
  action_type: string;
  author_user_id: string;
  author_business_role: string;
  body: string;
  detail: Record<string, unknown>;
  created_at: string;
};

type OperationsReport = {
  id: string;
  report_type: ReportType;
  title: string;
  status: ReportStatus;
  timezone: string;
  period_start: string;
  period_end: string;
  scope: Record<string, string>;
  metrics: Record<string, number | string>;
  sections: Record<string, unknown>;
  data_status: string;
  source_count: number;
  generated_at: string;
  reviewed_by_user_id?: string | null;
  review_note?: string | null;
  reviewed_at?: string | null;
  sources: ReportSource[];
  comments: ReportComment[];
};

type Props = {
  currentUser: EnterpriseAuthUser;
  onLogout: () => void;
};

const METRIC_LABELS: Record<string, string> = {
  pending_approvals: '待审批',
  active_executions: '执行中',
  failed_executions: '执行异常',
  overdue_runs: '逾期任务',
  failed_runs: '任务失败',
  authorization_denials: '授权拒绝',
};

const STATUS_LABELS: Record<ReportStatus, string> = {
  draft: '待确认',
  confirmed: '已确认',
  rejected: '已驳回',
};

const ROLE_OPTIONS = [
  ['after_sales_specialist', '售后'],
  ['listing_compliance_specialist', 'Listing 合规'],
  ['logistics_exception_specialist', '物流'],
  ['advertising_inspection_specialist', '广告'],
  ['designer', '美工'],
  ['procurement_specialist', '采购'],
] as const;

function formatTime(value?: string | null): string {
  if (!value) return '-';
  return new Intl.DateTimeFormat(undefined, {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(value));
}

function objectList(value: unknown): Array<Record<string, unknown>> {
  return Array.isArray(value)
    ? value.filter((item): item is Record<string, unknown> => Boolean(item && typeof item === 'object'))
    : [];
}

function stringList(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : [];
}

export default function OperationsReportsPage({ currentUser, onLogout }: Props) {
  const [reports, setReports] = useState<OperationsReport[]>([]);
  const [selected, setSelected] = useState<OperationsReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [reviewAction, setReviewAction] = useState<'confirmed' | 'rejected' | null>(null);
  const [reviewNote, setReviewNote] = useState('');
  const [comment, setComment] = useState('');
  const [followUpOpen, setFollowUpOpen] = useState(false);
  const [followUpTitle, setFollowUpTitle] = useState('');
  const [followUpRole, setFollowUpRole] = useState('logistics_exception_specialist');
  const [followUpPriority, setFollowUpPriority] = useState('normal');

  const loadDetail = useCallback(async (reportId: string) => {
    const detail = await api.get<OperationsReport>(
      `/api/enterprise/operations-reports/${encodeURIComponent(reportId)}?tenant_id=${encodeURIComponent(TENANT_ID)}`,
    );
    setSelected(detail);
    setReports((items) => items.map((item) => (item.id === detail.id ? detail : item)));
  }, []);

  const loadReports = useCallback(async () => {
    setLoading(true);
    try {
      const items = await api.get<OperationsReport[]>(
        `/api/enterprise/operations-reports?tenant_id=${encodeURIComponent(TENANT_ID)}`,
      );
      setReports(items);
      if (items[0]) await loadDetail(items[0].id);
      else setSelected(null);
    } catch (error) {
      notify.error(error instanceof Error ? error.message : '加载运营报告失败');
    } finally {
      setLoading(false);
    }
  }, [loadDetail]);

  useEffect(() => {
    void loadReports();
  }, [loadReports]);

  async function generate(reportType: ReportType, refresh = false) {
    setBusy(true);
    try {
      const report = await api.post<OperationsReport>('/api/enterprise/operations-reports/generate', {
        tenant_id: TENANT_ID,
        report_type: reportType,
        timezone: 'Asia/Shanghai',
        refresh,
      });
      setReports((items) => [report, ...items.filter((item) => item.id !== report.id)]);
      setSelected(report);
      notify.success(refresh ? '已生成新的报告快照' : '运营报告已生成');
    } catch (error) {
      notify.error(error instanceof Error ? error.message : '生成运营报告失败');
    } finally {
      setBusy(false);
    }
  }

  async function submitComment() {
    if (!selected || comment.trim().length < 2) return notify.warning('请填写批注');
    setBusy(true);
    try {
      const report = await api.post<OperationsReport>(
        `/api/enterprise/operations-reports/${encodeURIComponent(selected.id)}/comments`,
        { tenant_id: TENANT_ID, body: comment.trim() },
      );
      setSelected(report);
      setComment('');
      notify.success('批注已追加');
    } catch (error) {
      notify.error(error instanceof Error ? error.message : '保存批注失败');
    } finally {
      setBusy(false);
    }
  }

  async function submitReview() {
    if (!selected || !reviewAction || reviewNote.trim().length < 2) {
      return notify.warning('请填写确认或驳回依据');
    }
    setBusy(true);
    try {
      const endpoint = reviewAction === 'confirmed' ? 'confirm' : 'reject';
      const report = await api.post<OperationsReport>(
        `/api/enterprise/operations-reports/${encodeURIComponent(selected.id)}/${endpoint}`,
        { tenant_id: TENANT_ID, note: reviewNote.trim() },
      );
      setSelected(report);
      setReports((items) => items.map((item) => (item.id === report.id ? report : item)));
      setReviewAction(null);
      setReviewNote('');
      notify.success(reviewAction === 'confirmed' ? '报告已确认' : '报告已驳回');
    } catch (error) {
      notify.error(error instanceof Error ? error.message : '报告评审失败');
    } finally {
      setBusy(false);
    }
  }

  async function submitFollowUp() {
    if (!selected || followUpTitle.trim().length < 4) return notify.warning('请填写后续任务标题');
    setBusy(true);
    try {
      const report = await api.post<OperationsReport>(
        `/api/enterprise/operations-reports/${encodeURIComponent(selected.id)}/follow-ups`,
        {
          tenant_id: TENANT_ID,
          title: followUpTitle.trim(),
          owner_business_role: followUpRole,
          priority: followUpPriority,
          source_ids: selected.sources.filter((item) => ['critical', 'high'].includes(item.severity)).slice(0, 10).map((item) => item.id),
        },
      );
      setSelected(report);
      setFollowUpOpen(false);
      setFollowUpTitle('');
      notify.success('后续任务已进入对应岗位的统一待办队列');
    } catch (error) {
      notify.error(error instanceof Error ? error.message : '创建后续任务失败');
    } finally {
      setBusy(false);
    }
  }

  const majorExceptions = useMemo(
    () => objectList(selected?.sections.major_exceptions),
    [selected],
  );
  const roleActivity = useMemo(() => objectList(selected?.sections.role_activity), [selected]);
  const rootCauses = useMemo(
    () => objectList(selected?.sections.recurring_root_causes),
    [selected],
  );
  const dataWarnings = useMemo(() => stringList(selected?.sections.data_quality), [selected]);

  return (
    <div className="min-h-full px-6 pb-12 pt-8 lg:px-12">
      <AppHeader
        title="运营报告中心"
        description="按固定周期汇总审批、外部执行、任务与授权事件；每项异常保留来源证据。"
        userName={currentUser.display_name || currentUser.username}
        onLogout={onLogout}
      />

      <div className="mt-6 flex flex-wrap items-center justify-between gap-3">
        <div className="flex gap-2">
          <Button disabled={busy} onClick={() => void generate('daily')}>生成今日日报</Button>
          <Button variant="outline" disabled={busy} onClick={() => void generate('weekly')}>生成本周周报</Button>
        </div>
        {selected && (
          <Button variant="outline" disabled={busy} onClick={() => void generate(selected.report_type, true)}>
            重新生成新快照
          </Button>
        )}
      </div>

      <div className="mt-5 grid gap-5 xl:grid-cols-[300px_minmax(0,1fr)]">
        <aside className="rounded-[18px] border border-[#e6e8ee] bg-white p-3">
          <div className="px-2 pb-3 text-[13px] font-semibold text-[#303444]">报告历史</div>
          {loading && <p className="px-2 py-6 text-[13px] text-[#858b9c]">加载中…</p>}
          {!loading && reports.length === 0 && (
            <p className="px-2 py-6 text-[13px] text-[#858b9c]">暂无报告，生成第一份日报开始运营复盘。</p>
          )}
          <div className="space-y-2">
            {reports.map((report) => (
              <button
                key={report.id}
                type="button"
                onClick={() => void loadDetail(report.id)}
                className={cn(
                  'w-full rounded-[12px] border px-3 py-3 text-left transition',
                  selected?.id === report.id ? 'border-[#9bcfc2] bg-[#f1faf7]' : 'border-transparent hover:bg-[#f7f8fa]',
                )}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="truncate text-[13px] font-medium text-[#303444]">{report.title}</span>
                  <span className="text-[11px] text-[#858b9c]">{STATUS_LABELS[report.status]}</span>
                </div>
                <p className="mt-1 text-[11px] text-[#858b9c]">{report.source_count} 条来源 · {formatTime(report.generated_at)}</p>
              </button>
            ))}
          </div>
        </aside>

        <main className="min-w-0">
          {!selected && !loading && (
            <div className="rounded-[18px] border border-dashed border-[#d8dbe4] bg-white p-12 text-center text-[#858b9c]">
              生成日报或周报后，在这里查看重大异常、今日待办和来源证据。
            </div>
          )}
          {selected && (
            <div className="space-y-5">
              <section className="rounded-[18px] border border-[#e6e8ee] bg-white p-5">
                <div className="flex flex-wrap items-start justify-between gap-4">
                  <div>
                    <div className="flex items-center gap-2">
                      <h2 className="text-[20px] font-semibold text-[#202331]">{selected.title}</h2>
                      <span className={cn(
                        'rounded-full px-2.5 py-1 text-[11px]',
                        selected.status === 'confirmed' ? 'bg-[#e9f7f1] text-[#25745f]' : selected.status === 'rejected' ? 'bg-[#fff0f0] text-[#a33a3a]' : 'bg-[#fff6df] text-[#946c18]',
                      )}>{STATUS_LABELS[selected.status]}</span>
                      <span className="rounded-full bg-[#f0f2f7] px-2.5 py-1 text-[11px] text-[#667085]">数据 {selected.data_status}</span>
                    </div>
                    <p className="mt-2 text-[12px] text-[#858b9c]">截至 {formatTime(String(selected.metrics.data_as_of || selected.generated_at))} · {selected.source_count} 条可追溯来源</p>
                  </div>
                  {selected.status === 'draft' && (
                    <div className="flex gap-2">
                      <Button variant="outline" onClick={() => setReviewAction('rejected')}>驳回</Button>
                      <Button onClick={() => setReviewAction('confirmed')}>确认报告</Button>
                    </div>
                  )}
                </div>

                <div className="mt-5 grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
                  {Object.entries(METRIC_LABELS).map(([key, label]) => (
                    <div key={key} className="rounded-[13px] bg-[#f7f8fa] px-4 py-3">
                      <strong className="block text-[22px] text-[#252938]">{Number(selected.metrics[key] || 0)}</strong>
                      <span className="text-[11px] text-[#858b9c]">{label}</span>
                    </div>
                  ))}
                </div>
              </section>

              <div className="grid gap-5 lg:grid-cols-2">
                <section className="rounded-[18px] border border-[#e6e8ee] bg-white p-5">
                  <h3 className="text-[15px] font-semibold text-[#303444]">重大异常与今日必须处理</h3>
                  <div className="mt-4 space-y-3">
                    {majorExceptions.length === 0 && <p className="text-[13px] text-[#858b9c]">当前没有带证据的重大异常。</p>}
                    {majorExceptions.map((item, index) => (
                      <div key={`${String(item.source_id)}-${index}`} className="rounded-[12px] border border-[#f0dede] bg-[#fff9f9] px-4 py-3">
                        <span className="text-[11px] font-medium uppercase text-[#a33a3a]">{String(item.severity)}</span>
                        <p className="mt-1 text-[13px] text-[#464c5e]">{String(item.summary)}</p>
                      </div>
                    ))}
                  </div>
                </section>

                <section className="rounded-[18px] border border-[#e6e8ee] bg-white p-5">
                  <h3 className="text-[15px] font-semibold text-[#303444]">数据完整性</h3>
                  <div className="mt-4 space-y-3">
                    {dataWarnings.length === 0 && <p className="text-[13px] text-[#25745f]">本周期主要数据源均有记录。</p>}
                    {dataWarnings.map((warning) => (
                      <p key={warning} className="rounded-[12px] bg-[#fff8e8] px-4 py-3 text-[13px] text-[#80621f]">{warning}</p>
                    ))}
                  </div>
                </section>
              </div>

              <section className="rounded-[18px] border border-[#e6e8ee] bg-white p-5">
                <h3 className="text-[15px] font-semibold text-[#303444]">各岗位执行情况</h3>
                <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                  {roleActivity.length === 0 && <p className="text-[13px] text-[#858b9c]">暂无岗位运行记录。</p>}
                  {roleActivity.map((item) => (
                    <div key={String(item.name)} className="rounded-[12px] bg-[#f7f8fa] px-4 py-3">
                      <strong className="text-[13px] text-[#303444]">{String(item.name)}</strong>
                      <p className="mt-1 text-[12px] text-[#858b9c]">总计 {Number(item.total || 0)} 次</p>
                    </div>
                  ))}
                </div>
                {rootCauses.length > 0 && (
                  <div className="mt-5 border-t border-[#eceef2] pt-4">
                    <h4 className="text-[13px] font-semibold text-[#464c5e]">重复根因</h4>
                    <div className="mt-2 flex flex-wrap gap-2">
                      {rootCauses.map((item) => <span key={String(item.code)} className="rounded-full bg-[#f0f2f7] px-3 py-1 text-[12px]">{String(item.code)} · {Number(item.count)}</span>)}
                    </div>
                  </div>
                )}
              </section>

              <section className="rounded-[18px] border border-[#e6e8ee] bg-white p-5">
                <div className="flex items-center justify-between gap-3">
                  <h3 className="text-[15px] font-semibold text-[#303444]">来源证据</h3>
                  <Button variant="outline" onClick={() => setFollowUpOpen(true)}>创建后续任务</Button>
                </div>
                <div className="mt-4 divide-y divide-[#eceef2]">
                  {selected.sources.length === 0 && <p className="py-4 text-[13px] text-[#858b9c]">暂无可引用来源；报告不会据此生成趋势判断。</p>}
                  {selected.sources.map((source) => (
                    <a key={source.id} href={source.source_route} className="flex items-start justify-between gap-4 py-3 hover:bg-[#fafbfc]">
                      <div className="min-w-0">
                        <div className="flex items-center gap-2"><span className="rounded-full bg-[#eef3ff] px-2 py-0.5 text-[11px] text-[#315ea8]">{source.label}</span><span className="truncate text-[13px] text-[#303444]">{source.summary}</span></div>
                        <p className="mt-1 text-[11px] text-[#858b9c]">{source.business_key}</p>
                      </div>
                      <span className="shrink-0 text-[11px] text-[#858b9c]">{formatTime(source.occurred_at)}</span>
                    </a>
                  ))}
                </div>
              </section>

              <section className="rounded-[18px] border border-[#e6e8ee] bg-white p-5">
                <h3 className="text-[15px] font-semibold text-[#303444]">管理批注与后续任务</h3>
                <div className="mt-4 space-y-3">
                  {selected.comments.map((item) => (
                    <div key={item.id} className="rounded-[12px] bg-[#f7f8fa] px-4 py-3">
                      <div className="flex justify-between gap-3 text-[11px] text-[#858b9c]"><span>{item.action_type} · {item.author_business_role}</span><span>{formatTime(item.created_at)}</span></div>
                      <p className="mt-1 text-[13px] text-[#464c5e]">{item.body}</p>
                      {item.action_type === 'follow_up_created' && <p className="mt-1 text-[11px] text-[#315ea8]">负责人：{String(item.detail.owner_business_role || '-')} · 优先级：{String(item.detail.priority || '-')}{typeof item.detail.task_route === 'string' && <a className="ml-3 underline" href={item.detail.task_route}>打开真实任务</a>}</p>}
                    </div>
                  ))}
                </div>
                <div className="mt-4 flex gap-3">
                  <Textarea value={comment} onChange={(event) => setComment(event.target.value)} placeholder="追加管理批注；批注不会自动修改已发布 SOP" rows={2} />
                  <Button disabled={busy} onClick={() => void submitComment()}>追加批注</Button>
                </div>
              </section>
            </div>
          )}
        </main>
      </div>

      <Dialog open={Boolean(reviewAction)} onOpenChange={(open) => !open && setReviewAction(null)}>
        <DialogContent>
          <DialogTitle>{reviewAction === 'confirmed' ? '确认运营报告' : '驳回运营报告'}</DialogTitle>
          <p className="text-[13px] text-[#667085]">评审只追加管理意见，不修改报告中的来源证据。</p>
          <Textarea rows={4} value={reviewNote} onChange={(event) => setReviewNote(event.target.value)} placeholder="填写评审依据和后续约束" />
          <DialogFooter><Button variant="outline" onClick={() => setReviewAction(null)}>取消</Button><Button disabled={busy} onClick={() => void submitReview()}>确认提交</Button></DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={followUpOpen} onOpenChange={setFollowUpOpen}>
        <DialogContent>
          <DialogTitle>创建报告后续任务</DialogTitle>
          <Input value={followUpTitle} onChange={(event) => setFollowUpTitle(event.target.value)} placeholder="例如：核对物流异常并补充承运商回执" />
          <label className="space-y-2 text-[13px]">负责人岗位
            <select className="h-10 w-full rounded-md border border-input bg-background px-3" value={followUpRole} onChange={(event) => setFollowUpRole(event.target.value)}>
              {ROLE_OPTIONS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select>
          </label>
          <label className="space-y-2 text-[13px]">优先级
            <select className="h-10 w-full rounded-md border border-input bg-background px-3" value={followUpPriority} onChange={(event) => setFollowUpPriority(event.target.value)}>
              <option value="normal">普通</option><option value="high">高</option><option value="urgent">紧急</option><option value="low">低</option>
            </select>
          </label>
          <p className="text-[12px] text-[#858b9c]">系统会自动关联当前报告中的高风险来源，任务不会触发外部写操作。</p>
          <DialogFooter><Button variant="outline" onClick={() => setFollowUpOpen(false)}>取消</Button><Button disabled={busy} onClick={() => void submitFollowUp()}>创建任务</Button></DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
