import type { ComponentType, ReactNode, SVGProps } from 'react';
import { useMemo, useState } from 'react';

import AppHeader from '@/components/AppHeader';
import { StatCard } from '@/components/StatCard';
import { Button as UIButton } from '@/components/ui/button';
import { cn } from '@/lib/utils';

const RETURN_BUTTON_CLASS =
  'h-8 gap-1 rounded-[10px] border-[0.5px] border-[#e3e7f1] bg-white px-5 text-[12px] font-normal text-[#757f9c] hover:border-[#cbd3e6] hover:bg-white hover:text-[#18181a]';

import IconArrowRight from '../../assets/icons/arrow-right.svg?react';
import IconAdd from '../../assets/icons/add.svg?react';
import IconRefresh from '../../assets/icons/refresh.svg?react';
import IconSearch from '../../assets/icons/search.svg?react';
import plazaKnowledgeIcon from '../../assets/icons/plaza-knowledge.svg';
import plazaSkillIcon from '../../assets/icons/plaza-skill.svg';
import plazaSopIcon from '../../assets/icons/plaza-sop.svg';
import plazaToolIcon from '../../assets/icons/plaza-tool.svg';
import EmployeeAvatar from '../EmployeeAvatar';
import type { AgentProfileRead } from '../../types';

import PlatformEmployeeCard, { type PlatformStat } from './PlatformEmployeeCard';
import PlatformResourceCard, { type PlatformResourceAccent } from './PlatformResourceCard';
import PlatformSkillFolder from './PlatformSkillFolder';
import { groupSkillItems } from './skillGroups';

export type PlatformDetailKind = 'agents' | 'knowledge' | 'general-skills' | 'skills' | 'tools';

export type PlatformDetailItem = {
  id: string;
  title: string;
  description: string;
  meta: string;
  tags: string[];
  groupId?: string;
  groupName?: string;
  agent?: AgentProfileRead;
};

const PLATFORM_RESOURCE_ICON: Partial<Record<PlatformDetailKind, string>> = {
  knowledge: plazaKnowledgeIcon,
  'general-skills': plazaSkillIcon,
  skills: plazaSopIcon,
  tools: plazaToolIcon,
};

const PLATFORM_ACCENT: Partial<Record<PlatformDetailKind, PlatformResourceAccent>> = {
  knowledge: 'green',
  'general-skills': 'indigo',
  skills: 'blue',
  tools: 'orange',
};

export type PlatformKindDetailViewProps = {
  kind: PlatformDetailKind;
  title: string;
  subtitle: string;
  countLabel: string;
  signals: string[];
  icon: ComponentType<SVGProps<SVGSVGElement>>;
  items: PlatformDetailItem[];
  loading: boolean;
  employeeStats: (agent: AgentProfileRead) => PlatformStat[];
  onBack: () => void;
  onRefresh: () => void;
  createLabel?: string;
  onCreate?: () => void;
  onOpenItem: (item: PlatformDetailItem) => void;
  onGroupSkills?: (ids: string[], name: string) => Promise<void>;
  canManage?: boolean;
  unpublishingItemId?: string;
  onUnpublishItem?: (item: PlatformDetailItem) => void;
  onLogout?: () => void;
  userName?: string;
};

function DetailSkeleton({ kind }: { kind: PlatformDetailKind }) {
  const cardHeight = kind === 'agents' ? 'h-[140px]' : 'h-[112px]';
  return (
    <div className="grid grid-cols-1 gap-[16px] sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-5">
      {Array.from({ length: 8 }, (_, index) => (
        <div
          key={index}
          className={cn(
            'w-full animate-pulse rounded-[20px] border-[0.5px] border-[#f0f1f5] bg-[#f6f6f6]',
            cardHeight,
          )}
        />
      ))}
    </div>
  );
}

/**
 * Full-list view for a single 开放广场 module (/enterprise/platform/:kind).
 * Mirrors the main platform page card system inside the standard enterprise page shell.
 */
export default function PlatformKindDetailView({
  kind,
  title,
  subtitle,
  countLabel,
  signals,
  icon: PlatformIcon,
  items,
  loading,
  employeeStats,
  onBack,
  onRefresh,
  createLabel = '创建开放 Skill',
  onCreate,
  onOpenItem,
  onGroupSkills,
  canManage = false,
  unpublishingItemId,
  onUnpublishItem,
  onLogout,
  userName,
}: PlatformKindDetailViewProps) {
  const [searchText, setSearchText] = useState('');
  const [grouping, setGrouping] = useState(false);
  const [selectedSkillIds, setSelectedSkillIds] = useState<string[]>([]);
  const [folderName, setFolderName] = useState('');
  const [savingGroup, setSavingGroup] = useState(false);
  const [groupError, setGroupError] = useState('');

  const filteredItems = useMemo(() => {
    const keyword = searchText.trim().toLowerCase();
    if (!keyword) return items;
    return items.filter((item) => [
      item.title,
      item.description,
      item.meta,
      item.groupName || '',
      item.tags.join(' '),
    ].some((value) => value.toLowerCase().includes(keyword)));
  }, [items, searchText]);

  const groupedSkills = useMemo(
    () => kind === 'general-skills' ? groupSkillItems(filteredItems) : [],
    [filteredItems, kind],
  );

  async function saveGroup() {
    if (!onGroupSkills || selectedSkillIds.length < 2 || !folderName.trim()) return;
    setSavingGroup(true);
    setGroupError('');
    try {
      await onGroupSkills(selectedSkillIds, folderName.trim());
      setGrouping(false);
      setSelectedSkillIds([]);
      setFolderName('');
    } catch (error) {
      setGroupError(error instanceof Error ? error.message : '保存分组失败');
    } finally {
      setSavingGroup(false);
    }
  }

  function renderSkill(item: PlatformDetailItem) {
    return (
      <div key={item.id} className="relative min-w-0">
        <PlatformResourceCard
          icon={<img src={plazaSkillIcon} alt="" className="size-[32px] shrink-0 object-contain" />}
          accent="indigo"
          title={item.title}
          meta={item.meta}
          description={item.description}
          tags={item.tags.slice(0, 2)}
          onClick={() => onOpenItem(item)}
        />
        {grouping && (
          <label className="absolute right-[8px] top-[8px] flex items-center gap-[4px] rounded-[8px] bg-white px-[6px] py-[4px] text-[11px] shadow-sm">
            <input
              type="checkbox"
              aria-label={`选择 ${item.title}`}
              checked={selectedSkillIds.includes(item.id)}
              onChange={(event) => setSelectedSkillIds((current) => event.target.checked
                ? [...current, item.id]
                : current.filter((id) => id !== item.id))}
            />
            选择
          </label>
        )}
      </div>
    );
  }

  return (
    <div className="min-h-full box-border px-[48px] pt-[32px] pb-[43px] max-[900px]:px-[16px]" aria-busy={loading}>
      <AppHeader
        onLogout={onLogout}
        userName={userName}
        title={title}
        description={subtitle}
      />

      <div className="mt-[20px] mb-[16px] flex flex-wrap justify-end gap-[16px]">
        <UIButton variant="outline" onClick={onBack} className={RETURN_BUTTON_CLASS}>
          <IconArrowRight className="size-3.5 rotate-180" />
          返回开放广场
        </UIButton>
        {onCreate && (
          <UIButton onClick={onCreate} className="h-8 gap-1 rounded-[10px] bg-[#18181a] px-5 text-[12px] font-normal text-white hover:bg-[#303030]">
            <IconAdd className="size-3.5" />
            {createLabel}
          </UIButton>
        )}
        <UIButton
          variant="outline"
          onClick={onRefresh}
          disabled={loading}
          className={RETURN_BUTTON_CLASS}
        >
          <IconRefresh className={cn('size-[14px]', loading && 'animate-spin')} />
          刷新
        </UIButton>
      </div>

      <div className="flex flex-col gap-[24px] rounded-[20px] bg-white p-[18px_18px_24px_18px] shadow-[0_-4px_16px_0_rgba(0,0,0,0.05)]">
        <div className="flex flex-wrap items-stretch gap-[20px]" aria-label={`${title}统计`}>
          <StatCard value={items.length} label={countLabel} className="max-w-[220px]" />
        </div>

        <div className="flex flex-col gap-[18px]">
          <div className="flex items-center gap-[6px] px-[12px] text-[#757f9c]">
            <PlatformIcon className="size-[14px] shrink-0" />
            <span className="text-[14px] font-normal leading-none">{title}</span>
          </div>

          {signals.length > 0 && (
            <div className="flex flex-wrap items-center gap-[6px] px-[12px]">
              {signals.map((signal) => (
                <span
                  key={signal}
                  className="rounded-[20px] border-[0.5px] border-[#e3e7f1] px-[8px] py-[2px] text-[10px] leading-[normal] text-[#757f9c]"
                >
                  {signal}
                </span>
              ))}
            </div>
          )}

          <label className="flex h-[34px] w-full max-w-[360px] items-center gap-[8px] overflow-hidden rounded-[10px] border-[0.5px] border-[#e3e7f1] bg-white px-[12px] transition-colors focus-within:border-[#18181a]">
            <IconSearch className="size-[14px] shrink-0 text-[#858b9c]" />
            <input
              autoComplete="off"
              data-1p-ignore="true"
              data-lpignore="true"
              data-bwignore="true"
              value={searchText}
              placeholder={`搜索${countLabel}`}
              onChange={(event) => setSearchText(event.target.value)}
              className="min-w-0 flex-1 border-0 bg-transparent text-[12px] text-[#18181a] outline-none placeholder:text-[#858b9c]"
            />
          </label>

          {kind === 'general-skills' && onGroupSkills && (
            <div className="flex flex-wrap items-center gap-[8px] px-[12px]">
              <UIButton variant="outline" onClick={() => {
                setGrouping((current) => !current);
                setSelectedSkillIds([]);
                setGroupError('');
              }}>
                {grouping ? '取消整理' : '整理已有 Skill'}
              </UIButton>
              {grouping && (
                <>
                  <label className="text-[12px] text-[#464c5e]">
                    文件夹名称
                    <input
                      className="ml-[8px] h-[34px] rounded-[8px] border border-[#dfe4ec] px-[8px]"
                      value={folderName}
                      maxLength={100}
                      onChange={(event) => setFolderName(event.target.value)}
                    />
                  </label>
                  <span className="text-[12px] text-[#757f9c]">已选 {selectedSkillIds.length} 个</span>
                  <UIButton disabled={savingGroup || selectedSkillIds.length < 2 || !folderName.trim()} onClick={() => void saveGroup()}>
                    保存分组
                  </UIButton>
                </>
              )}
              {groupError && <span role="alert" className="text-[12px] text-red-600">{groupError}</span>}
            </div>
          )}

          {loading ? (
            <DetailSkeleton kind={kind} />
          ) : filteredItems.length === 0 ? (
            <div className="grid min-h-[180px] w-full place-items-center content-center gap-[10px] rounded-[18px] border border-dashed border-[#dfe4ec] bg-[#fbfcfd] px-[20px] py-[40px] text-center font-bold text-[#8b94aa]">
              <IconSearch className="size-[20px] shrink-0" />
              <span>{items.length === 0 ? '暂无开放内容' : '没有匹配的广场内容'}</span>
            </div>
          ) : kind === 'agents' ? (
            <div className="grid grid-cols-1 gap-[16px] sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-5">
              {filteredItems.map((item) => item.agent && (
                <PlatformEmployeeCard
                  key={item.id}
                  avatar={(
                    <EmployeeAvatar
                      agent={item.agent}
                      width={50}
                      height={59}
                      fit="contain"
                      objectPosition="center bottom"
                      className="overflow-visible! rounded-none! border-0! bg-transparent! bg-none! shadow-none! after:hidden!"
                    />
                  )}
                  name={item.title}
                  role={item.meta}
                  online={item.agent.status === 'active'}
                  description={item.description}
                  stats={employeeStats(item.agent)}
                  onOpen={() => onOpenItem(item)}
                  onUnpublish={canManage && onUnpublishItem ? () => onUnpublishItem(item) : undefined}
                  unpublishing={unpublishingItemId === item.id}
                />
              ))}
            </div>
          ) : kind === 'general-skills' ? (
            <div className="grid grid-cols-1 gap-[16px] sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-5">
              {groupedSkills.map((group) => group.name && group.items.length > 1 ? (
                <div key={group.key} className="col-span-full">
                  <PlatformSkillFolder name={group.name} count={group.items.length} forceOpen={Boolean(searchText.trim()) || grouping}>
                    {group.items.map(renderSkill)}
                  </PlatformSkillFolder>
                </div>
              ) : group.items.map(renderSkill))}
            </div>
          ) : (
            <div className="grid grid-cols-1 gap-[16px] sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-5">
              {filteredItems.map((item) => (
                <PlatformResourceCard
                  key={item.id}
                  icon={PLATFORM_RESOURCE_ICON[kind]
                    ? <img src={PLATFORM_RESOURCE_ICON[kind]} alt="" className="size-[32px] shrink-0 object-contain" />
                    : undefined}
                  accent={PLATFORM_ACCENT[kind]}
                  title={item.title}
                  meta={item.meta}
                  description={item.description}
                  tags={item.tags.slice(0, 2)}
                  onClick={() => onOpenItem(item)}
                />
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
