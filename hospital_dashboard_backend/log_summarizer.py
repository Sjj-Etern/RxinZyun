# -*- coding: utf-8 -*-
"""
后端日志总结器
==============
读取 run_backend.py 收集的日志（logs/backend.log），按时间线分组输出可读摘要，
并自动检测常见问题（车1/车2 链路卡点、电梯超时、匹配失败等）。

用法：
  python log_summarizer.py                       # 分析本次会话 logs/backend.log
  python log_summarizer.py logs/archive/xxx.log  # 分析指定历史日志
  python log_summarizer.py --tail 200            # 只看最后200行的快速摘要

输出：
  1. 控制台：彩色分组时间线摘要 + 问题清单
  2. 文件：  logs/summary.md（含可溯源的日志行号）
"""
import re
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_LOG = BASE_DIR / "logs" / "backend.log"
REPORT_FILE = BASE_DIR / "logs" / "summary.md"

# ============================================================
# 颜色输出（Windows 10+ ANSI）
# ============================================================
def _enable_color():
    if sys.platform == "win32":
        import ctypes
        try:
            kernel32 = ctypes.windll.kernel32
            kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
            # 控制台代码页切到 UTF-8，与 stdout utf-8 输出配套，避免中文乱码
            kernel32.SetConsoleCP(65001)
            kernel32.SetConsoleOutputCP(65001)
        except Exception:
            pass


class C:
    RESET = "\033[0m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    GRAY = "\033[90m"
    BOLD = "\033[1m"

    @classmethod
    def off(cls):
        for name in ("RESET", "RED", "GREEN", "YELLOW", "BLUE", "MAGENTA", "CYAN", "GRAY", "BOLD"):
            setattr(cls, name, "")


# ============================================================
# 日志行解析
# ============================================================
TS_RE = re.compile(r"^\[(\d{2}:\d{2}:\d{2})\]\s*(.*)$")


class LogLine:
    __slots__ = ("lineno", "ts", "text", "tag")

    def __init__(self, lineno: int, ts: str, text: str):
        self.lineno = lineno
        self.ts = ts          # 无时间戳时为 "??:??:??"
        self.text = text
        # 提取来源标签，如 [HIS Sender 车1] / [ROS Listener 车2] / [Elevator TCP]
        m = re.match(r"^\[(?!HIS Sender 车)(ROS Listener 车\d|HIS Sender 车\d|Elevator[^\]]*|DHT11[^\]]*|run_backend)\]\s*(.*)", text)
        if m:
            self.tag = m.group(1)
            self.text = m.group(2)
        else:
            self.tag = ""


# ============================================================
# 事件规则表：(分组, 正则, 展示模板, 严重级别)
#   展示模板中 {0} 为整行匹配对象，可用 m.group(n)
# ============================================================
RULES = [
    # ---------- 车1 链 ----------
    ("car1", re.compile(r"处方编码更新: (\S+) -> (\S+)"), "处方更新: {1} → {2}", "info"),
    ("car1", re.compile(r"重置药品发送状态"), None, "info"),
    ("car1", re.compile(r"处方 (\S+) 包含 (\d+) 个药品"), "处方 {1} 共 {2} 个药品", "info"),
    ("car1", re.compile(r"开始处理药品 (\d+)/(\d+) \(ID=(\d+)\)"), "▶ 开始药品 {1}/{2} (ID={3})", "info"),
    ("car1", re.compile(r"发送 start（第(\d+)次）"), "  发送 start 第{1}次", "info"),
    ("car1", re.compile(r"发送 running（第(\d+)次）"), "  发送 running 第{1}次", "info"),
    ("car1", re.compile(r"收到 running-started（共发送(\d+)次start）"), "  ✓ running-started（start共发{1}次）", "ok"),
    ("car1", re.compile(r"收到 running-step5-waiting-end（共发送(\d+)次running）"), "  ✓ step5-waiting-end（running共发{1}次）", "ok"),
    ("car1", re.compile(r"发送药品完成信号（end）"), "  发送 end ×2", "info"),
    ("car1", re.compile(r"药品 \d+/\d+ \(ID=\d+\) 处理完成"), "  ✓ 药品处理完成", "ok"),
    ("car1", re.compile(r"所有药品发送完成"), "✓ 所有药品发送完成", "ok"),
    ("car1", re.compile(r"收到药品 started 通知"), "  收到 started 通知 →", "info"),
    ("car1", re.compile(r"收到药品完成通知（Step5返回）"), "  收到 Step5 返回通知 →", "info"),
    ("car1", re.compile(r"收到所有药品完成信号（all_completed）"), "✓ 车1 all_completed", "ok"),
    ("car1", re.compile(r"收到 end 消息|收到任务完成信号"), "✓ 车1 任务完成", "ok"),
    ("car1", re.compile(r"\[ERROR\] 处方编码不匹配"), "  ✗ 处方编码不匹配（不设置事件）", "error"),
    ("car1", re.compile(r"药品ID不匹配！收到=(\d+) 预期=(\d+)"), "  ✗ 药品ID不匹配: 收到={1} 预期={2}", "error"),
    ("car1", re.compile(r"处方 \S+ 的药品列表为空"), "  ✗ 药品列表为空", "error"),

    # ---------- 车2 链 ----------
    ("car2", re.compile(r"启动 pharmacist-success 连续发送"), "▶ 启动 pharmacist-success 连续发送", "info"),
    ("car2", re.compile(r"启动 lift-across 连续发送"), "▶ 启动 lift-across 连续发送", "info"),
    ("car2", re.compile(r"启动 lift-open 连续发送"), "▶ 启动 lift-open 连续发送", "info"),
    ("car2", re.compile(r"启动 nurse-success 连续发送"), "▶ 启动 nurse-success 连续发送（3次）", "info"),
    ("car2", re.compile(r"\[连续发送\] 停止 (\S+)（共发送 (\d+) 次）"), "  ■ 停止 {1}（共{2}次）", "info"),
    ("car2", re.compile(r"电梯到达目标楼层: (\S+)"), "✓ 车2 lift-arrive（{1}）", "ok"),
    ("car2", re.compile(r"已停止 pharmacist-success"), "  ■ 停止 pharmacist-success", "info"),
    ("car2", re.compile(r"→ 车2: lift-across"), "  → 车2: lift-across", "info"),
    ("car2", re.compile(r"等待 (\d+) 秒\.\.\."), "  等待 {1} 秒（车2进电梯）", "info"),
    ("car2", re.compile(r"→ 车2: lift-open"), "  → 车2: lift-open", "info"),
    ("car2", re.compile(r"→ 车2: nurse-success"), "  → 车2: nurse-success", "info"),
    ("car2", re.compile(r"等待护士到达信号"), "  等待 nurse_arrive ...", "info"),
    ("car2", re.compile(r"护士已到达: (\S+)"), "✓ 车2 nurse_arrive（{1}）", "ok"),
    ("car2", re.compile(r"已停止 lift-open"), "  ■ 停止 lift-open", "info"),
    ("car2", re.compile(r"车2未注册"), "  ✗ 车2 未注册", "error"),

    # ---------- 电梯链 ----------
    ("elev", re.compile(r"TCP 服务端已启动，监听"), "TCP 服务端启动", "info"),
    ("elev", re.compile(r"ESP32 已连接: (\S+)"), "✓ ESP32 已连接: {1}", "ok"),
    ("elev", re.compile(r"ESP32 已断开: (\S+)"), "✗ ESP32 断开: {1}", "warn"),
    ("elev", re.compile(r"\[电梯\] 发送开门命令"), "  [电梯] 开门", "info"),
    ("elev", re.compile(r"✓ 开门完成"), "  ✓ 开门完成", "ok"),
    ("elev", re.compile(r"\[电梯\] 发送关门命令"), "  [电梯] 关门", "info"),
    ("elev", re.compile(r"✓ 关门完成"), "  ✓ 关门完成", "ok"),
    ("elev", re.compile(r"当前楼层=(\d+), 目标楼层=(\d+)"), "  当前{1}楼 → 目标{2}楼", "info"),
    ("elev", re.compile(r"发送去(\d+)楼命令"), "  [电梯] 去{1}楼", "info"),
    ("elev", re.compile(r"已在(\d+)楼，无需移动"), "  已在{1}楼，无需移动", "info"),
    ("elev", re.compile(r"ESP32 未连接，跳过(\S+)"), "  ⚠ ESP32 未连接，跳过{1}", "warn"),
    ("elev", re.compile(r"SEND #(\d+) → \S+: (\w+)"), "  SEND #{1} {2}", "info"),
    ("elev", re.compile(r"ACK  #(\d+): cmd=(\w+), status=(\S+)"), "  ACK  #{1} {2}({3})", "ok"),
    ("elev", re.compile(r"DONE #(\d+)"), "  DONE #{1}", "ok"),
    ("elev", re.compile(r"TIMEOUT #(\d+)"), "  ✗ TIMEOUT #{1}", "error"),
    ("elev", re.compile(r"发现请求 from (\S+)"), "  UDP 发现 from {1}", "info"),

    # ---------- HIS 同步 / 语音 ----------
    ("his", re.compile(r"获取到最新处方: (\S+)"), "HIS 最新待处理处方: {1}", "info"),
    ("his", re.compile(r"更新处方流程状态: (\S+).* -> (\S+)"), "DB 流程状态: {1} → {2}", "info"),
    ("his", re.compile(r"HIS处方状态更新: (\S+) -> dispensed"), "✓ HIS 处方 {1} → dispensed", "ok"),
    ("his", re.compile(r"pharmacist-success-trigger"), "HIS 节点3完成 → 触发 pharmacist-success", "info"),
    ("his", re.compile(r"语音播报成功"), "语音播报成功", "ok"),

    # ---------- 连接与异常 ----------
    ("sys", re.compile(r"已连接 Ros WebSocket: (\S+)"), "✓ ROS WS 已连接: {1}", "ok"),
    ("sys", re.compile(r"ROS WebSocket 不可达|WebSocket 连接失败"), "✗ ROS WebSocket 不可达/失败", "error"),
    ("sys", re.compile(r"WebSocket 连接已关闭"), "✗ WebSocket 连接关闭，将重连", "warn"),
    ("sys", re.compile(r"数据库表创建完成"), "✓ 数据库表创建完成", "ok"),
    ("sys", re.compile(r"\[去0机制\] 忽略 medicine_id=0 的消息: (\S+)"), "⚠ 去0机制忽略消息: {1}", "warn"),
    ("sys", re.compile(r"收到未匹配的 ACK"), "⚠ 收到未匹配 ACK", "warn"),
    ("sys", re.compile(r"主循环异常"), "✗ 主循环异常", "error"),
    ("sys", re.compile(r"发送失败"), "✗ 发送失败", "error"),
    ("sys", re.compile(r"消息处理任务异常"), "✗ 消息处理任务异常", "error"),
    ("sys", re.compile(r"===== 后端会话(开始|结束)"), None, "session"),
]

SEV_COLOR = {"info": C.CYAN, "ok": C.GREEN, "warn": C.YELLOW, "error": C.RED, "session": C.GRAY}
SECTION_TITLES = {
    "car1": "① 车1 链（start/running/end → 药房-病房配送）",
    "car2": "② 车2 链（pharmacist-success → 电梯 → 护士站）",
    "elev": "③ 电梯链（ESP32 TCP/UDP）",
    "his":  "④ HIS 同步 / 语音播报",
    "sys":  "⑤ 系统连接 / 异常",
}


def load_lines(path: Path, tail: int = 0):
    lines = []
    with open(path, encoding="utf-8", errors="replace") as f:
        for i, raw in enumerate(f, 1):
            m = TS_RE.match(raw.rstrip())
            ts = m.group(1) if m else "??:??:??"
            text = m.group(2) if m else raw.rstrip()
            lines.append(LogLine(i, ts, text))
    return lines[-tail:] if tail else lines


def match_event(line: LogLine):
    """返回 (section, display, severity) 或 None"""
    for section, rx, tmpl, sev in RULES:
        m = rx.search(line.text)
        if m:
            # 安全替换：{n} 对应正则第 n 组；组不存在时置空，避免 IndexError
            groups = m.groups()
            disp = re.sub(r"\{(\d+)\}",
                          lambda g: groups[int(g.group(1)) - 1] if 0 < int(g.group(1)) <= len(groups) else "",
                          tmpl) if tmpl else line.text
            return section, disp, sev
    return None


def summarize(lines):
    """主分析：分组时间线 + 问题检测"""
    events = []           # (lineno, ts, tag, section, disp, sev)
    problems = []         # (severity, ts, lineno, desc, evidence)
    start_send_counts = []  # (lineno, ts, count)
    last_start_count = {}

    for ln in lines:
        ev = match_event(ln)
        if not ev:
            continue
        section, disp, sev = ev
        events.append((ln.lineno, ln.ts, ln.tag, section, disp, sev))

        # ---- 问题检测 ----
        m = re.search(r"发送 start（第(\d+)次）", ln.text)
        if m:
            count = int(m.group(1))
            tag_key = ln.tag or "?"
            if count > last_start_count.get(tag_key, 0) + 20:  # 计数跳变说明新一轮
                pass
            last_start_count[tag_key] = count
            if count in (5, 10, 20, 50, 100):
                problems.append(("warn", ln.ts, ln.lineno,
                                 f"start 已重发 {count} 次仍未收到匹配的 running-started（可能：车1未回/处方编码不匹配/药品ID不匹配）",
                                 ln.text))
        m = re.search(r"发送 running（第(\d+)次）", ln.text)
        if m and int(m.group(1)) in (5, 10, 20, 50):
            problems.append(("warn", ln.ts, ln.lineno,
                             f"running 已重发 {m.group(1)} 次仍未收到匹配的 step5-waiting-end", ln.text))
        if "处方编码不匹配" in ln.text:
            problems.append(("error", ln.ts, ln.lineno, "车1反馈处方编码与当前处方不匹配 → started 事件未设置，start 将持续重发", ln.text))
        if "药品ID不匹配" in ln.text:
            problems.append(("error", ln.ts, ln.lineno, "车1反馈药品ID与预期不符 → 对应事件未设置，流程卡住", ln.text))
        if "去0机制" in ln.text:
            problems.append(("warn", ln.ts, ln.lineno, "车端消息 medicine_id=0 被去0机制忽略", ln.text))
        if "TIMEOUT" in ln.text:
            problems.append(("error", ln.ts, ln.lineno, "电梯命令 ACK 超时", ln.text))
        if "连接已关闭" in ln.text or "连接失败" in ln.text:
            problems.append(("warn", ln.ts, ln.lineno, "WebSocket 断连（将自动重连）", ln.text))

    # 车2 链完整性检测（注意用完整事件文案判断，避免"等待 nurse_arrive"被误判为已收到）
    texts = [e[4] for e in events]
    car2_started = any("启动 pharmacist-success 连续发送" in t for t in texts)
    car2_lift_arrive = any("✓ 车2 lift-arrive" in t for t in texts)
    car2_nurse = any("✓ 车2 nurse_arrive" in t for t in texts)
    car2_done = any("启动 nurse-success" in t for t in texts)
    if car2_started and not car2_lift_arrive:
        problems.append(("warn", "??:??:??", "-",
                         "车2链：pharmacist-success 已连发但未收到 lift-arrive（车2未到电梯/未回报）", ""))
    if car2_lift_arrive and not car2_nurse:
        problems.append(("warn", "??:??:??", "-",
                         "车2链：已收到 lift-arrive 但一直未收到 nurse_arrive（8步编排可能阻塞在 Step7 等待）", ""))
    if car2_nurse and not car2_done:
        problems.append(("warn", "??:??:??", "-",
                         "车2链：已收到 nurse_arrive 但未发送 nurse-success（Step8 未执行？）", ""))

    # 车1 链完整性检测
    car1_medicine_started = any("开始药品" in t for t in texts)
    car1_got_started = any("✓ running-started" in t for t in texts)
    if car1_medicine_started and not car1_got_started:
        problems.append(("warn", "??:??:??", "-",
                         "车1链：已发送 start 但从未收到匹配的 running-started（对照上方匹配错误定位原因）", ""))

    return events, problems


def print_console(events, problems, log_path: Path, total_lines: int):
    print(f"\n{C.BOLD}╔══════════════════════════════════════════════════════════╗")
    print(f"║          医院大屏后端日志摘要  ({log_path.name})")
    print(f"╚══════════════════════════════════════════════════════════╝{C.RESET}")
    print(f"{C.GRAY}日志总行数: {total_lines} | 提取事件: {len(events)} | 检出问题: {len(problems)}{C.RESET}")

    # 按行号顺序统一输出，分组标题按 section 首次出现位置插入
    seen_sections = []
    by_section = {}
    for ev in events:
        by_section.setdefault(ev[3], []).append(ev)

    order = ["car1", "car2", "elev", "his", "sys"]
    for section in order:
        evs = by_section.get(section)
        if not evs:
            continue
        print(f"\n{C.BOLD}{C.MAGENTA}━━ {SECTION_TITLES[section]} ━━{C.RESET}")
        for lineno, ts, tag, _, disp, sev in evs:
            color = SEV_COLOR.get(sev, C.RESET)
            tag_str = f"{C.GRAY}[{tag}]{C.RESET}" if tag else ""
            print(f"  {C.GRAY}{ts}{C.RESET} {color}{disp}{C.RESET} {tag_str} {C.GRAY}(L{lineno}){C.RESET}")

    # 问题清单
    print(f"\n{C.BOLD}{C.RED}━━ ⚠ 问题清单（按时间排序）━━{C.RESET}")
    if not problems:
        print(f"  {C.GREEN}未检出问题 ✓{C.RESET}")
    else:
        sev_rank = {"error": 0, "warn": 1}
        for sev, ts, lineno, desc, evidence in sorted(problems, key=lambda p: (sev_rank.get(p[0], 9),)):
            color = C.RED if sev == "error" else C.YELLOW
            icon = "✗" if sev == "error" else "⚠"
            loc = f"L{lineno}" if lineno != "-" else ""
            print(f"  {color}{icon} [{ts}] {desc}{C.RESET} {C.GRAY}{loc}{C.RESET}")


def write_report(events, problems, log_path: Path, total_lines: int):
    lines_out = []
    lines_out.append(f"# 后端日志摘要报告\n")
    lines_out.append(f"- 日志文件: `{log_path}`")
    lines_out.append(f"- 日志总行数: {total_lines} | 提取事件: {len(events)} | 检出问题: {len(problems)}\n")

    by_section = {}
    for ev in events:
        by_section.setdefault(ev[3], []).append(ev)

    for section in ["car1", "car2", "elev", "his", "sys"]:
        evs = by_section.get(section)
        if not evs:
            continue
        lines_out.append(f"\n## {SECTION_TITLES[section]}\n")
        lines_out.append("| 时间 | 事件 | 来源 | 行号 |")
        lines_out.append("|------|------|------|------|")
        for lineno, ts, tag, _, disp, sev in evs:
            mark = {"ok": "✅", "error": "❌", "warn": "⚠️"}.get(sev, "")
            lines_out.append(f"| {ts} | {mark} {disp} | {tag} | L{lineno} |")

    lines_out.append(f"\n## 问题清单\n")
    if not problems:
        lines_out.append("未检出问题 ✓")
    else:
        for sev, ts, lineno, desc, evidence in problems:
            icon = "❌" if sev == "error" else "⚠️"
            loc = f"（日志 L{lineno}）" if lineno != "-" else ""
            lines_out.append(f"- {icon} **[{ts}]** {desc} {loc}")
            if evidence:
                lines_out.append(f"  - 证据: `{evidence[:120]}`")

    REPORT_FILE.parent.mkdir(exist_ok=True)
    REPORT_FILE.write_text("\n".join(lines_out), encoding="utf-8")


def main():
    _enable_color()
    # Windows 控制台避免 GBK 编码崩溃
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    args = sys.argv[1:]
    tail = 0
    log_path = DEFAULT_LOG
    if "--tail" in args:
        i = args.index("--tail")
        tail = int(args[i + 1])
        args = args[:i] + args[i + 2:]
    if args:
        log_path = Path(args[0])
    if not log_path.exists():
        print(f"[总结器] 日志文件不存在: {log_path}")
        print(f"[总结器] 请先用 run_backend.py 启动后端生成日志，或传入日志路径")
        sys.exit(1)

    lines = load_lines(log_path, tail=tail)
    events, problems = summarize(lines)
    print_console(events, problems, log_path, len(lines))
    write_report(events, problems, log_path, len(lines))
    print(f"\n{C.GRAY}报告已生成: {REPORT_FILE}{C.RESET}\n")


if __name__ == "__main__":
    main()
