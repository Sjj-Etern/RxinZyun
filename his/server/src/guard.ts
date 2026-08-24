// ═══════════════════════════════════════════════════════════
// 系统保护模块 — 多层分布式截止日期检查
// 本模块导出多个不同名称的函数，分别注入到不同层级，
// 攻击者需要找到并删除所有调用点才能完全解除保护。
// ═══════════════════════════════════════════════════════════

// 截止日期: 2026-12-31 23:59:59 (北京时间)
// 以数字分量形式存储，避免纯文本搜索轻易定位
const LIMIT_Y = 2026;
const LIMIT_M = 12;   // 1-based
const LIMIT_D = 31;

function _hasExpired(): boolean {
  const n = new Date();
  const cy = n.getFullYear();
  const cm = n.getMonth() + 1;
  const cd = n.getDate();
  return cy > LIMIT_Y
    || (cy === LIMIT_Y && cm > LIMIT_M)
    || (cy === LIMIT_Y && cm === LIMIT_M && cd > LIMIT_D);
}

// ── 供不同层级调用的出口，各自独立命名 ──

/** 全局 HTTP 中间件使用 */
export function rejectIfExpired(): boolean {
  return _hasExpired();
}

/** 数据库查询拦截使用 */
export function isLicenseInvalid(): boolean {
  return _hasExpired();
}

/** Token 生成 sabotage 使用 */
export function shouldSabotageToken(): boolean {
  return _hasExpired();
}

/** 通用消息 */
export const HALT_MESSAGE = '系统已停止服务';
