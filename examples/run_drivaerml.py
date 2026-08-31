# -*- coding: utf-8 -*-
"""Run the public DrivAerML STL through the AeroForge pipeline.

This example defaults to a cheap import/smoke profile.  The explicit
``showcase`` profile enables a denser wake region and real ParaView renders;
it is still not a mesh-independent production study.

Usage:
    python examples/run_drivaerml.py path/to/body_drivaerml_run_1.stl
    python examples/run_drivaerml.py path/to/body_drivaerml_run_1.stl --profile showcase
"""
import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from aeroforge.agents import OrchestratorAgent  # noqa: E402


def _profile_settings(profile: str) -> dict:
    """Return explicit, reviewable settings for the two supported demo modes."""
    if profile == "showcase":
        return {
            "base_cells_per_L": 12,
            "surface_refine_level": 1,
            "max_global_cells": 500_000,
            "wake_refinement": True,
            "nose_refinement": False,
            "wall_treatment": "wallFunction",
            "render": True,
        }
    if profile == "smoke":
        return {
            "base_cells_per_L": 10,
            "surface_refine_level": 1,
            "max_global_cells": 500_000,
            "wake_refinement": False,
            "nose_refinement": False,
            "wall_treatment": "wallFunction",
            "render": False,
        }
    raise ValueError(f"unknown DrivAerML profile: {profile}")


def _default_iterations(profile: str) -> int:
    """Keep smoke cheap while giving the showcase wake enough steady iterations."""
    return 800 if profile == "showcase" else 160


async def main() -> int:
    parser = argparse.ArgumentParser(description="DrivAerML STL CFD run")
    parser.add_argument("stl", type=Path, help="closed DrivAerML STL")
    parser.add_argument("--workspace", type=Path, default=Path("workspace/drivaerml"))
    parser.add_argument("--velocity", type=float, default=30.0)
    parser.add_argument(
        "--iterations", type=int, default=None,
        help="稳态迭代数；未指定时 smoke=160，showcase=800",
    )
    parser.add_argument(
        "--profile", choices=("smoke", "showcase"), default="smoke",
        help="smoke=快速导入验证；showcase=尾流加密并生成三机位图（仍非生产网格）",
    )
    args = parser.parse_args()
    if not args.stl.exists():
        parser.error(f"STL not found: {args.stl}")

    settings = _profile_settings(args.profile)
    iterations = args.iterations if args.iterations is not None else _default_iterations(args.profile)
    state = await OrchestratorAgent(args.workspace).run(
        f"车辆外流场 {args.velocity:g} m/s",
        upload_stl_path=args.stl,
        upload_ground_clearance=0.005,
        geometry_source_label="DrivAerML run 1 (CC BY-SA 4.0)",
        n_iterations=iterations,
        **settings,
    )
    report = state["report"]
    mesh = state["outputs"]["mesh"]["mesh"]
    sim = state["outputs"]["simulation"]["simulation"]
    print(f"状态: {state['status']}  case: {state['outputs']['physics']['case_dir']}")
    print(f"网格: {mesh.cell_count} cells, checkMesh={mesh.passed_checkmesh}")
    print(f"收敛: {sim.converged}, 残差: {sim.final_residuals}")
    if sim.converged and sim.force_coeffs is not None:
        print(f"Cd={sim.force_coeffs.cd:.5f}, Cl={sim.force_coeffs.cl:.5f}")
    else:
        print("Cd=N/A（未通过收敛门禁，不能发布气动系数）")
    print(f"报告: {report.markdown_report_path}")
    return 0 if state["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
