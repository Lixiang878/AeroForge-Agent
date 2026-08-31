"""aeroforge 命令行：一句话 → 参数化几何 → OpenFOAM 仿真 → 风洞级可视化。"""
import argparse
import asyncio
import sys
from .agents import OrchestratorAgent
from .tools.windtunnel_viz import DEFAULT_ANIMATION_FPS, parse_vehicle_color


def main():
    p = argparse.ArgumentParser(
        prog="aeroforge",
        description='例：aeroforge "做 Ahmed body 迎风仿真，风速 40 m/s，风向角 0 度"')
    p.add_argument("prompt", help="自然语言任务描述")
    p.add_argument("--workspace", default="workspace")
    p.add_argument("--upload-stl", default=None,
                   help="上传真实模型 STL（真实车型等强烈推荐）")
    p.add_argument("--upload-ground-clearance", type=float, default=None,
                   help="上传模型最低点相对 z=0 地面的高度（m）")
    p.add_argument("--upload-scale", type=float, default=None,
                   help="上传 STL 的统一尺度因子（默认按资产清单 m/cm/mm；无清单为 1）")
    p.add_argument("--upload-rotation-z", type=float, default=0.0,
                   help="上传 STL 绕全局 z 轴旋转角（deg，默认 0）")
    p.add_argument("--model-manifest", default=None,
                   help="具体车型资产清单 JSON（来源、许可、SHA-256、单位和轴向）")
    p.add_argument("--vehicle-color", default="#102947",
                   help="渲染车漆颜色，格式 #RRGGBB")
    p.add_argument("--animation", action="store_true",
                   help="生成真实场动画；稳态默认示踪粒子输运，瞬态使用物理时间步")
    p.add_argument("--animation-mode", default="auto",
                   choices=("auto", "steady_particles", "steady_orbit", "transient"),
                   help="动画模式（auto按源求解器选择，不能把瞬态数据改标稳态）")
    p.add_argument("--animation-frames", type=int, default=120,
                   help="动画帧数（默认 120；稳态示踪粒子更连贯）")
    p.add_argument("--animation-fps", type=int, default=DEFAULT_ANIMATION_FPS,
                   help=f"动画帧率（默认 {DEFAULT_ANIMATION_FPS}；120 帧约 3 秒）")
    p.add_argument("--no-viz", action="store_true", help="跳过高清可视化渲染")
    a = p.parse_args()
    try:
        parse_vehicle_color(a.vehicle_color)
    except ValueError as exc:
        p.error(str(exc))
    if a.animation_frames < 2 or a.animation_fps <= 0:
        p.error("animation frames must be >= 2 and fps must be > 0")
    kw = {}
    if a.upload_stl:
        kw["upload_stl_path"] = a.upload_stl
        if a.upload_ground_clearance is not None:
            kw["upload_ground_clearance"] = a.upload_ground_clearance
        if a.upload_scale is not None:
            kw["upload_scale"] = a.upload_scale
        kw["upload_rotation_z_deg"] = a.upload_rotation_z
        if a.model_manifest:
            kw["model_manifest_path"] = a.model_manifest
    kw["vehicle_color"] = a.vehicle_color
    kw["animate"] = a.animation
    kw["animation_mode"] = a.animation_mode
    kw["animation_frames"] = a.animation_frames
    kw["animation_fps"] = a.animation_fps
    if a.no_viz:
        kw["render"] = False
    try:
        r = asyncio.run(OrchestratorAgent(a.workspace).run(a.prompt, **kw))
    except (OSError, ValueError) as exc:
        print(f"输入/几何错误: {exc}", file=sys.stderr)
        return 2
    rep = r["report"]
    print(f"\n报告: {rep.markdown_report_path}")
    fc = rep.simulation.force_coeffs if rep.simulation.converged else None
    if fc:
        line = f"Cd = {fc.cd:.4f}"
        if fc.cd_pressure is not None and fc.cd_viscous is not None:
            line += f"（压差 {fc.cd_pressure:.4f} + 摩擦 {fc.cd_viscous:.4f}）"
        print(line)
    else:
        reason = ("dry-run：无 OpenFOAM 运行时"
                  if any("dry-run" in note for note in rep.simulation.notes)
                  else "未通过收敛门禁")
        print(f"Cd = N/A（{reason}，不虚构数值）")
    if rep.visualization_paths:
        print("高清可视化:")
        for x in rep.visualization_paths:
            print(f"  {x}")
    elif rep.visualization_note:
        print(f"可视化: {rep.visualization_note}")
    animation_paths = getattr(rep, "animation_paths", [])
    if animation_paths:
        print("真实场动画:")
        for x in animation_paths:
            print(f"  {x}")
    interactive_paths = getattr(rep, "interactive_paths", [])
    if interactive_paths:
        print("可拖动三维交互视图:")
        for x in interactive_paths:
            print(f"  {x}")
    return 1 if r.get("status") == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
