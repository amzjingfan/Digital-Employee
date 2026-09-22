import { useMemo, useState } from 'react';

import { api } from '@/api/client';
import { Button } from '@/components/ui/button';

import type {
  ValidationOption,
  ValidationRun,
  ValidationScope,
} from './dataValidationTypes';

const MAX_RECORDED_FILE_BYTES = 2 * 1024 * 1024;
const controlClass = 'min-h-9 rounded-lg border border-[#d9deea] bg-white px-2 text-[12px] text-[#252936]';

type Props = {
  currentUserId: string;
  scope: ValidationScope | null;
  ownerOptions: ValidationOption[];
  onCompleted: (run: ValidationRun) => void | Promise<void>;
};

type Metadata = {
  sourceLabel: string;
  approvalRef: string;
  approverId: string;
  dataPeriodStart: string;
  dataPeriodEnd: string;
  replayAsOf: string;
  approvedAt: string;
  approvalValidUntil: string;
};

const initialMetadata: Metadata = {
  sourceLabel: '',
  approvalRef: '',
  approverId: '',
  dataPeriodStart: '',
  dataPeriodEnd: '',
  replayAsOf: '',
  approvedAt: '',
  approvalValidUntil: '',
};

function toUtc(value: string): string {
  return new Date(value).toISOString();
}

function readFileText(file: File): Promise<string> {
  if (typeof file.text === 'function') return file.text();
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.addEventListener('load', () => resolve(String(reader.result || '')));
    reader.addEventListener('error', () => reject(reader.error));
    reader.readAsText(file);
  });
}

export default function TikTokRecordedValidationForm({
  currentUserId,
  scope,
  ownerOptions,
  onCompleted,
}: Props) {
  const [metadata, setMetadata] = useState<Metadata>(initialMetadata);
  const [file, setFile] = useState<File | null>(null);
  const [fileInputKey, setFileInputKey] = useState(0);
  const [attested, setAttested] = useState(false);
  const [busy, setBusy] = useState(false);
  const [errorNotice, setErrorNotice] = useState('');
  const [successNotice, setSuccessNotice] = useState('');
  const approvers = useMemo(
    () => ownerOptions.filter((option) => option.id !== currentUserId),
    [currentUserId, ownerOptions],
  );
  const metadataComplete = Object.values(metadata).every((value) => value.trim().length > 0);
  const canSubmit = Boolean(
    scope?.status === 'active'
    && file
    && metadataComplete
    && attested
    && !busy,
  );

  function updateMetadata(field: keyof Metadata, value: string) {
    setMetadata((current) => ({ ...current, [field]: value }));
  }

  function clearFile() {
    setFile(null);
    setFileInputKey((value) => value + 1);
  }

  function selectFile(selected: File | undefined) {
    setErrorNotice('');
    setSuccessNotice('');
    if (!selected) {
      setFile(null);
      return;
    }
    if (selected.size > MAX_RECORDED_FILE_BYTES) {
      clearFile();
      setErrorNotice('文件超过 2 MiB 限制');
      return;
    }
    setFile(selected);
  }

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canSubmit || !file || !scope) return;
    setBusy(true);
    setErrorNotice('');
    setSuccessNotice('');
    try {
      let dataset: unknown;
      try {
        dataset = JSON.parse(await readFileText(file)) as unknown;
      } catch {
        setErrorNotice('JSON 文件格式无效');
        return;
      }
      const run = await api.post<ValidationRun>(
        '/api/enterprise/tiktok/data-validation/runs/recorded',
        {
          scope_revision: scope.revision,
          source_label: metadata.sourceLabel.trim(),
          approval_ref: metadata.approvalRef.trim(),
          approved_by_user_id: metadata.approverId,
          approved_at: toUtc(metadata.approvedAt),
          approval_valid_until: toUtc(metadata.approvalValidUntil),
          data_period_start: toUtc(metadata.dataPeriodStart),
          data_period_end: toUtc(metadata.dataPeriodEnd),
          replay_as_of: toUtc(metadata.replayAsOf),
          sanitization_attested: true,
          dataset,
        },
      );
      setSuccessNotice(run.status === 'passed' ? '录制回放验证通过' : '录制回放完成但数据质量未通过');
      await onCompleted(run);
    } catch {
      setErrorNotice('录制回放运行失败');
    } finally {
      clearFile();
      setBusy(false);
    }
  }

  return (
    <form className="mt-3 grid gap-3" onSubmit={(event) => void submit(event)}>
      {scope?.status !== 'active' && (
        <p className="m-0 text-[12px] text-[#98620a]">请先启用试点范围</p>
      )}
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        <label className="grid gap-1 text-[12px] text-[#4d596f]">
          选择脱敏 JSON
          <input
            key={fileInputKey}
            aria-label="选择脱敏 JSON"
            type="file"
            accept="application/json,.json"
            className={controlClass}
            onChange={(event) => selectFile(event.target.files?.[0])}
          />
        </label>
        <TextField label="来源标签" value={metadata.sourceLabel} onChange={(value) => updateMetadata('sourceLabel', value)} />
        <TextField label="审批引用" value={metadata.approvalRef} onChange={(value) => updateMetadata('approvalRef', value)} />
        <label className="grid gap-1 text-[12px] text-[#4d596f]">
          独立审批人
          <select
            aria-label="独立审批人"
            className={controlClass}
            value={metadata.approverId}
            onChange={(event) => updateMetadata('approverId', event.target.value)}
          >
            <option value="">未选择</option>
            {approvers.map((owner) => <option key={owner.id} value={owner.id}>{owner.label}</option>)}
          </select>
        </label>
        <DateTimeField label="数据开始时间" value={metadata.dataPeriodStart} onChange={(value) => updateMetadata('dataPeriodStart', value)} />
        <DateTimeField label="数据结束时间" value={metadata.dataPeriodEnd} onChange={(value) => updateMetadata('dataPeriodEnd', value)} />
        <DateTimeField label="回放基准时间" value={metadata.replayAsOf} onChange={(value) => updateMetadata('replayAsOf', value)} />
        <DateTimeField label="审批时间" value={metadata.approvedAt} onChange={(value) => updateMetadata('approvedAt', value)} />
        <DateTimeField label="审批有效期" value={metadata.approvalValidUntil} onChange={(value) => updateMetadata('approvalValidUntil', value)} />
      </div>
      <label className="flex items-start gap-2 text-[12px] text-[#4d596f]">
        <input
          type="checkbox"
          checked={attested}
          onChange={(event) => setAttested(event.target.checked)}
        />
        确认文件已脱敏并获准回放
      </label>
      {errorNotice && <div role="alert" className="rounded-lg bg-[#fff0f0] px-3 py-2 text-[12px] text-[#b42318]">{errorNotice}</div>}
      {successNotice && <div role="status" className="rounded-lg bg-[#f0faf4] px-3 py-2 text-[12px] text-[#18733d]">{successNotice}</div>}
      <div>
        <Button type="submit" disabled={!canSubmit}>运行录制回放</Button>
      </div>
    </form>
  );
}

function TextField({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <label className="grid gap-1 text-[12px] text-[#4d596f]">
      {label}
      <input
        aria-label={label}
        className={controlClass}
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
    </label>
  );
}

function DateTimeField({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <label className="grid gap-1 text-[12px] text-[#4d596f]">
      {label}
      <input
        aria-label={label}
        type="datetime-local"
        className={controlClass}
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
    </label>
  );
}
