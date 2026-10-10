import {
  Dialog,
  DialogContent,
  DialogTitle,
} from '@/components/ui';
import { Button } from '@/components/ui/button';

type Props = {
  choices: string[] | null;
  selectedPaths: string[];
  loading: boolean;
  error: string;
  onSelectedChange: (paths: string[]) => void;
  onImport: () => void;
  onClose: () => void;
};

export default function SkillFolderSelectionDialog({
  choices,
  selectedPaths,
  loading,
  error,
  onSelectedChange,
  onImport,
  onClose,
}: Props) {
  const allSelected = Boolean(choices?.length) && selectedPaths.length === choices?.length;
  return (
    <Dialog open={Boolean(choices)} onOpenChange={(open) => { if (!open && !loading) onClose(); }}>
      <DialogContent aria-describedby={undefined} className="flex w-[calc(100%-2rem)] flex-col gap-0 overflow-hidden rounded-[16px] p-0 sm:max-w-[520px]">
        <DialogTitle className="border-b border-border px-[24px] py-[16px] text-[16px] font-semibold text-foreground">
          选择要导入的技能
        </DialogTitle>
        <p className="px-[24px] pt-[16px] text-[13px] text-muted-foreground">
          找到 {choices?.length || 0} 个 SKILL.md。请选择要导入的子技能。导入后立即启用，失败时整批不保存。
        </p>
        <div className="flex items-center justify-between px-[24px] pt-[12px] text-[13px]">
          <label className="flex cursor-pointer items-center gap-[8px]">
            <input
              type="checkbox"
              checked={allSelected}
              disabled={loading}
              onChange={(event) => onSelectedChange(event.target.checked ? [...(choices || [])] : [])}
            />
            全选
          </label>
          <span className="text-muted-foreground">已选择 {selectedPaths.length} 项</span>
        </div>
        <div className="max-h-[360px] overflow-y-auto px-[24px] py-[16px]">
          {choices?.map((path) => (
            <label
              key={path}
              className="mb-[8px] flex cursor-pointer items-center gap-[10px] rounded-[8px] border border-border px-[12px] py-[10px] text-[13px]"
            >
              <input
                type="checkbox"
                checked={selectedPaths.includes(path)}
                disabled={loading}
                onChange={(event) => onSelectedChange(event.target.checked
                  ? [...selectedPaths, path]
                  : selectedPaths.filter((item) => item !== path))}
              />
              <span className="min-w-0 break-all">{path.replace(/\/?SKILL\.md$/i, '') || '根目录'}</span>
            </label>
          ))}
        </div>
        {error && <p role="alert" className="px-[24px] pb-[8px] text-[12px] text-destructive">{error}</p>}
        <div className="flex justify-end gap-[8px] bg-background px-[24px] py-[12px]">
          <Button variant="outline" disabled={loading} onClick={onClose}>取消</Button>
          <Button disabled={loading || !selectedPaths.length} onClick={onImport}>
            {loading ? '正在导入…' : `导入选中（${selectedPaths.length}）`}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
