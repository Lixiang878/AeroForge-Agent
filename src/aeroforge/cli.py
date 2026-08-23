"""aeroforge 命令行：一句话 → 参数化几何 → OpenFOAM 仿真 → 风洞级可视化。"""
import argparse
import asyncio
from .agents import OrchestratorAgent


def main():
    p = argparse.ArgumentParser(
        prog="aeroforge",
        description='例：aeroforge "做 Ahmed body 迎风仿真，风速 40 m/s，风向角 0 度"')
    p.add_argument("prompt", help="自然语言任务描述")
    p.add_argument("--workspace", default="workspace")
    p.add_argument("--upload-stl", default=None,
                   help="上传真实模型 STL（真实车型等强烈推荐）")
    p.add_argument("--no-viz", action="store_true", help="跳过高清可视化渲染")
    a = p.parse_args()
    kw = {}
    if a.upload_stl:
        kw["upload_stl_path"] = a.upload_stl
    if a.no_viz:
        kw["render"] = False
    r = asyncio.run(OrchestratorAgent(a.workspace).run(a.prompt, **kw))
    rep = r["report"]
    print(f"\n报告: {rep.markdown_report_path}")
    fc = rep.simulation.force_coeffs
    if fc:
        line = f"Cd = {fc.cd:.4f}"
        if fc.cd_pressure is not None and fc.cd_viscous is not None:
            line += f"（压差 {fc.cd_pressure:.4f} + 摩擦 {fc.cd_viscous:.4f}）"
        print(line)
    else:
        print("Cd = N/A（dry-run：无 OpenFOAM 运行时或未收敛，不虚构数值）")
    if rep.visualization_paths:
        print("高清可视化:")
        for x in rep.visualization_paths:
            print(f"  {x}")
    elif rep.visualization_note:
        print(f"可视化: {rep.visualization_note}")


if __name__ == "__main__":
    main()
