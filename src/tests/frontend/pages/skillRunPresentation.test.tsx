import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import { SkillRunReply, presentSkillTrace, resultSucceeded } from '@/pages/skillRunPresentation';

describe('skill run result presentation', () => {
  it('renders a skill test reply as readable Markdown', () => {
    const reply = '## 使用步骤\n\n1. 检查授权\n2. 生成方案\n\n使用 `demo` 模式。';
    const html = renderToStaticMarkup(createElement(SkillRunReply, { content: reply }));

    expect(html).toContain('<h2>使用步骤</h2>');
    expect(html).toContain('<ol>');
    expect(html).toContain('<li>检查授权</li>');
    expect(html).toContain('<code>demo</code>');
    expect(html).not.toContain('## 使用步骤');
  });

  it('gives Harness v2 events readable titles without repeating raw event codes', () => {
    expect(presentSkillTrace({ phase: 'turn_plan_created', message: 'turn_plan_created' }))
      .toEqual({ title: '制定执行计划', message: '' });
    expect(presentSkillTrace({ phase: 'harness_action_created', message: 'harness_action_created' }))
      .toEqual({ title: '执行操作', message: '' });
    expect(presentSkillTrace({ phase: 'instructions_loaded', message: 'instructions_loaded' }))
      .toEqual({ title: '加载技能说明', message: '' });
    expect(presentSkillTrace({ phase: 'reflection_passed', message: '第 1 次运行结果可用' }))
      .toEqual({ title: '校验通过', message: '第 1 次运行结果可用' });
    expect(presentSkillTrace({ phase: 'future_event', message: 'future_event' }))
      .toEqual({ title: '执行步骤', message: '' });
  });

  it('requires a real answer and an explicit successful result', () => {
    const answer = { reply: '北京今天晴朗', structured_result: { success: true }, stderr: '' };
    expect(resultSucceeded(answer)).toBe(true);
    expect(resultSucceeded({ ...answer, reply: '' })).toBe(false);
    expect(resultSucceeded({ ...answer, structured_result: { success: true, runtime_error_code: 'HARNESS_V2_ERROR' } })).toBe(false);
    expect(resultSucceeded({ ...answer, structured_result: {} })).toBe(false);
  });
});
