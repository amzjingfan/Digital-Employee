import { renderMarkdownBlocks } from './chat/chatHelpers';

export const SKILL_MARKDOWN_PREVIEW_BODY_CLASS =
  'min-w-0 max-w-full [&>*:first-child]:mt-0 [&>*:last-child]:mb-0 [&>h1]:mb-4 [&>h1]:text-[22px] [&>h1]:font-semibold [&>h1]:leading-[1.35] [&>h2]:mb-3 [&>h2]:mt-6 [&>h2]:text-[18px] [&>h2]:font-semibold [&>h2]:leading-[1.4] [&>h3]:mb-2 [&>h3]:mt-5 [&>h3]:text-[16px] [&>h3]:font-semibold [&_p]:mb-3 [&_p]:wrap-anywhere [&>ul]:mb-3 [&>ol]:mb-3 [&>ul]:list-disc [&>ol]:list-decimal [&>ul]:pl-6 [&>ol]:pl-6 [&_li]:mb-1 [&>blockquote]:mb-3 [&>blockquote]:border-l-2 [&>blockquote]:border-[#e3e7f1] [&>blockquote]:pl-4 [&>blockquote]:text-[#757f9c] [&_a]:text-[#0b6cf5] [&_a]:underline [&_p_code]:rounded-[4px] [&_p_code]:bg-[#f6f7fb] [&_p_code]:px-1 [&_p_code]:py-[1px] [&_p_code]:font-mono [&_li_code]:rounded-[4px] [&_li_code]:bg-[#f6f7fb] [&_li_code]:px-1 [&_li_code]:py-[1px] [&_li_code]:font-mono [&_.code-block-vscode]:mb-3 [&_table]:mb-3 [&_table]:w-full [&_table]:border-collapse [&_th]:border [&_th]:border-[#e3e7f1] [&_th]:bg-[#f6f7fb] [&_th]:px-3 [&_th]:py-2 [&_td]:border [&_td]:border-[#e3e7f1] [&_td]:px-3 [&_td]:py-2';

const PHASE_LABELS: Record<string, string> = {
  user_message_received: '收到测试问题',
  turn_plan_created: '制定执行计划',
  router_decision_created: '确定处理方式',
  task_frame_started: '开始执行任务',
  harness_action_created: '执行操作',
  instructions_loaded: '加载技能说明',
  harness_tool_completed: '工具执行完成',
  task_frame_finished: '任务执行结束',
  assistant_message_created: '生成最终回复',
  session_state_changed: '更新会话状态',
  general_skill_selected: '选择技能',
  general_skill_intent_checked: '检查技能适用范围',
  skill_started: '开始执行技能',
  skill_resumed: '继续执行技能',
  skill_step_changed: '进入下一步骤',
  skill_loaded: '加载技能',
  read_started: '阅读技能内容',
  read_created: '完成技能阅读',
  read_failed: '读取技能失败',
  planning: '生成执行方案',
  plan_created: '生成代码',
  attempt_started: '开始运行',
  running_code: '运行代码',
  stdout_chunk: '运行输出',
  stderr_chunk: '错误输出',
  code_finished: '读取运行结果',
  code_timeout: '运行超时',
  reflection_passed: '校验通过',
  reflection_retrying: '反思修复',
  reflection_stopped: '停止重试',
  repair_planning: '重新生成代码',
  repair_failed: '修复失败',
  plan_failed: '生成失败',
  replying: '生成回复',
  reply_created: '完成回复',
  reply_failed: '回复失败',
};

export function presentSkillTrace(item: Record<string, unknown>): { title: string; message: string } {
  const phase = typeof item.phase === 'string' ? item.phase : '';
  const rawMessage = typeof item.message === 'string' ? item.message.trim() : '';
  const message = rawMessage === phase || /^[a-z][a-z0-9_]*$/.test(rawMessage) ? '' : rawMessage;
  return {
    title: PHASE_LABELS[phase] || '执行步骤',
    message: message.length > 180 ? `${message.slice(0, 180)}…` : message,
  };
}

export function SkillRunReply({ content, className = '' }: { content: string; className?: string }) {
  return (
    <div className={`${SKILL_MARKDOWN_PREVIEW_BODY_CLASS} ${className}`}>
      {renderMarkdownBlocks(content)}
    </div>
  );
}
