import { describe, expect, it } from 'vitest';

import { groupSkillItems } from '@/components/openPlatform/skillGroups';

function skill(id: string, groupId?: string, groupName?: string) {
  return { id, title: id, description: '', meta: id, tags: [], groupId, groupName };
}

describe('skill groups', () => {
  it('groups by identity and leaves ungrouped or singleton skills visible', () => {
    const groups = groupSkillItems([
      skill('one', 'a', 'HR'),
      skill('solo'),
      skill('two', 'a', 'HR'),
      skill('other', 'b', 'HR'),
    ]);

    expect(groups.map((group) => group.items.map((item) => item.id))).toEqual([
      ['one', 'two'], ['solo'], ['other'],
    ]);
    expect(groups[0].name).toBe('HR');
    expect(groups[2].key).not.toBe(groups[0].key);
  });
});
