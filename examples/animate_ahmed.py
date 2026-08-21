# -*- coding: utf-8 -*-
"""Ahmed body 瞬态动画仿真（pimpleFoam，供 ParaView 播放动态过程）。

流程：
1. 复用最近一次已收敛稳态算例的网格（不重新网格化）；
2. 重建瞬态字典（pimpleFoam / Euler ddt / PIMPLE / CFL 自适应步长）；
3. 把收敛稳态场拷贝为 t=0 初场，从该状态继续瞬态演化
   （尾流涡脱落 / 摆动将自然发展出来）；
4. 运行 pimpleFoam，按动画帧间隔写盘（默认 ~40 帧）；
5. 完成后提示 ParaView 打开方式：直接打开 case 目录下的 `<name>.foam`
   文件（OpenFOAM reader），时间轴即可播放。

用法：
    python examples/animate_ahmed.py [--task task_XXXX] [--frames 40] [--flow-times 3]
"""
import argparse
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'src'))

from aeroforge.core.runtime_bridge import RuntimeBridge, detect_runtime  # noqa: E402
from aeroforge.tools.case_builder import CaseSpec, build_case  # noqa: E402
from aeroforge.tools.stl_tools import read_stl_bbox  # noqa: E402


def find_latest_task() -> Path:
    ws = Path('workspace')
    tasks = [p for p in ws.glob('task_*')
             if (p / 'case' / 'constant' / 'polyMesh').exists()]
    if not tasks:
        raise SystemExit('[animate] 未找到已生成网格的算例，请先运行 verify_ahmed.py')
    return max(tasks, key=lambda p: p.stat().st_mtime)


def latest_field_dir(case: Path) -> Path:
    dirs = [d for d in case.iterdir() if d.is_dir() and d.name.replace('.', '', 1).isdigit()]
    if not dirs:
        raise SystemExit('[animate] case 中没有可用的时间场目录')
    return max(dirs, key=lambda d: float(d.name))


def main() -> int:
    ap = argparse.ArgumentParser(description="Ahmed body transient animation run")
    ap.add_argument("--task", default=None, help="指定 task 目录名（默认取最新）")
    ap.add_argument("--frames", type=int, default=40, help="动画帧数（写盘次数）")
    ap.add_argument("--flow-times", type=float, default=3.0,
                    help="仿真物理时长 = flow-times × L/U（默认 3 个对流时间尺度）")
    ap.add_argument("--slant", type=float, default=20.0)
    args = ap.parse_args()

    if not detect_runtime().available:
        print('[animate] 未检测到 OpenFOAM 运行时，无法运行瞬态仿真。')
        return 2

    task = Path('workspace') / args.task if args.task else find_latest_task()
    case = task / 'case'
    print(f'[animate] 复用算例: {case}')

    # ---- 重建瞬态字典（网格 constant/polyMesh 不受影响）
    stl = task / 'geometry' / 'model.stl'
    bbox = read_stl_bbox(stl)
    L = bbox.x_max - bbox.x_min
    end_time = args.flow_times * L / 40.0
    spec = CaseSpec(stl_path=stl, surface='body', bbox=bbox, velocity=40.0,
                    solver_mode='transient', end_time=end_time,
                    write_interval_t=end_time / args.frames,
                    max_co=2.0,
                    base_cells_per_L=22, surface_refine_level=3)
    build_case(case, spec)
    print(f'[animate] 瞬态字典已生成: endTime={end_time:.4f}s, '
          f'写盘间隔={end_time / args.frames:.5f}s (~{args.frames} 帧)')

    # ---- 收敛稳态场 → t=0 初场（并清理旧的伪时间目录，保证 ParaView 时间轴干净）
    zero = case / '0'
    if (zero / 'U').exists() and (zero / 'p').exists():
        # 0/ 已是上次拷贝的收敛初场（避免从被中断的半成品帧继续）
        print('[animate] 复用已有 0/ 收敛初场')
    else:
        src = latest_field_dir(case)
        for f in ('U', 'p', 'k', 'omega', 'nut'):
            if (src / f).exists():
                shutil.copy2(src / f, zero / f)
        if (src / 'phi').exists():
            shutil.copy2(src / 'phi', zero / 'phi')
        print(f'[animate] 初场: {src.name} -> 0/')
    for d in case.iterdir():
        if d.is_dir() and d.name != '0' and d.name.replace('.', '', 1).isdigit():
            shutil.rmtree(d)
    shutil.rmtree(case / 'postProcessing', ignore_errors=True)  # 旧力系数数据
    print('[animate] 旧时间目录与后处理数据已清理')

    # ---- 运行 pimpleFoam
    bridge = RuntimeBridge()
    print('[animate] 开始 pimpleFoam（尾流涡脱落发展，需要较长时间）...')
    res = bridge.run(['pimpleFoam'], cwd=case, timeout=7200)
    log = Path(res['log_path']) if res.get('log_path') else case / 'log.pimpleFoam'
    tail = log.read_text(encoding='utf-8', errors='ignore')[-600:] if log.exists() else ''
    print(f'[animate] pimpleFoam rc={res.get("returncode")}')
    print(tail[-400:])

    foam_file = case / (case.name + '.foam')
    print()
    print('=' * 60)
    print('ParaView 打开方式:')
    print(f'  1. 打开文件: {foam_file}')
    print('     （File -> Open，文件类型自动识别为 OpenFOAM reader）')
    print('  2. Apply 后，工具栏时间轴选择最后一帧之前的全部时间步')
    print('  3. 变量选 U，可用 Glyph/StreamTracer/Slice 观察尾流涡结构')
    print('  4. 播放按钮即为动态过程（涡脱落/尾迹摆动）')
    print('=' * 60)
    return 0 if res.get('returncode') == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
