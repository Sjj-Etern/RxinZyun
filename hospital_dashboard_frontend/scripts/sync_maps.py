#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ROS 占用栅格地图同步脚本
扫描 src/map/ 下的 *.pgm 文件，转为浏览器可显示的 *.png，
并读取同名 *.yaml 提取 origin / resolution / 尺寸，输出映射参数供前端 .env 使用。

用法：
    python scripts/sync_maps.py

输出：
    src/map/<name>.png           （浏览器可显示的地图底图）
    控制台打印 .env 配置片段（origin / resolution / height）
"""
import os
import sys
import re
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    print('ERROR: Pillow 未安装，请运行: pip install Pillow', file=sys.stderr)
    sys.exit(1)

# 脚本所在目录：scripts/；地图目录：../src/map/
SCRIPT_DIR = Path(__file__).resolve().parent
MAP_DIR = SCRIPT_DIR.parent / 'src' / 'map'


def parse_pgm_size(pgm_path: Path):
    """读取 P5/P2 PGM 文件头部，返回 (width, height)。跳过注释行。"""
    with open(pgm_path, 'rb') as f:
        magic = f.readline().strip()  # P5 或 P2
        if magic not in (b'P5', b'P2'):
            raise ValueError(f'{pgm_path.name}: 非 PGM P5/P2 格式（magic={magic}）')
        # 跳过注释行与空行，读取 width height
        line = f.readline()
        while line.startswith(b'#') or line.strip() == b'':
            line = f.readline()
        w, h = map(int, line.split())
    return w, h


def parse_yaml(yaml_path: Path):
    """解析 ROS map yaml，返回 dict（image / resolution / origin / ...）。"""
    if not yaml_path.exists():
        return None
    result = {}
    for raw in yaml_path.read_text(encoding='utf-8').splitlines():
        line = raw.split('#', 1)[0].strip()
        if not line or ':' not in line:
            continue
        key, _, val = line.partition(':')
        result[key.strip()] = val.strip()
    return result


def parse_origin(origin_str: str):
    """解析 origin: [-50.0, -50.0, 0.0] → (x, y, yaw)。"""
    nums = re.findall(r'-?\d+\.?\d*', origin_str)
    return tuple(float(x) for x in nums[:3]) if len(nums) >= 3 else (0.0, 0.0, 0.0)


def main():
    if not MAP_DIR.exists():
        print(f'ERROR: 地图目录不存在: {MAP_DIR}', file=sys.stderr)
        sys.exit(1)

    pgm_files = sorted(MAP_DIR.glob('*.pgm'))
    if not pgm_files:
        print(f'未找到 .pgm 文件，目录: {MAP_DIR}')
        return

    print(f'找到 {len(pgm_files)} 个地图文件，开始同步...\n')

    env_lines = []
    for pgm in pgm_files:
        name = pgm.stem  # 如 map810
        yaml_path = pgm.with_suffix('.yaml')
        png_path = pgm.with_suffix('.png')

        # 1. 转换 pgm → png
        img = Image.open(pgm)
        img.save(png_path, 'PNG')
        w, h = img.size
        print(f'  [转换] {name}.pgm ({w}x{h}) → {name}.png')

        # 2. 读取 yaml 参数
        yaml_data = parse_yaml(yaml_path)
        if yaml_data is None:
            print(f'  [警告] {name}.yaml 不存在，使用默认参数')
            resolution, origin_x, origin_y = 0.05, -50.0, -50.0
        else:
            resolution = float(yaml_data.get('resolution', 0.05))
            ox, oy, _ = parse_origin(yaml_data.get('origin', '[-50.0, -50.0, 0.0]'))
            origin_x, origin_y = ox, oy

        print(f'  [参数] resolution={resolution} m/px, origin=({origin_x}, {origin_y}), size={w}x{h}')

        # 3. 收集 .env 配置片段（前端按车 id 读取）
        env_lines.append(f'# {name} 地图参数（由 sync_maps.py 自动生成）')
        env_lines.append(f'VITE_MAP_{name.upper()}_W={w}')
        env_lines.append(f'VITE_MAP_{name.upper()}_H={h}')
        env_lines.append(f'VITE_MAP_{name.upper()}_RESOLUTION={resolution}')
        env_lines.append(f'VITE_MAP_{name.upper()}_ORIGIN_X={origin_x}')
        env_lines.append(f'VITE_MAP_{name.upper()}_ORIGIN_Y={origin_y}')
        env_lines.append('')

    print('\n========== .env 配置片段（复制到 .env）==========')
    print('\n'.join(env_lines))
    print('==========================================')
    print(f'\n完成。PNG 文件位于: {MAP_DIR}')


if __name__ == '__main__':
    main()
