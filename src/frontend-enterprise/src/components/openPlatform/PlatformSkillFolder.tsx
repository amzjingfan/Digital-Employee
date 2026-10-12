import { useState, type ReactNode } from 'react';

import IconFolder from '../../assets/icons/cap-folder.svg?react';

export default function PlatformSkillFolder({
  name,
  count,
  compact = false,
  forceOpen = false,
  children,
}: {
  name: string;
  count: number;
  compact?: boolean;
  forceOpen?: boolean;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const expanded = forceOpen || open;
  return (
    <section className="rounded-[14px] border border-[#dfe6f5] bg-[#f8faff] p-[10px]">
      <button
        type="button"
        aria-expanded={expanded}
        onClick={() => setOpen((value) => !value)}
        className="flex w-full items-center gap-[8px] rounded-[10px] bg-white px-[10px] py-[12px] text-left text-[12px] text-[#464c5e]"
      >
        <IconFolder className="size-[18px] shrink-0 text-[#1a71ff]" />
        <span className="min-w-0 flex-1 truncate font-medium">{name}</span>
        <span className="shrink-0 text-[#757f9c]">{count} 个技能</span>
        <span aria-hidden="true" className="text-[#757f9c]">{expanded ? '⌃' : '⌄'}</span>
      </button>
      {expanded && (
        <div className={compact
          ? 'mt-[10px] flex flex-col gap-[10px]'
          : 'mt-[12px] grid grid-cols-1 gap-[16px] sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-5'}>
          {children}
        </div>
      )}
    </section>
  );
}
