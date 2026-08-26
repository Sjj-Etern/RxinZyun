# -*- coding: utf-8 -*-
"""
后端启动包装脚本（日志收集器）
================================
作用：
  1. 以子进程方式启动 app.py（不修改后端任何代码）
  2. 实时读取子进程 stdout/stderr，为每一行补上 [HH:MM:SS] 时间戳
  3. 同时输出到：控制台（照常显示） + logs/backend.log（本次会话完整日志）
  4. 每次启动时，将上一次的 logs/backend.log 归档到 logs/archive/，日志随每次重跑更新

用法：
  python run_backend.py            # 启动后端并收集日志
  Ctrl+C 停止（会同时终止后端子进程）

之后运行日志总结器：
  python log_summarizer.py         # 读取 logs/backend.log 生成摘要
"""
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
LOG_DIR = BASE_DIR / "logs"
ARCHIVE_DIR = LOG_DIR / "archive"
LOG_FILE = LOG_DIR / "backend.log"

APP_CMD = [sys.executable, "-u", "app.py"]  # -u 禁用子进程输出缓冲，保证实时性


def prepare_log_file() -> Path:
    """启动前归档旧日志，返回本次会话的日志文件路径"""
    LOG_DIR.mkdir(exist_ok=True)
    ARCHIVE_DIR.mkdir(exist_ok=True)

    if LOG_FILE.exists() and LOG_FILE.stat().st_size > 0:
        ts = datetime.fromtimestamp(LOG_FILE.stat().st_mtime).strftime("%Y%m%d_%H%M%S")
        archive_path = ARCHIVE_DIR / f"backend_{ts}.log"
        shutil.move(str(LOG_FILE), str(archive_path))
        print(f"[run_backend] 旧日志已归档: {archive_path.name}")

    return LOG_FILE


def main() -> None:
    # Windows 控制台避免 GBK 编码崩溃
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    log_file = prepare_log_file()
    print(f"[run_backend] 后端日志将写入: {log_file}")
    print(f"[run_backend] 正在启动后端: {' '.join(APP_CMD)}")

    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"

    proc = subprocess.Popen(
        APP_CMD,
        cwd=str(BASE_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,  # stderr 合并进同一管道
        env=env,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )

    def stamp() -> str:
        return datetime.now().strftime("%H:%M:%S")

    try:
        with open(log_file, "w", encoding="utf-8", newline="\n") as f:
            f.write(f"[{stamp()}] [run_backend] ===== 后端会话开始 {datetime.now()} =====\n")
            assert proc.stdout is not None
            for line in proc.stdout:
                stamped = f"[{stamp()}] {line.rstrip()}"
                print(stamped)
                f.write(stamped + "\n")
                f.flush()
    except KeyboardInterrupt:
        print("\n[run_backend] 收到 Ctrl+C，正在停止后端...")
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"[{stamp()}] [run_backend] ===== 后端会话结束 exit={proc.returncode} =====\n")
        print(f"[run_backend] 后端已停止 (exit={proc.returncode})，日志已保存: {log_file}")


if __name__ == "__main__":
    main()
