"""核心契约与可视化单元测试（v0.4.0：message_bus/state_machine 死代码已删）。"""
from pathlib import Path

import pytest

from aeroforge.core.models import (
    BoundingBox, FinalReport, GeometryInfo, MeshReport, SimulationTask, SimReport)
from aeroforge.tools.windtunnel_viz import read_freestream, render_case, find_pvpython


def test_find_pvpython_returns_path_or_none():
    r = find_pvpython()
    assert r is None or isinstance(r, Path)


def test_read_freestream_parses_uniform_vector(tmp_path):
    (tmp_path / "0").mkdir()
    (tmp_path / "0" / "U").write_text(
        "dimensions [0 1 -1 0 0 0 0];\ninternalField uniform (40 0 0);\n")
    assert read_freestream(tmp_path) == pytest.approx(40.0)


def test_render_case_skips_without_result_field(tmp_path):
    case = tmp_path / "case"
    case.mkdir()
    (case / "constant" / "polyMesh").mkdir(parents=True)
    (case / "0").mkdir()
    (case / "0" / "U").write_text("internalField uniform (1 0 0);\n")
    r = render_case(case)
    assert r["status"] == "skipped"
    assert r["images"] == []
    assert "非零时刻 U" in r["note"]


def test_final_report_accepts_visualization_note():
    task = SimulationTask(user_prompt="t")
    geo = GeometryInfo(
        stl_path=Path("m.stl"),
        bbox=BoundingBox(x_min=0, x_max=1, y_min=0, y_max=1, z_min=0, z_max=1),
        characteristic_length=1.0, source="parametric_test")
    mesh = MeshReport(mesh_path=Path("."))
    sim = SimReport(case_dir=Path("."), converged=False)
    rep = FinalReport(task=task, geometry=geo, mesh=mesh, simulation=sim,
                      markdown_report_path=Path("r.md"),
                      visualization_note="pvpython 未找到")
    assert rep.visualization_note == "pvpython 未找到"
