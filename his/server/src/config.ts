// 系统截止日期配置
// 当到达此日期后，系统将禁止任何人登录，已登录用户也会被强制踢出
export const SYSTEM_DEADLINE = '2026-12-31T23:59:59';
export const SYSTEM_DEADLINE_MESSAGE = '系统已停止服务';

export function isPastDeadline(): boolean {
  return new Date() > new Date(SYSTEM_DEADLINE);
}
