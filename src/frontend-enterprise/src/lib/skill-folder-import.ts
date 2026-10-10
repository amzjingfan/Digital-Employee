export type SkillFolderEntry = { file: File; path: string };

function cleanPath(path: string): string {
  const parts = path.replace(/\\/g, '/').replace(/^\/+/, '').split('/');
  if (parts.some((part) => !part || part === '.' || part === '..')) {
    throw new Error(`技能文件路径无效：${path}`);
  }
  return parts.join('/');
}

export function listSkillFolderChoices(entries: SkillFolderEntry[]): string[] {
  return entries
    .map((entry) => cleanPath(entry.path))
    .filter((path) => path.split('/').pop()?.toLowerCase() === 'skill.md')
    .sort((left, right) => left.localeCompare(right));
}

export function selectSkillFolderEntries(entries: SkillFolderEntry[], skillPath: string): SkillFolderEntry[] {
  const choices = listSkillFolderChoices(entries);
  if (!choices.includes(skillPath)) throw new Error('文件夹中没有找到所选的 SKILL.md');
  const prefix = skillPath.slice(0, skillPath.length - 'SKILL.md'.length);
  if (choices.some((choice) => choice !== skillPath && choice.startsWith(prefix)
    && choice.slice(prefix.length).toLowerCase() === 'skill.md')) {
    throw new Error('同一目录存在多个 SKILL.md，请只保留一个');
  }
  const otherSkillFolders = choices
    .filter((choice) => choice !== skillPath)
    .map((choice) => choice.slice(0, choice.length - 'SKILL.md'.length))
    .filter((folder) => folder.length > prefix.length && folder.startsWith(prefix));
  const selected = entries
    .map((entry) => ({ ...entry, path: cleanPath(entry.path) }))
    .filter((entry) => entry.path.startsWith(prefix)
      && !otherSkillFolders.some((folder) => entry.path.startsWith(folder)))
    .map((entry) => ({ ...entry, path: entry.path.slice(prefix.length) }));
  const paths = selected.map((entry) => entry.path);
  if (new Set(paths).size !== paths.length) throw new Error('技能文件夹中存在重复文件路径');
  return selected;
}

export async function readSkillFolderFiles(entries: SkillFolderEntry[]) {
  return Promise.all(entries.map(async ({ file, path }) => {
    let content: string;
    try {
      content = new TextDecoder('utf-8', { fatal: true }).decode(await file.arrayBuffer());
      if (content.includes('\0')) throw new Error('binary');
    } catch {
      throw new Error(`无法读取技能文件 ${path}：仅支持 UTF-8 文本文件`);
    }
    return { path, content, size: file.size, mime_type: file.type || undefined };
  }));
}
