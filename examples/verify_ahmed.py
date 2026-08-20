"""Ahmed body 端到端基准验证（真实 OpenFOAM 求解路径）。

流程：需求解析 -> Ahmed 参数化几何（含前鼻圆角） -> 从零生成 case
-> blockMesh/surfaceFeatureExtract/snappyHexMesh/checkMesh
-> simpleFoam (k-omega SST) -> Cd 提取 -> 与实验值对比
-> 输出 verification_report.md

验证角选择：
- 默认 20°（附体流动，稳态 RANS 适用区，定量通过判据 ±10%，参考 0.197）；
- --slant 25 复现经典工况（参考 0.285，处于分离双稳态区，稳态 RANS
  已知高估，结果如实报告）。

要求：本机 PATH 有 OpenFOAM，或 Windows + WSL 内装有 OpenFOAM
（RuntimeBridge 自动探测）。无运行时则显式报告 dry-run 并退出码 2。

用法：
    python examples/verify_ahmed.py [--slant 20] [--iterations 800] [--velocity 40]
"""
import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from aeroforge.agents import OrchestratorAgent  # noqa: E402
from aeroforge.core.runtime_bridge import detect_runtime  # noqa: E402
from aeroforge.tools.validation import (ahmed_reference, compare_cd,  # noqa: E402
                                        render_validation_markdown)


async def main() -> int:
    ap = argparse.ArgumentParser(description="Ahmed body CFD validation")
    ap.add_argument("--slant", type=float, default=20.0, choices=[20.0, 25.0],
                    help="后窗斜角；20° 为定量通过判据角，25° 为经典报告角")
    ap.add_argument("--iterations", type=int, default=800)
    ap.add_argument("--velocity", type=float, default=40.0,
                    help="来流速度 m/s（默认 40，对应 Re≈2.78e6）")
    ap.add_argument("--refine-level", type=int, default=3,
                    help="表面/尾流加密级数（默认 3；2 更快但偏差更大）")
    ap.add_argument("--base-div", type=int, default=22,
                    help="背景网格密度：特征长度方向单元数（默认 22）")
    args = ap.parse_args()

    runtime = detect_runtime()
    if not runtime.available:
        print("[verify] 未检测到 OpenFOAM 运行时（native/WSL），无法真实求解。")
        print("[verify] dry-run 仅生成可审阅的 case 目录，不出验证结论。")

    prompt = (f'对"Ahmed body {args.slant:g}°"做迎风 CFD 验证，'
              f'风速 {args.velocity:g} m/s，稳态不可压')
    orch = OrchestratorAgent('workspace')
    state = await orch.run(prompt, n_iterations=args.iterations,
                           surface_refine_level=args.refine_level,
                           base_cells_per_L=args.base_div)

    report = state['report']
    sim = state['outputs']['simulation']['simulation']
    mesh = state['outputs']['mesh']['mesh']
    task_dir = Path(report.geometry.stl_path).parents[1]

    extra = {
        "运行时后端": state['outputs']['simulation'].get('runtime_backend', 'n/a'),
        "网格单元数": mesh.cell_count,
        "checkMesh 通过": mesh.passed_checkmesh,
        "求解耗时 (s)": sim.runtime_seconds,
        "最终残差": sim.final_residuals,
        "case 目录": str(state['outputs']['physics']['case_dir']),
    }

    if not runtime.available or sim.force_coeffs is None or not sim.converged:
        print("[verify] 无真实求解结果，验证未执行（dry-run）。")
        (task_dir / 'results' / 'verification_report.md').write_text(
            "# 验证未执行\n\n未检测到 OpenFOAM 运行时或求解未收敛，"
            "按项目约定不发布任何虚构数值。\n", encoding='utf-8')
        return 2

    ref = ahmed_reference(args.slant)
    res = compare_cd(sim.force_coeffs.cd, reference=ref,
                     slant_angle_deg=args.slant)
    md = render_validation_markdown(res, extra)
    out = task_dir / 'results' / 'verification_report.md'
    out.write_text(md, encoding='utf-8')
    print(md)
    print(f"[verify] 报告: {out}")
    return 0 if res.passed else 1


if __name__ == '__main__':
    sys.exit(asyncio.run(main()))
