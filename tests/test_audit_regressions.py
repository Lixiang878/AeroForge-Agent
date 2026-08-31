import asyncio
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

import aeroforge
from aeroforge.agents.physics_config import PhysicsConfigAgent
from aeroforge.agents.simulation_pilot import SimulationPilotAgent
from aeroforge.agents.mesh_smith import MeshSmithAgent
from aeroforge.agents import OrchestratorAgent
from aeroforge.core.models import (
    BoundingBox,
    GeometryInfo,
    ForceCoeffs,
    FinalReport,
    MeshReport,
    Regime,
    SimReport,
    SimulationTask,
)
from aeroforge.core.runtime_bridge import RuntimeInfo
from aeroforge.tools.case_builder import CaseSpec, build_case, domain_from_bbox
from aeroforge.tools.geometry_tools import car_triangles, write_ascii_stl, create_car_stl, create_cylinder_stl
from aeroforge.tools.geometry_tools import validate_stl
from aeroforge.tools import openfoam_tools
from aeroforge.tools.openfoam_tools import parse_force_coeffs
from aeroforge.tools.openfoam_tools import run_mesh_sequence
from aeroforge.tools.stl_tools import (
    _iter_triangles,
    ahmed_body_stl,
    is_watertight,
    prepare_stl_for_cfd,
    signed_volume,
    stl_surface_area,
    read_stl_bbox,
)
from aeroforge.tools.viz_tools import generate_markdown_report
from aeroforge.agents.requirement_parser import RequirementParserAgent
from aeroforge.agents.geometry_hunter import GeometryHunterAgent
from aeroforge.tools.physics_tools import check_flux_conservation, check_symmetry


def _coeff_row(time: int, cd: float) -> str:
    values = [time, cd, cd / 2, cd / 2, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    return " ".join(f"{v:g}" for v in values)


def test_force_coeff_parser_uses_file_with_latest_time(tmp_path):
    d = tmp_path / "postProcessing" / "forceCoeffs1" / "0"
    d.mkdir(parents=True)
    (d / "coefficient.dat").write_text(
        "# Time Cd Cd(f) Cd(r) Cl Cl(f) Cl(r) Cm\n"
        + _coeff_row(20, 0.40) + "\n",
        encoding="utf-8",
    )
    (d / "coefficient_0.dat").write_text(
        "# Time Cd Cd(f) Cd(r) Cl Cl(f) Cl(r) Cm\n"
        + _coeff_row(10, 0.20) + "\n",
        encoding="utf-8",
    )
    parsed = parse_force_coeffs(tmp_path)
    assert parsed is not None
    assert parsed.cd == pytest.approx(0.40)


def test_continuity_error_parser_returns_latest_global_percent(tmp_path):
    log = tmp_path / "log.simpleFoam"
    log.write_text(
        "time step continuity errors : sum local = 0.01, global = -0.002, cumulative = 0.1\n"
        "time step continuity errors : sum local = 0.003, global = 0.0005, cumulative = 0.11\n",
        encoding="utf-8",
    )
    assert openfoam_tools.parse_continuity_error(log) == pytest.approx(0.05)


def test_simulation_does_not_call_high_residual_run_converged(tmp_path, monkeypatch):
    import aeroforge.agents.simulation_pilot as pilot

    log = tmp_path / "log.simpleFoam"
    log.write_text(
        "Time = 10\n"
        "smoothSolver: Solving for Ux, Initial residual = 0.1, Final residual = 0.01, No Iterations 1\n"
        "smoothSolver: Solving for p, Initial residual = 0.1, Final residual = 0.01, No Iterations 1\n"
        "time step continuity errors : sum local = 0.001, global = 0.0001, cumulative = 0.001\n"
        "End\n",
        encoding="utf-8",
    )
    d = tmp_path / "postProcessing" / "forceCoeffs1" / "0"
    d.mkdir(parents=True)
    (d / "coefficient.dat").write_text(_coeff_row(10, 0.3) + "\n", encoding="utf-8")

    class FakeBridge:
        info = RuntimeInfo(backend="native")
        available = True

    monkeypatch.setattr(pilot, "RuntimeBridge", lambda: FakeBridge())
    monkeypatch.setattr(
        pilot,
        "run_solver",
        lambda *args, **kwargs: {"returncode": 0, "log_path": str(log)},
    )

    result = asyncio.run(
        SimulationPilotAgent().run(
            {"case_dir": tmp_path, "solver": "simpleFoam"},
            {"status": "completed", "mesh": MeshReport(mesh_path=tmp_path, cell_count=1, passed_checkmesh=True)},
        )
    )
    assert result["status"] == "failed"
    assert result["simulation"].converged is False
    assert any("残差" in note for note in result["notes"])
    assert any("残差" in note for note in result["simulation"].notes)


def test_simulation_report_contains_continuity_error(tmp_path, monkeypatch):
    import aeroforge.agents.simulation_pilot as pilot

    log = tmp_path / "log.simpleFoam"
    log.write_text(
        "Time = 10\n"
        "smoothSolver: Solving for Ux, Initial residual = 0.1, Final residual = 1e-5, No Iterations 1\n"
        "smoothSolver: Solving for p, Initial residual = 0.1, Final residual = 1e-5, No Iterations 1\n"
        "time step continuity errors : sum local = 0.001, global = 0.0005, cumulative = 0.001\n"
        "End\n",
        encoding="utf-8",
    )
    d = tmp_path / "postProcessing" / "forceCoeffs1" / "0"
    d.mkdir(parents=True)
    (d / "coefficient.dat").write_text(_coeff_row(10, 0.3) + "\n", encoding="utf-8")

    class FakeBridge:
        info = RuntimeInfo(backend="native")
        available = True

    monkeypatch.setattr(pilot, "RuntimeBridge", lambda: FakeBridge())
    monkeypatch.setattr(
        pilot,
        "run_solver",
        lambda *args, **kwargs: {"returncode": 0, "log_path": str(log)},
    )
    result = asyncio.run(
        SimulationPilotAgent().run(
            {"case_dir": tmp_path, "solver": "simpleFoam"},
            {"status": "completed", "mesh": MeshReport(mesh_path=tmp_path, cell_count=1, passed_checkmesh=True)},
        )
    )
    assert result["simulation"].flux_error_percent == pytest.approx(0.05)


def test_simulation_requires_all_rans_residual_fields(tmp_path, monkeypatch):
    import aeroforge.agents.simulation_pilot as pilot

    log = tmp_path / "log.simpleFoam"
    log.write_text(
        "Time = 10\n"
        "smoothSolver: Solving for Ux, Initial residual = 0.1, Final residual = 1e-5, No Iterations 1\n"
        "smoothSolver: Solving for p, Initial residual = 0.1, Final residual = 1e-5, No Iterations 1\n"
        "time step continuity errors : sum local = 0.001, global = 0.0005, cumulative = 0.001\n"
        "End\n",
        encoding="utf-8",
    )
    d = tmp_path / "postProcessing" / "forceCoeffs1" / "0"
    d.mkdir(parents=True)
    (d / "coefficient.dat").write_text(_coeff_row(10, 0.3) + "\n", encoding="utf-8")

    class FakeBridge:
        info = RuntimeInfo(backend="native")
        available = True

    monkeypatch.setattr(pilot, "RuntimeBridge", lambda: FakeBridge())
    monkeypatch.setattr(
        pilot,
        "run_solver",
        lambda *args, **kwargs: {"returncode": 0, "log_path": str(log)},
    )
    result = asyncio.run(
        SimulationPilotAgent().run(
            {"case_dir": tmp_path, "solver": "simpleFoam"},
            {"status": "completed", "mesh": MeshReport(mesh_path=tmp_path, cell_count=1, passed_checkmesh=True)},
        )
    )
    assert result["status"] == "failed"
    assert any("残差字段缺失" in note for note in result["notes"])


def test_simulation_requires_mesh_report_to_pass_checkmesh(tmp_path, monkeypatch):
    import aeroforge.agents.simulation_pilot as pilot

    class FakeBridge:
        info = RuntimeInfo(backend="native")
        available = True

    monkeypatch.setattr(pilot, "RuntimeBridge", lambda: FakeBridge())
    monkeypatch.setattr(
        pilot,
        "run_solver",
        lambda *args, **kwargs: pytest.fail("solver must not run on failed mesh"),
    )
    result = asyncio.run(
        SimulationPilotAgent().run(
            {"case_dir": tmp_path, "solver": "simpleFoam"},
            {
                "status": "completed",
                "mesh": MeshReport(mesh_path=tmp_path, passed_checkmesh=False),
            },
        )
    )
    assert result["status"] == "skipped"


def test_simulation_rejects_stale_force_coeff_output(tmp_path, monkeypatch):
    import aeroforge.agents.simulation_pilot as pilot

    log = tmp_path / "log.simpleFoam"
    lines = ["Time = 10"]
    for field in ("Ux", "Uy", "Uz", "p", "k", "omega"):
        lines.append(
            f"smoothSolver: Solving for {field}, Initial residual = 0.1, "
            "Final residual = 1e-5, No Iterations 1"
        )
    lines.extend([
        "time step continuity errors : sum local = 0.001, global = 0.0001, cumulative = 0.001",
        "End",
    ])
    log.write_text("\n".join(lines) + "\n", encoding="utf-8")
    d = tmp_path / "postProcessing" / "forceCoeffs1" / "0"
    d.mkdir(parents=True)
    (d / "coefficient.dat").write_text(_coeff_row(10, 0.3) + "\n", encoding="utf-8")

    class FakeBridge:
        info = RuntimeInfo(backend="native")
        available = True

    monkeypatch.setattr(pilot, "RuntimeBridge", lambda: FakeBridge())
    monkeypatch.setattr(
        pilot,
        "run_solver",
        lambda *args, **kwargs: {"returncode": 0, "log_path": str(log)},
    )
    result = asyncio.run(
        SimulationPilotAgent().run(
            {"case_dir": tmp_path, "solver": "simpleFoam"},
            {"status": "completed", "mesh": MeshReport(mesh_path=tmp_path, cell_count=1, passed_checkmesh=True)},
        )
    )
    assert result["status"] == "failed"
    assert any("本次求解更新" in note for note in result["notes"])


def test_transient_task_selects_pimplefoam(tmp_path):
    stl = tmp_path / "model.stl"
    create_car_stl(stl)
    bbox = read_stl_bbox(stl)
    task = SimulationTask(
        user_prompt="瞬态车辆风场",
        regime=Regime.TRANSIENT,
        velocity=20.0,
    )
    parsed = {"task": task}
    geometry = {
        "geometry": GeometryInfo(
            stl_path=stl,
            bbox=bbox,
            characteristic_length=4.7,
            source="test",
        )
    }
    result = asyncio.run(PhysicsConfigAgent().run(parsed, geometry, workspace=tmp_path))
    assert result["solver"] == "pimpleFoam"
    assert result["spec"].solver_mode == "transient"


def test_physics_config_forwards_mesh_and_wall_controls(tmp_path):
    stl = tmp_path / "model.stl"
    create_car_stl(stl)
    bbox = read_stl_bbox(stl)
    task = SimulationTask(user_prompt="可控网格车辆风场", velocity=20.0)
    geometry = {
        "geometry": GeometryInfo(
            stl_path=stl,
            bbox=bbox,
            characteristic_length=4.7,
            source="test",
        )
    }
    result = asyncio.run(
        PhysicsConfigAgent().run(
            {"task": task},
            geometry,
            workspace=tmp_path,
            base_cells_per_L=8,
            surface_refine_level=1,
            wake_refinement=False,
            nose_refinement=False,
            wall_treatment="wallFunction",
            n_wall_layers=2,
        )
    )
    spec = result["spec"]
    assert spec.base_cells_per_L == 8
    assert spec.surface_refine_level == 1
    assert spec.wake_refinement is False
    assert spec.nose_refinement is False
    assert spec.wall_treatment == "wallFunction"
    assert spec.n_wall_layers == 2


def test_domain_top_margin_is_relative_to_body_bbox():
    bbox = BoundingBox(x_min=0, x_max=4, y_min=-1, y_max=1, z_min=10, z_max=12)
    dom = domain_from_bbox(bbox, (3, 7, 2.5, 2))
    assert dom["z_min"] == pytest.approx(0.0)
    assert dom["z_max"] == pytest.approx(16.0)


def test_yaw_uses_open_farfield_side_patches(tmp_path):
    stl = tmp_path / "model.stl"
    create_car_stl(stl)
    bbox = read_stl_bbox(stl)
    case = build_case(
        tmp_path / "case",
        CaseSpec(
            stl_path=stl,
            bbox=bbox,
            velocity=20.0,
            yaw_angle_deg=30.0,
            base_cells_per_L=8,
            surface_refine_level=1,
            wake_refinement=False,
            nose_refinement=False,
            wall_treatment="wallFunction",
        ),
    )
    block = (case / "system" / "blockMeshDict").read_text(encoding="utf-8")
    assert "sideLow\n    {\n        type patch;" in block
    assert "sideHigh\n    {\n        type patch;" in block
    u = (case / "0" / "U").read_text(encoding="utf-8")
    assert "pressureInletOutletVelocity" in u


def test_yaw_reference_area_uses_projected_frontal_area(tmp_path):
    stl = tmp_path / "model.stl"
    create_car_stl(stl)
    bbox = read_stl_bbox(stl)
    yaw = 45.0
    case = build_case(
        tmp_path / "case",
        CaseSpec(
            stl_path=stl,
            bbox=bbox,
            velocity=20.0,
            yaw_angle_deg=yaw,
            base_cells_per_L=8,
            surface_refine_level=1,
            wake_refinement=False,
            nose_refinement=False,
            wall_treatment="wallFunction",
        ),
    )
    import math

    expected = (abs(math.cos(math.radians(yaw))) * (bbox.y_max - bbox.y_min)
                + abs(math.sin(math.radians(yaw))) * (bbox.x_max - bbox.x_min)) * (
                    bbox.z_max - bbox.z_min
                )
    control = (case / "system" / "controlDict").read_text(encoding="utf-8")
    assert f"Aref            {expected:g};" in control


def test_non_slip_upstream_has_no_orphan_ground_patch(tmp_path):
    stl = tmp_path / "model.stl"
    create_car_stl(stl)
    bbox = read_stl_bbox(stl)
    case = build_case(
        tmp_path / "case",
        CaseSpec(
            stl_path=stl,
            bbox=bbox,
            upstream_slip_ground=False,
            base_cells_per_L=8,
            surface_refine_level=1,
            wake_refinement=False,
            nose_refinement=False,
            wall_treatment="wallFunction",
        ),
    )
    block = (case / "system" / "blockMeshDict").read_text(encoding="utf-8")
    assert "groundUpstream" not in block
    for field in ("U", "p", "k", "omega", "nut"):
        text = (case / "0" / field).read_text(encoding="utf-8")
        assert "groundUpstream" not in text


def test_ascii_stl_metrics_are_supported(tmp_path):
    stl = tmp_path / "tetra.stl"
    write_ascii_stl(
        stl,
        [
            ((0, 0, 0), (1, 0, 0), (0, 1, 0)),
            ((0, 0, 0), (0, 0, 1), (1, 0, 0)),
            ((0, 0, 0), (0, 1, 0), (0, 0, 1)),
            ((1, 0, 0), (0, 0, 1), (0, 1, 0)),
        ],
        name="tetra",
    )
    assert stl_surface_area(stl) > 0
    assert is_watertight(stl)
    assert signed_volume(stl) != 0


def test_stl_iterator_streams_instead_of_reading_entire_file(tmp_path, monkeypatch):
    ascii_stl = tmp_path / "cylinder.stl"
    create_cylinder_stl(ascii_stl, segments=8)
    binary_stl = tmp_path / "ahmed.stl"
    ahmed_body_stl(binary_stl, arc_segments=4)

    def reject_read_bytes(self):
        raise AssertionError("large STL parsing must not call Path.read_bytes")

    monkeypatch.setattr(Path, "read_bytes", reject_read_bytes)
    assert len(list(_iter_triangles(ascii_stl))) == 32
    assert len(list(_iter_triangles(binary_stl))) > 0


def test_prepare_stl_for_cfd_merges_and_aligns_ground(tmp_path):
    source = tmp_path / "source.stl"
    write_ascii_stl(
        source,
        [
            ((0, 0, -2), (1, 0, -2), (0, 1, -2)),
            ((0, 0, -2), (0, 0, -1), (1, 0, -2)),
            ((0, 0, -2), (0, 1, -2), (0, 0, -1)),
            ((1, 0, -2), (0, 0, -1), (0, 1, -2)),
        ],
        name="part_a",
    )
    prepared = tmp_path / "prepared.stl"
    bbox = prepare_stl_for_cfd(source, prepared, target_ground_z=0.01)
    assert prepared.stat().st_size == 84 + 4 * 50
    assert bbox.z_min == pytest.approx(0.01)
    assert bbox.z_max == pytest.approx(1.01)
    assert is_watertight(prepared)


def test_prepare_stl_for_cfd_can_rotate_vehicle_into_positive_x_flow(tmp_path):
    source = tmp_path / "offset_tetra.stl"
    write_ascii_stl(
        source,
        [
            ((1, -4, 0), (3, -4, 0), (1, -2, 0)),
            ((1, -4, 0), (1, -4, 1), (3, -4, 0)),
            ((1, -4, 0), (1, -2, 0), (1, -4, 1)),
            ((3, -4, 0), (1, -4, 1), (1, -2, 0)),
        ],
        name="offset_tetra",
    )
    prepared = tmp_path / "rotated.stl"
    bbox = prepare_stl_for_cfd(source, prepared, rotation_z_deg=180.0)
    assert bbox.x_min == pytest.approx(-3.0)
    assert bbox.x_max == pytest.approx(-1.0)
    assert bbox.y_min == pytest.approx(2.0)
    assert bbox.y_max == pytest.approx(4.0)
    assert is_watertight(prepared)


def test_steady_case_writes_small_smoke_runs(tmp_path):
    stl = tmp_path / "car.stl"
    create_car_stl(stl)
    bbox = read_stl_bbox(stl)
    build_case(
        tmp_path / "case",
        CaseSpec(stl_path=stl, bbox=bbox, n_iterations=8),
    )
    control = (tmp_path / "case" / "system" / "controlDict").read_text(
        encoding="utf-8"
    )
    assert "writeInterval   1;" in control
    assert "writeInterval   1;" in control[control.index("forceCoeffs1"):]


def test_drivaerml_example_exposes_explicit_smoke_and_showcase_profiles():
    import importlib.util

    path = Path(__file__).resolve().parents[1] / "examples" / "run_drivaerml.py"
    spec = importlib.util.spec_from_file_location("run_drivaerml_example", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    smoke = module._profile_settings("smoke")
    showcase = module._profile_settings("showcase")
    assert smoke["base_cells_per_L"] == 10
    assert smoke["render"] is False
    assert showcase["base_cells_per_L"] == 12
    assert showcase["wake_refinement"] is True
    assert showcase["nose_refinement"] is False
    assert showcase["render"] is True


def test_streamline_template_explicitly_uses_velocity_vector():
    template = (
        Path(__file__).resolve().parents[1]
        / "src" / "aeroforge" / "tools" / "pv_templates" / "streamline_hd.py"
    ).read_text(encoding="utf-8")
    assert '"Vectors", "vectors"' in template
    assert '"POINTS", "U"' in template


def test_truncated_binary_stl_is_rejected_with_clear_error(tmp_path):
    stl = tmp_path / "truncated.stl"
    data = bytearray(84)
    data[80:84] = (1).to_bytes(4, "little")
    stl.write_bytes(data)
    with pytest.raises(ValueError, match="truncated"):
        read_stl_bbox(stl)


def test_geometry_validation_accepts_binary_stl(tmp_path):
    stl = tmp_path / "ahmed.stl"
    ahmed_body_stl(stl)
    bbox = validate_stl(stl)
    assert bbox.z_max > bbox.z_min


def test_simplified_car_is_lifted_above_ground(tmp_path):
    stl = tmp_path / "car.stl"
    create_car_stl(stl)
    assert read_stl_bbox(stl).z_min > 0


def test_simplified_car_is_one_connected_surface_component():
    triangles = car_triangles()
    edge_to_faces = {}
    for index, triangle in enumerate(triangles):
        for a, b in zip(triangle, triangle[1:] + triangle[:1]):
            edge = tuple(sorted((a, b)))
            edge_to_faces.setdefault(edge, []).append(index)
    graph = {i: set() for i in range(len(triangles))}
    for faces in edge_to_faces.values():
        for face in faces:
            graph[face].update(other for other in faces if other != face)
    seen = set()
    components = 0
    for root in graph:
        if root in seen:
            continue
        components += 1
        stack = [root]
        while stack:
            face = stack.pop()
            if face in seen:
                continue
            seen.add(face)
            stack.extend(graph[face] - seen)
    assert components == 1


def test_ahmed_side_normals_point_outward(tmp_path):
    stl = tmp_path / "ahmed.stl"
    ahmed_body_stl(stl, slant_angle_deg=20, arc_segments=8)
    triangles = list(_iter_triangles(stl))
    ys = [point[1] for triangle in triangles for point in triangle]
    half_width = max(ys)

    def normal_y(triangle):
        a, b, c = triangle
        u = [b[i] - a[i] for i in range(3)]
        v = [c[i] - a[i] for i in range(3)]
        return u[2] * v[0] - u[0] * v[2]

    left = [t for t in triangles if all(point[1] < -half_width + 1e-8 for point in t)]
    right = [t for t in triangles if all(point[1] > half_width - 1e-8 for point in t)]
    assert left and right
    assert all(normal_y(t) < 0 for t in left)
    assert all(normal_y(t) > 0 for t in right)


def test_watertight_check_tolerates_ascii_roundoff(tmp_path):
    stl = tmp_path / "cylinder.stl"
    create_cylinder_stl(stl, segments=32)
    assert is_watertight(stl)


def test_naca_generator_closes_trailing_edge(tmp_path):
    from aeroforge.tools.geometry_tools import create_naca_stl

    stl = tmp_path / "naca.stl"
    create_naca_stl(stl)
    assert is_watertight(stl)


def test_simulation_task_rejects_nonpositive_physics():
    with pytest.raises(ValueError):
        SimulationTask(user_prompt="bad", velocity=0)


def test_case_spec_rejects_invalid_turbulence_and_transient_settings(tmp_path):
    stl = tmp_path / "model.stl"
    create_car_stl(stl)
    bbox = read_stl_bbox(stl)
    with pytest.raises(ValueError):
        CaseSpec(stl_path=stl, bbox=bbox, turbulence_viscosity_ratio=0)
    with pytest.raises(ValueError):
        CaseSpec(stl_path=stl, bbox=bbox, solver_mode="transient", delta_t=0)
    with pytest.raises(ValueError):
        CaseSpec(stl_path=stl, bbox=bbox, base_cell_size=-1)


def test_mesh_stage_rejects_failed_checkmesh_even_with_stale_log(tmp_path, monkeypatch):
    import aeroforge.agents.mesh_smith as mesh_smith

    class FakeBridge:
        info = RuntimeInfo(backend="native")
        available = True

    monkeypatch.setattr(mesh_smith, "RuntimeBridge", lambda: FakeBridge())
    monkeypatch.setattr(mesh_smith, "run_mesh_sequence", lambda *args, **kwargs: {"ok": True, "logs": []})
    monkeypatch.setattr(mesh_smith, "run_checkmesh", lambda *args, **kwargs: {"returncode": 1})
    monkeypatch.setattr(
        mesh_smith,
        "parse_mesh_stats",
        lambda *args, **kwargs: {
            "cell_count": 10,
            "max_non_orthogonality": 1,
            "max_skewness": 1,
            "passed_checkmesh": True,
        },
    )
    result = asyncio.run(
        MeshSmithAgent().run({"case_dir": tmp_path}, {"task": object()})
    )
    assert result["status"] == "failed"


def test_mesh_stage_rejects_missing_cell_count(tmp_path, monkeypatch):
    import aeroforge.agents.mesh_smith as mesh_smith

    class FakeBridge:
        info = RuntimeInfo(backend="native")
        available = True

    monkeypatch.setattr(mesh_smith, "RuntimeBridge", lambda: FakeBridge())
    monkeypatch.setattr(mesh_smith, "run_mesh_sequence", lambda *args, **kwargs: {"ok": True, "logs": []})
    monkeypatch.setattr(mesh_smith, "run_checkmesh", lambda *args, **kwargs: {"returncode": 0})
    monkeypatch.setattr(
        mesh_smith,
        "parse_mesh_stats",
        lambda *args, **kwargs: {
            "cell_count": 0,
            "max_non_orthogonality": 1,
            "max_skewness": 1,
            "passed_checkmesh": True,
        },
    )
    result = asyncio.run(
        MeshSmithAgent().run({"case_dir": tmp_path}, {"task": object()})
    )
    assert result["status"] == "failed"


def test_package_version_matches_release():
    assert aeroforge.__version__ == "0.4.0"


def test_orchestrator_propagates_dry_run_status(tmp_path, monkeypatch):
    import aeroforge.core.runtime_bridge as runtime_bridge

    monkeypatch.setattr(
        runtime_bridge,
        "detect_runtime",
        lambda *args, **kwargs: RuntimeInfo(backend="unavailable"),
    )
    result = asyncio.run(
        OrchestratorAgent(tmp_path).run("Ahmed body 迎风 20 m/s")
    )
    assert result["status"] == "dry-run"
    assert result["stage_status"]["mesh"] == "dry-run"
    assert result["stage_status"]["simulation"] == "dry-run"


def test_report_does_not_promote_failed_force_coeff(tmp_path):
    task = SimulationTask(user_prompt="failed")
    stl = tmp_path / "model.stl"
    create_car_stl(stl)
    bbox = read_stl_bbox(stl)
    report = FinalReport(
        task=task,
        geometry=GeometryInfo(
            stl_path=stl,
            bbox=bbox,
            characteristic_length=4.7,
            source="test",
        ),
        mesh=MeshReport(mesh_path=tmp_path, passed_checkmesh=True),
        simulation=SimReport(
            case_dir=tmp_path,
            converged=False,
            force_coeffs=ForceCoeffs(cd=0.4, cl=0.1),
        ),
        markdown_report_path=tmp_path / "report.md",
    )
    generate_markdown_report(report)
    text = (tmp_path / "report.md").read_text(encoding="utf-8")
    assert "阻力系数 Cd: N/A" in text
    assert "未通过收敛门禁" in text


def test_report_exposes_continuity_gate_for_converged_run(tmp_path):
    task = SimulationTask(user_prompt="converged")
    stl = tmp_path / "model.stl"
    create_car_stl(stl)
    bbox = read_stl_bbox(stl)
    report = FinalReport(
        task=task,
        geometry=GeometryInfo(
            stl_path=stl,
            bbox=bbox,
            characteristic_length=4.7,
            source="test",
        ),
        mesh=MeshReport(mesh_path=tmp_path, passed_checkmesh=True),
        simulation=SimReport(
            case_dir=tmp_path,
            converged=True,
            final_residuals={"Ux": 1e-5},
            force_coeffs=ForceCoeffs(cd=0.4, cl=0.1),
            flux_error_percent=0.05,
        ),
        markdown_report_path=tmp_path / "report.md",
    )
    generate_markdown_report(report)
    text = (tmp_path / "report.md").read_text(encoding="utf-8")
    assert "全局连续性误差: 0.05%" in text


def test_runtime_selects_highest_numeric_openfoam_version(monkeypatch):
    import aeroforge.core.runtime_bridge as runtime_bridge

    monkeypatch.setattr(runtime_bridge.shutil, "which", lambda name: None)
    monkeypatch.setattr(runtime_bridge, "_wsl_exe", lambda: "wsl.exe")

    def fake_run(argv, **kwargs):
        if "ls -1 /usr/lib/openfoam" in argv[-1]:
            return SimpleNamespace(returncode=0, stdout="openfoam9\nopenfoam2412\n")
        return SimpleNamespace(returncode=0, stdout="/usr/bin/simpleFoam\n")

    monkeypatch.setattr(runtime_bridge.subprocess, "run", fake_run)
    info = runtime_bridge._detect_runtime_uncached(timeout=1)
    assert info.version == "openfoam2412"


def test_runtime_timeout_returns_failure_record(monkeypatch, tmp_path):
    import aeroforge.core.runtime_bridge as runtime_bridge

    bridge = runtime_bridge.RuntimeBridge(runtime_bridge.RuntimeInfo(backend="native"))

    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=args[0], timeout=kwargs.get("timeout", 1))

    monkeypatch.setattr(runtime_bridge.subprocess, "run", timeout)
    result = bridge.run(["simpleFoam"], cwd=tmp_path, timeout=1)
    assert result["returncode"] != 0
    assert result["timed_out"] is True


def test_mesh_sequence_propagates_final_dry_run(monkeypatch, tmp_path):
    class FakeBridge:
        def __init__(self):
            self.calls = 0

        def run(self, argv, cwd, timeout):
            self.calls += 1
            if self.calls == 3:
                return {"dry_run": True, "returncode": None, "log_path": None}
            return {"dry_run": False, "returncode": 0, "log_path": str(tmp_path / f"log{self.calls}")}

    result = run_mesh_sequence(tmp_path, FakeBridge())
    assert result["ok"] is False
    assert result["dry_run"] is True
    assert result["stage"] == "snappyHexMesh"


def test_requirement_parser_accepts_signed_yaw_angle():
    for prompt in ("Ahmed body 风速 20 m/s 偏航 -15°",
                   "Ahmed body 风速 20 m/s 偏航角为 -15°"):
        result = asyncio.run(RequirementParserAgent().run(prompt))
        assert result["task"].yaw_angle_deg == pytest.approx(-15.0)


def test_requirement_parser_marks_explicit_upload_source(tmp_path):
    upload = tmp_path / "model.stl"
    upload.write_bytes(b"placeholder")
    result = asyncio.run(
        RequirementParserAgent().run("Ahmed body 20 m/s", upload_stl_path=upload)
    )
    assert result["task"].geometry_source.value == "upload"


def test_requirement_parser_marks_current_parametric_fallback_source():
    result = asyncio.run(RequirementParserAgent().run("Ahmed body 20 m/s"))
    assert result["task"].geometry_source.value == "parametric"


def test_requirement_parser_keeps_simplified_vehicle_name_clean():
    result = asyncio.run(
        RequirementParserAgent().run("简化车辆迎风仿真，风速 20 m/s，风向角 30 度")
    )
    assert result["task"].object_name == "简化车辆"


def test_legacy_physics_checks_fail_closed_without_evidence(tmp_path):
    assert check_flux_conservation(tmp_path) is None
    assert check_symmetry(tmp_path) is None


def test_missing_explicit_upload_fails_instead_of_falling_back(tmp_path):
    missing = tmp_path / "missing.stl"
    task = SimulationTask(user_prompt="upload", upload_stl_path=missing)
    with pytest.raises(FileNotFoundError):
        asyncio.run(GeometryHunterAgent().run({"task": task}, workspace=tmp_path))


def test_uploaded_open_stl_is_rejected_before_meshing(tmp_path):
    upload = tmp_path / "open.stl"
    write_ascii_stl(upload, [
        ((0, 0, 0), (1, 0, 0), (0, 1, 0)),
        ((0, 0, 0), (0, 0, 1), (1, 0, 0)),
        ((0, 0, 0), (0, 1, 0), (0, 0, 1)),
    ])
    task = SimulationTask(user_prompt="upload", upload_stl_path=upload)
    with pytest.raises(ValueError, match="封闭"):
        asyncio.run(GeometryHunterAgent().run({"task": task}, workspace=tmp_path))


def test_orchestrator_aligns_uploaded_vehicle_to_requested_ground(tmp_path, monkeypatch):
    import aeroforge.core.runtime_bridge as runtime_bridge

    source = tmp_path / "source_car.stl"
    create_car_stl(source, ground_clearance=0.12)
    monkeypatch.setattr(
        runtime_bridge,
        "detect_runtime",
        lambda *args, **kwargs: RuntimeInfo(backend="unavailable"),
    )
    result = asyncio.run(
        OrchestratorAgent(tmp_path / "work").run(
            "车辆外流场 20 m/s",
            upload_stl_path=source,
            upload_ground_clearance=0.005,
            render=False,
        )
    )
    geometry = result["report"].geometry
    assert geometry.bbox.z_min == pytest.approx(0.005)
    assert geometry.stl_path.read_bytes()[:5] != b"solid"


def test_cli_returns_nonzero_for_failed_pipeline(monkeypatch, tmp_path):
    import aeroforge.cli as cli

    report = SimpleNamespace(
        markdown_report_path=tmp_path / "report.md",
        simulation=SimpleNamespace(
            converged=False,
            force_coeffs=None,
            notes=["未通过收敛门禁"],
        ),
        visualization_paths=[],
        visualization_note="未收敛",
    )

    class FakeAgent:
        async def run(self, *args, **kwargs):
            return {"status": "failed", "report": report}

    monkeypatch.setattr(cli, "OrchestratorAgent", lambda workspace: FakeAgent())
    monkeypatch.setattr(sys, "argv", ["aeroforge", "test task"])
    assert cli.main() == 1


def test_cli_forwards_upload_geometry_controls(monkeypatch, tmp_path):
    import aeroforge.cli as cli

    report = SimpleNamespace(
        markdown_report_path=tmp_path / "report.md",
        simulation=SimpleNamespace(converged=False, force_coeffs=None, notes=["未收敛"]),
        visualization_paths=[], visualization_note="未收敛",
    )
    captured = {}

    class FakeAgent:
        async def run(self, *args, **kwargs):
            captured.update(kwargs)
            return {"status": "dry-run", "report": report}

    monkeypatch.setattr(cli, "OrchestratorAgent", lambda workspace: FakeAgent())
    monkeypatch.setattr(
        sys,
        "argv",
        ["aeroforge", "vehicle", "--upload-stl", "body.stl",
         "--upload-ground-clearance", "0.005", "--upload-scale", "0.001",
         "--upload-rotation-z", "90"],
    )
    assert cli.main() == 0
    assert captured["upload_ground_clearance"] == pytest.approx(0.005)
    assert captured["upload_scale"] == pytest.approx(0.001)
    assert captured["upload_rotation_z_deg"] == pytest.approx(90.0)


def test_cli_reports_input_error_without_traceback(monkeypatch):
    import aeroforge.cli as cli

    class FakeAgent:
        async def run(self, *args, **kwargs):
            raise FileNotFoundError("上传的 STL 不存在")

    monkeypatch.setattr(cli, "OrchestratorAgent", lambda workspace: FakeAgent())
    monkeypatch.setattr(sys, "argv", ["aeroforge", "test task"])
    assert cli.main() == 2


def test_visualization_does_not_accept_stale_images_after_renderer_failure(tmp_path, monkeypatch):
    import aeroforge.tools.windtunnel_viz as viz

    case = tmp_path / "case"
    (case / "constant" / "polyMesh").mkdir(parents=True)
    (case / "1").mkdir()
    (case / "1" / "U").write_text("internalField uniform (1 0 0);\n", encoding="utf-8")
    results = case / "results"
    results.mkdir()
    for view in ("front", "wake", "side"):
        (results / f"streamline_hd_{view}.png").write_bytes(b"x" * 20_001)
    monkeypatch.setattr(viz, "find_pvpython", lambda: Path("pvpython"))
    monkeypatch.setattr(
        viz.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=1, stdout="", stderr="renderer failed"),
    )
    result = viz.render_case(case, u_free=1.0)
    assert result["status"] == "failed"
