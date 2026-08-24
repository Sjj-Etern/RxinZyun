"""
电梯控制完整测试脚本（纯 HTTP API，无 ROS/WebSocket）

用法:
  python test_elevator.py               # 默认全流程测试
  python test_elevator.py --floor 3     # 只去指定楼层
  python test_elevator.py --door        # 只测试开门关门
  python test_elevator.py --lift        # 只测试升降功能
  python test_elevator.py --monitor     # 持续监控状态
"""
import requests
import time
import argparse
import sys
from datetime import datetime

BASE = "http://127.0.0.1:8080"


def ts():
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]


def log(msg):
    print(f"[{ts()}] {msg}")


def cmd(cmd_name, floor=3):
    """发送命令，返回 (ok, ack_dict)"""
    url = f"{BASE}/api/v1/elevator/command?cmd={cmd_name}"
    if cmd_name == "go_floor":
        url += f"&floor={floor}"
    try:
        r = requests.post(url, timeout=15)
        data = r.json()
        if data.get("status") == "success":
            return True, data.get("ack", {})
        return False, data
    except Exception as e:
        return False, {"error": str(e)}


def state():
    """查询电梯控制器状态"""
    try:
        r = requests.get(f"{BASE}/api/v1/elevator/state", timeout=5)
        return r.json()
    except Exception as e:
        return {"error": str(e)}


# ====================================================================
# 测试用例
# ====================================================================

def test_connection():
    """测试连接"""
    log("=" * 50)
    log("1. 连接测试")
    log("=" * 50)

    s = state()
    if s.get("connected"):
        log(f"✓ ESP32 已连接: {s['client_addr']}")
        return True
    else:
        log(f"✗ ESP32 未连接: {s}")
        return False


def test_door():
    """测试开门关门"""
    log("=" * 50)
    log("2. 门控测试")
    log("=" * 50)

    # 开门
    ok, ack = cmd("open_door")
    log(f"  开门: {'✓' if ok else '✗'} {ack}")

    # 关门
    ok, ack = cmd("close_door")
    log(f"  关门: {'✓' if ok else '✗'} {ack}")

    return True


def test_status():
    """查询当前状态"""
    ok, ack = cmd("status")
    if ok:
        log(f"  状态: 楼层={ack.get('floor')}, 温度={ack.get('temp')}°C, 湿度={ack.get('humi')}%")
        return ack
    else:
        log(f"  ✗ 状态查询失败: {ack}")
        return None


def test_lift(floors="3,5,1"):
    """测试升降功能"""
    log("=" * 50)
    log("3. 升降功能测试")
    log("=" * 50)

    floor_list = [int(f.strip()) for f in floors.split(",")]
    results = []

    # 先查当前楼层
    current = test_status()
    if current is None:
        return []
    start_floor = current.get("floor", 0)

    for target in floor_list:
        current = test_status()
        if current is None:
            break
        now = current.get("floor", 0)

        if target == now:
            log(f"  跳过: 已在 {target} 楼")
            continue

        direction = "上行" if target > now else "下行"
        diff = abs(target - now)
        log(f"  {direction}: {now}→{target} (差 {diff} 层)")

        ok, ack = cmd("go_floor", target)
        if not ok:
            log(f"  ✗ 命令失败: {ack}")
            results.append({"from": now, "to": target, "ok": False})
            continue

        # 等待移动完成（每层约 5 秒）
        wait = diff * 5 + 2
        log(f"  等待移动完成 ({wait} 秒)...")
        time.sleep(wait)

        # 验证
        final = test_status()
        if final:
            actual = final.get("floor", 0)
            match = actual == target
            log(f"  {'✓' if match else '✗'} 实际楼层={actual}, 期望={target}")
            results.append({"from": now, "to": target, "actual": actual, "ok": match})

    return results


def test_flow():
    """完整流程测试（模拟 lift-arrive 场景）"""
    log("=" * 50)
    log("4. 完整流程测试（模拟 lift-arrive）")
    log("=" * 50)

    # 1. 查询初始状态
    s = test_status()
    if s is None:
        return 0, 1
    current_floor = s.get("floor", 1)

    # 2. 开门
    log("  [Step 1] 开门（电梯到达，开门）")
    ok, ack = cmd("open_door")
    log(f"  {'✓' if ok else '✗'} 开门: {ack}")

    # 3. 关门
    log("  [Step 2] 关门（车2进入电梯后关门）")
    ok, ack = cmd("close_door")
    log(f"  {'✓' if ok else '✗'} 关门: {ack}")

    # 4. 去目标楼层（模拟 lift-arrive 后的楼层移动）
    target = 3 if current_floor != 3 else 5
    diff = abs(target - current_floor)
    log(f"  [Step 3] 去目标楼层: {current_floor}→{target} (差 {diff} 层)")
    ok, ack = cmd("go_floor", target)
    if ok:
        wait = diff * 5 + 3
        log(f"  等待电梯移动 {wait} 秒...")
        time.sleep(wait)
        s = test_status()
        actual = s.get("floor", 0) if s else 0
        log(f"  {'✓' if actual == target else '✗'} 实际楼层={actual}")
    else:
        log(f"  ✗ {ack}")

    # 5. 开门（到达后开门）
    log("  [Step 4] 开门（到达目标楼层，开门）")
    ok, ack = cmd("open_door")
    log(f"  {'✓' if ok else '✗'} 开门: {ack}")

    # 6. 关门
    log("  [Step 5] 关门（护士取药后关门）")
    ok, ack = cmd("close_door")
    log(f"  {'✓' if ok else '✗'} 关门: {ack}")

    return 6, 0


def test_monitor(interval=5):
    """持续监控"""
    log("=" * 50)
    log("持续监控模式 (Ctrl+C 退出)")
    log("=" * 50)

    count = 0
    try:
        while True:
            count += 1
            ok, ack = cmd("status")
            if ok:
                log(f"  [#{count}] 楼层={ack.get('floor')}, "
                    f"温度={ack.get('temp')}°C, 湿度={ack.get('humi')}%")
            else:
                log(f"  [#{count}] ✗ {ack}")
            time.sleep(interval)
    except KeyboardInterrupt:
        log("监控结束")


# ====================================================================
# 主入口
# ====================================================================

def main():
    parser = argparse.ArgumentParser(description="电梯控制测试脚本")
    parser.add_argument("--door", action="store_true", help="仅测试门控")
    parser.add_argument("--lift", action="store_true", help="仅测试升降")
    parser.add_argument("--floors", default="3,5,1", help="升降测试楼层序列")
    parser.add_argument("--floor", type=int, default=0, help="去指定楼层")
    parser.add_argument("--monitor", action="store_true", help="持续监控")
    parser.add_argument("--interval", type=int, default=5, help="监控间隔秒数")
    parser.add_argument("--all", action="store_true", help="运行全部测试")
    args = parser.parse_args()

    # 默认：连接 + 门控 + 升降
    run_all = args.all or not any([args.door, args.lift, args.floor, args.monitor])

    print("=" * 50)
    print("  电梯控制测试")
    print("=" * 50)

    if not test_connection():
        sys.exit(1)

    if args.monitor:
        test_monitor(args.interval)
        return

    if args.door or run_all:
        test_door()

    if args.lift or run_all:
        results = test_lift(args.floors)
        if results:
            passed = sum(1 for r in results if r["ok"])
            total = len(results)
            log(f"\n升降测试: {passed}/{total} 通过")

    if args.floor > 0:
        log("=" * 50)
        log(f"去 {args.floor} 楼")
        log("=" * 50)
        ok, ack = cmd("go_floor", args.floor)
        log(f"  {'✓' if ok else '✗'} {ack}")

    if run_all:
        passed, failed = test_flow()
        log(f"\n完整流程: {passed} 通过, {failed} 失败")

    # 最终状态
    log("=" * 50)
    log("最终状态")
    log("=" * 50)
    test_status()

    print("=" * 50)
    print("  测试完成")
    print("=" * 50)


if __name__ == "__main__":
    main()