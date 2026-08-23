# -*- coding: utf-8 -*-
"""一句话体验 demo：宝马 X3 迎风仿真。

真实车型请用 --upload-stl 上传 STL（参数化库只有 Ahmed/简化车/圆柱/NACA，
"宝马X3" 会退化为简化车形并在报告中如实标注来源）。
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from aeroforge.agents import OrchestratorAgent  # noqa: E402

UPLOAD = sys.argv[1] if len(sys.argv) > 1 else None


async def main():
    kw = {"upload_stl_path": UPLOAD} if UPLOAD else {}
    prompt = ("做一辆 宝马X3 的迎风 CFD 仿真，风速 120 km/h，风向角 0 度，"
              "我要风洞烟线可视化")
    state = await OrchestratorAgent("workspace").run(prompt, **kw)
    rep = state["report"]
    print(f"\n对象: {rep.task.object_name}  风速: {rep.task.velocity:.1f} m/s  "
          f"风向角: {rep.task.yaw_angle_deg:g}°")
    print(f"几何来源: {rep.geometry.source}")
    print(f"报告: {rep.markdown_report_path}")
    fc = rep.simulation.force_coeffs
    print(f"Cd = {fc.cd:.4f}" if fc else "Cd = N/A（dry-run：无 OpenFOAM 运行时）")
    for x in rep.visualization_paths:
        print(f"  可视化: {x}")


if __name__ == "__main__":
    asyncio.run(main())
