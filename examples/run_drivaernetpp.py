# -*- coding: utf-8 -*-
"""Run one selected, native DrivAerNet++ STL through AeroForge.

The dataset is not bulk-downloaded by this example.  Pass either a local STL
path or ``--dataset-dir`` plus one exact design ID after placing that selected
subset on the E: workspace.
"""
import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from aeroforge.agents import OrchestratorAgent  # noqa: E402
from aeroforge.tools.drivaernet_adapter import (  # noqa: E402
    discover_native_stl,
    validate_native_stl,
)


def _settings(profile: str) -> dict:
    if profile == "showcase":
        return {
            "base_cells_per_L": 12,
            "surface_refine_level": 1,
            "max_global_cells": 500_000,
            "wake_refinement": True,
            "nose_refinement": False,
            "wall_treatment": "wallFunction",
            "render": True,
            "iterations": 800,
        }
    return {
        "base_cells_per_L": 10,
        "surface_refine_level": 1,
        "max_global_cells": 500_000,
        "wake_refinement": False,
        "nose_refinement": False,
        "wall_treatment": "wallFunction",
        "render": False,
        "iterations": 160,
    }


async def _run(args: argparse.Namespace, mesh: Path, design_id: str) -> int:
    settings = _settings(args.profile)
    iterations = args.iterations if args.iterations is not None else settings.pop("iterations")
    state = await OrchestratorAgent(args.workspace).run(
        f"DrivAerNet++ {design_id} 车辆外流场 {args.velocity:g} m/s",
        upload_stl_path=mesh,
        upload_ground_clearance=args.ground_clearance,
        geometry_source_label=f"DrivAerNet++ {design_id} (CC BY-NC 4.0)",
        n_iterations=iterations,
        vehicle_color=args.vehicle_color,
        **settings,
    )
    simulation = state["outputs"]["simulation"]["simulation"]
    print(f"状态: {state['status']}  设计: {design_id}  case: {state['outputs']['physics']['case_dir']}")
    print(f"收敛: {simulation.converged}  报告: {state['report'].markdown_report_path}")
    if simulation.converged and simulation.force_coeffs is not None:
        print(f"Cd={simulation.force_coeffs.cd:.5f}, Cl={simulation.force_coeffs.cl:.5f}")
    else:
        print("Cd=N/A（未通过收敛门禁，不能发布气动系数）")
    return 0 if state["status"] == "completed" else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one native DrivAerNet++ design")
    parser.add_argument("stl", type=Path, nargs="?", help="selected native STL")
    parser.add_argument("--dataset-dir", type=Path, help="local E: directory containing selected STL subset")
    parser.add_argument("--design-id", help="exact DrivAerNet++ design ID")
    parser.add_argument("--workspace", type=Path, default=Path("workspace/drivaernetpp"))
    parser.add_argument("--velocity", type=float, default=30.0)
    parser.add_argument("--iterations", type=int, default=None)
    parser.add_argument("--ground-clearance", type=float, default=0.005)
    parser.add_argument("--vehicle-color", default="#1A80E6")
    parser.add_argument("--profile", choices=("smoke", "showcase"), default="showcase")
    args = parser.parse_args()
    if args.dataset_dir is not None:
        if not args.design_id or args.stl is not None:
            parser.error("--dataset-dir requires --design-id and must replace the positional STL")
        try:
            mesh = discover_native_stl(args.dataset_dir, args.design_id)
        except (FileNotFoundError, ValueError) as exc:
            parser.error(str(exc))
    else:
        if args.stl is None:
            parser.error("pass a selected native STL or --dataset-dir + --design-id")
        mesh = args.stl.resolve()
        if not mesh.is_file():
            parser.error(f"STL not found: {mesh}")
    design_id = args.design_id or mesh.stem
    gate = validate_native_stl(mesh)
    if gate["status"] != "passed":
        parser.error("native STL quality gate failed: " + "; ".join(gate["errors"]))
    return asyncio.run(_run(args, mesh, design_id))


if __name__ == "__main__":
    raise SystemExit(main())
