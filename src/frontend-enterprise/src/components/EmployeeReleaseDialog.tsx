import {
  Button,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  notify,
} from '@/components/ui';
import { GitCompare, History, LoaderCircle, Rocket, RotateCcw } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';

import { api, TENANT_ID } from '../api/client';
import { employeeDisplayName } from '../employee';
import type { AgentProfileRead, AgentReleaseDiffRead, AgentReleaseRead } from '../types';

export default function EmployeeReleaseDialog({
  agent,
  open,
  canPublish,
  onClose,
  onChanged,
}: {
  agent: AgentProfileRead | null;
  open: boolean;
  canPublish: boolean;
  onClose: () => void;
  onChanged: () => void;
}) {
  const [releases, setReleases] = useState<AgentReleaseRead[]>([]);
  const [reason, setReason] = useState('');
  const [loading, setLoading] = useState(false);
  const [acting, setActing] = useState(false);
  const [diff, setDiff] = useState<AgentReleaseDiffRead | null>(null);
  const displayName = useMemo(() => (agent ? employeeDisplayName(agent) : '数字员工'), [agent]);

  async function load() {
    if (!agent) return;
    setLoading(true);
    try {
      setReleases(await api.get<AgentReleaseRead[]>(
        `/api/enterprise/agents/${encodeURIComponent(agent.id)}/releases?tenant_id=${encodeURIComponent(TENANT_ID)}`,
      ));
    } catch (error) {
      notify.error(error instanceof Error ? error.message : '加载员工版本失败');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (!open || !agent) return;
    setReason('');
    setDiff(null);
    void load();
  }, [agent, open]);

  async function publish() {
    if (!agent || reason.trim().length < 3) return;
    setActing(true);
    try {
      await api.post(`/api/enterprise/agents/${encodeURIComponent(agent.id)}/releases/publish`, {
        tenant_id: TENANT_ID,
        reason: reason.trim(),
      });
      notify.success('数字员工生产版本已发布');
      setReason('');
      await load();
      onChanged();
    } catch (error) {
      notify.error(error instanceof Error ? error.message : '发布员工版本失败');
    } finally {
      setActing(false);
    }
  }

  async function rollback(row: AgentReleaseRead) {
    if (!agent || reason.trim().length < 3) {
      notify.error('回滚前请填写至少 3 个字的原因');
      return;
    }
    if (!window.confirm(`确认将「${displayName}」回滚到 v${row.version}？系统会生成一个新的生产版本。`)) return;
    setActing(true);
    try {
      await api.post(
        `/api/enterprise/agents/${encodeURIComponent(agent.id)}/releases/${encodeURIComponent(row.id)}/rollback`,
        { tenant_id: TENANT_ID, reason: reason.trim() },
      );
      notify.success(`已回滚并发布新版本`);
      setReason('');
      setDiff(null);
      await load();
      onChanged();
    } catch (error) {
      notify.error(error instanceof Error ? error.message : '回滚员工版本失败');
    } finally {
      setActing(false);
    }
  }

  async function compare(row: AgentReleaseRead, older: AgentReleaseRead) {
    if (!agent) return;
    setLoading(true);
    try {
      const query = new URLSearchParams({
        tenant_id: TENANT_ID,
        left_release_id: older.id,
        right_release_id: row.id,
      });
      setDiff(await api.get<AgentReleaseDiffRead>(
        `/api/enterprise/agents/${encodeURIComponent(agent.id)}/release-diff?${query.toString()}`,
      ));
    } catch (error) {
      notify.error(error instanceof Error ? error.message : '加载版本差异失败');
    } finally {
      setLoading(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={(next) => { if (!next && !acting) onClose(); }}>
      <DialogContent className="flex max-h-[calc(100dvh-3rem)] w-[calc(100%-2rem)] flex-col gap-0 overflow-hidden rounded-[18px] border-0 bg-[#f7f8fa] p-0 sm:max-w-[820px]">
        <DialogHeader className="border-b border-[#e9ecf2] bg-white px-[26px] py-[22px]">
          <DialogTitle className="flex items-center gap-[9px] text-[16px] text-[#18181a]">
            <History className="size-[18px]" />版本发布 · <span data-i18n-ignore>{displayName}</span>
          </DialogTitle>
          <DialogDescription className="mt-[5px] text-[12px] text-[#757f9c]">
            发布后固定员工档案、SOP、知识库和工具版本；配置变化会自动回到待发布状态。
          </DialogDescription>
        </DialogHeader>

        <div className="min-h-0 flex-1 space-y-[16px] overflow-y-auto px-[26px] py-[22px]">
          <section className="rounded-[15px] border border-[#e3e7ef] bg-white p-[16px]">
            <div className="flex flex-wrap items-center justify-between gap-[10px]">
              <div>
                <strong className="text-[13px] text-[#20242d]">
                  当前状态：{agent?.release_state === 'published' ? `生产 v${agent.published_release_version || 0}` : '待发布'}
                </strong>
                <p className="mt-[4px] text-[11px] text-[#7d8597]">只有租户管理员可签署生产发布或回滚。</p>
              </div>
              <Button
                type="button"
                disabled={!canPublish || acting || reason.trim().length < 3}
                onClick={() => void publish()}
                className="h-[34px] rounded-[10px] bg-[#18181a] px-[13px] text-[11px] text-white"
              >
                {acting ? <LoaderCircle className="size-[13px] animate-spin" /> : <Rocket className="size-[13px]" />}
                发布生产版本
              </Button>
            </div>
            <textarea
              value={reason}
              onChange={(event) => setReason(event.target.value)}
              placeholder="填写发布或回滚原因（至少 3 个字）"
              aria-label="发布或回滚原因"
              className="mt-[12px] min-h-[70px] w-full resize-y rounded-[11px] border border-[#e1e5ed] bg-[#fafbfc] px-[11px] py-[9px] text-[12px] outline-none focus:border-[#9aa5bb]"
            />
          </section>

          <section className="overflow-hidden rounded-[15px] border border-[#e3e7ef] bg-white">
            {loading && !releases.length ? (
              <div className="grid h-[100px] place-items-center"><LoaderCircle className="size-[18px] animate-spin" /></div>
            ) : releases.length ? releases.map((row, index) => {
              const older = releases[index + 1];
              return (
                <article key={row.id} className={index ? 'border-t border-[#edf0f4] px-[16px] py-[14px]' : 'px-[16px] py-[14px]'}>
                  <div className="flex flex-wrap items-center gap-[8px]">
                    <strong className="text-[12px] text-[#20242d]">v{row.version}</strong>
                    <span className={row.status === 'published' ? 'rounded-full bg-[#e8f7ec] px-[7px] py-[2px] text-[9px] text-[#218546]' : 'rounded-full bg-[#f0f2f5] px-[7px] py-[2px] text-[9px] text-[#7d8597]'}>
                      {row.status === 'published' ? '生效中' : '历史版本'}
                    </span>
                    <code className="text-[9px] text-[#9299a8]">{row.snapshot_digest.slice(0, 19)}…</code>
                    <span className="ml-auto text-[10px] text-[#9299a8]">{formatDate(row.published_at)}</span>
                  </div>
                  <p className="mt-[6px] text-[11px] text-[#5f687b]" data-i18n-ignore>{row.release_reason}</p>
                  <div className="mt-[9px] flex flex-wrap gap-[7px]">
                    {older && (
                      <Button type="button" variant="outline" disabled={loading} onClick={() => void compare(row, older)} className="h-[28px] rounded-[8px] px-[8px] text-[10px]">
                        <GitCompare className="size-[11px]" />查看差异
                      </Button>
                    )}
                    {row.status !== 'published' && canPublish && (
                      <Button type="button" variant="outline" disabled={acting} onClick={() => void rollback(row)} className="h-[28px] rounded-[8px] px-[8px] text-[10px]">
                        <RotateCcw className="size-[11px]" />回滚到此版本
                      </Button>
                    )}
                  </div>
                </article>
              );
            }) : (
              <div className="flex h-[100px] flex-col items-center justify-center text-[11px] text-[#8a92a3]">
                <History className="mb-[7px] size-[18px]" />尚无生产版本
              </div>
            )}
          </section>

          {diff && (
            <section className="rounded-[15px] border border-[#dfe4ed] bg-white p-[16px]">
              <h3 className="text-[12px] font-semibold text-[#252932]">版本差异（{diff.changes.length} 项）</h3>
              <div className="mt-[9px] max-h-[220px] overflow-auto rounded-[10px] bg-[#f7f8fa] p-[10px]">
                {diff.changes.length ? diff.changes.map((change) => (
                  <div key={change.path} className="border-b border-[#e6e9ef] py-[7px] last:border-0">
                    <code className="text-[10px] font-semibold text-[#4f596d]">{change.path}</code>
                    <pre className="mt-[4px] whitespace-pre-wrap break-all text-[9px] text-[#7d8597]">{renderValue(change.before)} → {renderValue(change.after)}</pre>
                  </div>
                )) : <p className="text-[10px] text-[#8a92a3]">两个版本没有配置差异。</p>}
              </div>
            </section>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}

function renderValue(value: unknown): string {
  if (value === undefined) return '∅';
  return typeof value === 'string' ? value : JSON.stringify(value);
}

function formatDate(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit',
  }).format(date);
}
