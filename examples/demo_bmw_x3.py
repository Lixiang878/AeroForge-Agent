# -*- coding: utf-8 -*-
"""一句话体验 demo：宝马 X3 迎风仿真。

真实车型必须同时传入有授权且封闭的 STL 与资产清单；系统不会把“宝马X3”
静默替换为简化车。
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from aeroforge.agents import OrchestratorAgent  # noqa: E402

UPLOAD = sys.argv[1] if len(sys.argv) > 1 else None
MANIFEST = sys.argv[2] if len(sys.argv) > 2 else None
if not UPLOAD or not MANIFEST:
    raise SystemExit(
        "用法: python examples/demo_bmw_x3.py "
        "<授权且封闭的宝马X3 STL> <manifest.json>")


async def main():
    kw = {
        "upload_stl_path": UPLOAD,
        "model_manifest_path": MANIFEST,
        "vehicle_color": "#1A80E6",
        "animate": True,
    }
    prompt = ("做一辆 宝马X3 的迎风 CFD 仿真，风速 120 km/h，风向角 0 度，"
              "我要风洞烟线可视化")
    state = await OrchestratorAgent("workspace").run(prompt, **kw)
    rep = state["report"]
    print(f"\n对象: {rep.task.object_name}  风速: {rep.task.velocity:.1f} m/s  "
          f"风向角: {rep.task.yaw_angle_deg:g}°")
    print(f"几何来源: {rep.geometry.source}")
    print(f"报告: {rep.markdown_report_path}")
    fc = rep.simulation.force_coeffs if rep.simulation.converged else None
    if fc:
        print(f"Cd = {fc.cd:.4f}")
    else:
        reason = ("dry-run：无 OpenFOAM 运行时"
                  if any("dry-run" in note for note in rep.simulation.notes)
                  else "未通过收敛门禁")
        print(f"Cd = N/A（{reason}）")
    for x in rep.visualization_paths:
        print(f"  可视化: {x}")
    for x in rep.animation_paths:
        print(f"  动画: {x}")


if __name__ == "__main__":
    asyncio.run(main())
