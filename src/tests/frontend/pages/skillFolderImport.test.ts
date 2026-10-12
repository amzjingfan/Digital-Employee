import { describe, expect, it } from 'vitest';

import {
  listSkillFolderChoices,
  readSkillFolderFiles,
  readSelectedSkillFolders,
  skillFolderGroupName,
  selectSkillFolderEntries,
} from '@/lib/skill-folder-import';

function entry(path: string, content = '') {
  const encoded = new TextEncoder().encode(content);
  return {
    path,
    file: {
      name: path.split('/').pop() || path,
      size: encoded.byteLength,
      type: 'text/plain',
      arrayBuffer: async () => encoded.buffer,
    } as File,
  };
}

describe('skill folder import', () => {
  it('names a batch only when selected skills share the selected outer folder', () => {
    expect(skillFolderGroupName([
      'bundle/skills/one/SKILL.md', 'bundle/skills/two/SKILL.md',
    ])).toBe('bundle');
    expect(skillFolderGroupName(['first/one/SKILL.md', 'second/two/SKILL.md'])).toBeUndefined();
    expect(skillFolderGroupName(['SKILL.md', 'extras/one/SKILL.md'])).toBeUndefined();
    expect(skillFolderGroupName(['bundle/one/SKILL.md'])).toBeUndefined();
  });

  it('lists every child skill and scopes the chosen package to its own files', () => {
    const entries = [
      entry('bundle/skills/hr-one/SKILL.md', '# One'),
      entry('bundle/skills/hr-one/references/one.md', '# One reference'),
      entry('bundle/skills/hr-two/SKILL.md', '# Two'),
      entry('bundle/skills/hr-two/references/two.md', '# Two reference'),
      entry('bundle/README.md', '# Bundle'),
    ];

    expect(listSkillFolderChoices(entries)).toEqual([
      'bundle/skills/hr-one/SKILL.md',
      'bundle/skills/hr-two/SKILL.md',
    ]);
    expect(selectSkillFolderEntries(entries, 'bundle/skills/hr-two/SKILL.md').map((item) => item.path)).toEqual([
      'SKILL.md',
      'references/two.md',
    ]);
  });

  it('reads the chosen files as UTF-8 and rejects unreadable files', async () => {
    const selected = selectSkillFolderEntries([
      entry('package/SKILL.md', '# Skill'),
      entry('package/references/guide.md', '# Guide'),
    ], 'package/SKILL.md');

    expect((await readSkillFolderFiles(selected)).map((item) => item.path)).toEqual([
      'SKILL.md',
      'references/guide.md',
    ]);
    const invalid = {
      ...entry('package/references/broken.md'),
      file: {
        name: 'broken.md',
        size: 1,
        type: 'text/plain',
        arrayBuffer: async () => Uint8Array.of(0xff).buffer,
      } as File,
    };
    await expect(readSkillFolderFiles([entry('SKILL.md', '# Skill'), invalid])).rejects.toThrow('UTF-8');
  });

  it('does not include a nested skill when the root skill is chosen', () => {
    const entries = [
      entry('SKILL.md', '# Root'),
      entry('references/root.md', '# Root reference'),
      entry('extras/child/SKILL.md', '# Child'),
      entry('extras/child/references/child.md', '# Child reference'),
    ];

    expect(selectSkillFolderEntries(entries, 'SKILL.md').map((item) => item.path)).toEqual([
      'SKILL.md',
      'references/root.md',
    ]);
  });

  it('reads exactly one, several, or all selected child skills before saving', async () => {
    const entries = [
      entry('bundle/a/SKILL.md', '# A'),
      entry('bundle/a/references/a.md', 'A'),
      entry('bundle/b/SKILL.md', '# B'),
      entry('bundle/c/SKILL.md', '# C'),
    ];
    const choices = listSkillFolderChoices(entries);
    for (const selected of [choices.slice(0, 1), choices.slice(0, 2), choices]) {
      const packages = await readSelectedSkillFolders(entries, selected);
      expect(packages.map((item) => item.skillPath)).toEqual(selected);
      expect(packages.every((item) => item.files.filter((file) => file.path === 'SKILL.md').length === 1)).toBe(true);
    }
    await expect(readSelectedSkillFolders(entries, [])).rejects.toThrow('至少选择');
  });
});
