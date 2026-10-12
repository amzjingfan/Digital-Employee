import type { PlatformDetailItem } from './PlatformKindDetailView';

export type SkillGroup = { key: string; name?: string; items: PlatformDetailItem[] };

export function groupSkillItems(items: PlatformDetailItem[]): SkillGroup[] {
  const groups = new Map<string, SkillGroup>();
  for (const item of items) {
    const key = item.groupId && item.groupName ? `group:${item.groupId}` : `skill:${item.id}`;
    const group = groups.get(key);
    if (group) {
      group.items.push(item);
    } else {
      groups.set(key, { key, name: item.groupName, items: [item] });
    }
  }
  return [...groups.values()];
}
