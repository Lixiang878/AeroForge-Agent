from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest
from PIL import Image

import aeroforge.tools.windtunnel_viz as viz
from aeroforge.agents.geometry_hunter import GeometryHunterAgent
from aeroforge.agents.requirement_parser import RequirementParserAgent
import aeroforge.core.models as core_models
from aeroforge.tools.geometry_tools import create_car_stl
from aeroforge.tools.viz_tools import generate_markdown_report


def test_parse_vehicle_color_converts_hex_to_normalized_rgb():
    assert hasattr(viz, "parse_vehicle_color")
    assert viz.parse_vehicle_color("#1A80E6") == (
        0x1A / 255.0,
        0x80 / 255.0,
        0xE6 / 255.0,
    )


def test_render_case_passes_vehicle_paint_to_paraview(tmp_path, monkeypatch):
    case = tmp_path / "case"
    (case / "constant" / "polyMesh").mkdir(parents=True)
    (case / "1").mkdir()
    (case / "1" / "U").write_text("internalField uniform (1 0 0);\n")
    captured: dict[str, list[str]] = {}

    def fake_run(command, **_kwargs):
        captured["command"] = command
        results = case / "results"
        results.mkdir()
        for view in ("front", "wake", "side"):
            (results / f"streamline_hd_{view}.png").write_bytes(b"x" * 20_001)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(viz, "find_pvpython", lambda: Path("pvpython"))
    monkeypatch.setattr(viz.subprocess, "run", fake_run)
    result = viz.render_case(case, u_free=30.0, vehicle_color="#1A80E6")

    assert result["status"] == "completed"
    assert captured["command"][-1] == "0.101961,0.501961,0.901961"


def test_named_production_vehicle_never_falls_back_to_simplified_car(tmp_path):
    parsed = asyncio.run(RequirementParserAgent().run("宝马 X3 外流场 30 m/s"))
    with pytest.raises(ValueError, match="授权.*STL"):
        asyncio.run(GeometryHunterAgent().run(parsed, workspace=tmp_path))


def test_model_asset_manifest_requires_traceable_license_and_sha256():
    assert hasattr(core_models, "ModelAssetManifest")
    with pytest.raises(ValueError):
        core_models.ModelAssetManifest(
            model_id="bmw-m4-example",
            manufacturer="BMW",
            model="M4",
            source_url="https://example.invalid/model.glb",
            source_sha256="0" * 64,
            license_id="unknown",
        )


def test_named_vehicle_upload_requires_asset_manifest(tmp_path):
    source = tmp_path / "bmw_x3.stl"
    create_car_stl(source)
    parsed = asyncio.run(RequirementParserAgent().run(
        "宝马 X3 外流场 30 m/s", upload_stl_path=source))

    with pytest.raises(ValueError, match="资产清单"):
        asyncio.run(GeometryHunterAgent().run(parsed, workspace=tmp_path))


def test_named_vehicle_manifest_hash_must_match_uploaded_asset(tmp_path):
    source = tmp_path / "bmw_x3.stl"
    create_car_stl(source)
    manifest = tmp_path / "model.json"
    manifest.write_text(json.dumps({
        "model_id": "bmw-x3-private",
        "manufacturer": "BMW",
        "model": "X3",
        "source_url": "private://user-supplied",
        "source_sha256": "0" * 64,
        "license_id": "private-authorized-use",
    }), encoding="utf-8")
    parsed = asyncio.run(RequirementParserAgent().run(
        "宝马 X3 外流场 30 m/s", upload_stl_path=source))

    with pytest.raises(ValueError, match="SHA-256"):
        asyncio.run(GeometryHunterAgent().run(
            parsed, workspace=tmp_path, model_manifest_path=manifest))


def test_named_vehicle_with_matching_manifest_is_imported_and_traced(tmp_path):
    source = tmp_path / "bmw_x3.stl"
    create_car_stl(source)
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    manifest = tmp_path / "model.json"
    manifest.write_text(json.dumps({
        "model_id": "bmw-x3-private",
        "manufacturer": "BMW",
        "model": "X3",
        "source_url": "private://user-supplied",
        "source_sha256": digest,
        "license_id": "private-authorized-use",
        "derivatives_allowed": True,
        "cfd_ready": True,
    }), encoding="utf-8")
    parsed = asyncio.run(RequirementParserAgent().run(
        "宝马 X3 外流场 30 m/s", upload_stl_path=source))

    output = asyncio.run(GeometryHunterAgent().run(
        parsed, workspace=tmp_path, model_manifest_path=manifest))
    geometry = output["geometry"]

    assert geometry.stl_path.exists()
    assert geometry.manifest_path is not None
    assert geometry.manifest_path.read_text(encoding="utf-8") == manifest.read_text(
        encoding="utf-8")
    assert geometry.source == "BMW X3 (private-authorized-use)"


@pytest.mark.parametrize("manufacturer,model", [("BMW", "M4"), ("Audi", "X3")])
def test_named_vehicle_request_must_match_manifest_identity(tmp_path, manufacturer, model):
    source = tmp_path / "car.stl"
    create_car_stl(source)
    manifest = tmp_path / "model.json"
    manifest.write_text(json.dumps({
        "model_id": "private-model", "manufacturer": manufacturer, "model": model,
        "source_url": "private://user-supplied",
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "license_id": "private-authorized-use", "derivatives_allowed": True,
    }), encoding="utf-8")
    parsed = asyncio.run(RequirementParserAgent().run(
        "宝马 X3 外流场 30 m/s", upload_stl_path=source))

    with pytest.raises(ValueError, match="车型.*不一致"):
        asyncio.run(GeometryHunterAgent().run(
            parsed, workspace=tmp_path, model_manifest_path=manifest))


def test_manifest_units_drive_scale_and_unsupported_axes_fail_closed(tmp_path):
    source = tmp_path / "bmw_x3.stl"
    create_car_stl(source)
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    manifest_data = {
        "model_id": "bmw-x3-private",
        "manufacturer": "BMW",
        "model": "X3",
        "source_url": "private://user-supplied",
        "source_sha256": digest,
        "license_id": "private-authorized-use",
        "units": "mm",
        "forward_axis": "-X",
        "up_axis": "+Z",
        "derivatives_allowed": True,
    }
    manifest = tmp_path / "model.json"
    manifest.write_text(json.dumps(manifest_data), encoding="utf-8")
    parsed = asyncio.run(RequirementParserAgent().run(
        "宝马 X3 外流场 30 m/s", upload_stl_path=source))

    output = asyncio.run(GeometryHunterAgent().run(
        parsed, workspace=tmp_path / "scaled", model_manifest_path=manifest))
    assert output["geometry"].bbox.x_max < 0.01

    manifest_data["up_axis"] = "+Y"
    manifest.write_text(json.dumps(manifest_data), encoding="utf-8")
    with pytest.raises(ValueError, match="轴向"):
        asyncio.run(GeometryHunterAgent().run(
            parsed, workspace=tmp_path / "bad-axis", model_manifest_path=manifest))


def test_cli_forwards_model_manifest_paint_and_animation(monkeypatch, tmp_path):
    import aeroforge.cli as cli

    report = SimpleNamespace(
        markdown_report_path=tmp_path / "report.md",
        simulation=SimpleNamespace(converged=False, force_coeffs=None, notes=["dry-run"]),
        visualization_paths=[], visualization_note="dry-run",
    )
    captured = {}

    class FakeAgent:
        async def run(self, *_args, **kwargs):
            captured.update(kwargs)
            return {"status": "dry-run", "report": report}

    monkeypatch.setattr(cli, "OrchestratorAgent", lambda _workspace: FakeAgent())
    monkeypatch.setattr(sys, "argv", [
        "aeroforge", "宝马 X3 30 m/s", "--upload-stl", "body.stl",
        "--model-manifest", "model.json", "--vehicle-color", "#1A80E6",
        "--animation", "--animation-mode", "steady_particles",
        "--animation-frames", "36", "--animation-fps", "12",
    ])

    assert cli.main() == 0
    assert captured["model_manifest_path"] == "model.json"
    assert captured["vehicle_color"] == "#1A80E6"
    assert captured["animate"] is True
    assert captured["animation_mode"] == "steady_particles"
    assert captured["animation_frames"] == 36
    assert captured["animation_fps"] == 12


def test_bmw_demo_requires_and_forwards_asset_manifest():
    source = (Path(__file__).parents[1] / "examples" / "demo_bmw_x3.py").read_text(
        encoding="utf-8")
    assert "<manifest.json>" in source
    assert '"model_manifest_path": MANIFEST' in source


def test_render_animation_skips_without_real_result_field(tmp_path):
    assert hasattr(viz, "render_animation")
    case = tmp_path / "case"
    (case / "constant" / "polyMesh").mkdir(parents=True)
    result = viz.render_animation(case)
    assert result["status"] == "skipped"
    assert result["animation_paths"] == []
    assert "非零时刻 U" in result["note"]


@pytest.mark.parametrize("mode,expected_mode", [
    ("steady_orbit", "steady_orbit"), ("auto", "steady_particles")])
def test_render_animation_builds_fresh_gif_from_paraview_frames(
        tmp_path, monkeypatch, mode, expected_mode):
    case = tmp_path / "case"
    (case / "constant" / "polyMesh").mkdir(parents=True)
    (case / "1").mkdir()
    (case / "1" / "U").write_text("internalField uniform (30 0 0);\n")
    (case / "system").mkdir()
    (case / "system" / "controlDict").write_text("application simpleFoam;\n")
    captured = {}

    def fake_run(command, **_kwargs):
        captured["command"] = command
        frame_dir = case / "results" / "animation" / expected_mode / "frames"
        frame_dir.mkdir(parents=True, exist_ok=True)
        for index in range(4):
            Image.new("RGB", (320, 180), (10 + index, 20, 30)).save(
                frame_dir / f"frame_{index:04d}.png")
        (frame_dir / "animation_metadata.json").write_text(json.dumps({
            "source_field_time": 1.0,
            "source_field_times": [1.0] * 4,
            "particle_transport_times_s": [0.0, 0.1, 0.2, 0.3],
            "particle_cycle_duration_s": 0.4,
            "camera_motion": False,
        }), encoding="utf-8")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(viz, "find_pvpython", lambda: Path("pvpython"))
    monkeypatch.setattr(viz.subprocess, "run", fake_run)
    result = viz.render_animation(
        case, u_free=30.0, vehicle_color="#1A80E6", frames=4, fps=2, mode=mode)

    assert result["status"] == "completed"
    assert result["mode"] == expected_mode
    assert result["animation_paths"][0].suffix == ".gif"
    assert result["animation_paths"][0].stat().st_size > 100
    manifest = json.loads(result["manifest_path"].read_text(encoding="utf-8"))
    assert manifest["field"] == "U"
    assert manifest["mode"] == expected_mode
    assert manifest["source_solver"] == "simpleFoam"
    assert manifest["source_regime"] == "steady"
    assert manifest["vehicle_color"] == "#1A80E6"
    assert manifest["frame_count"] == 4
    if expected_mode == "steady_particles":
        assert manifest["particle_advection"]["transport_seconds_per_video_second"] == pytest.approx(0.2)
        assert len(manifest["animations"][0]["frame_durations_ms"]) == 4
    assert captured["command"][-3:] == ["4", expected_mode, str(case / "results" / "animation" / expected_mode / "frames")]


def test_short_transient_case_never_falls_back_to_steady_animation(tmp_path):
    case = tmp_path / "case"
    (case / "constant" / "polyMesh").mkdir(parents=True)
    (case / "0.1").mkdir()
    (case / "0.1" / "U").write_text("internalField uniform (30 0 0);\n")
    (case / "system").mkdir()
    (case / "system" / "controlDict").write_text("application pimpleFoam;\n")

    result = viz.render_animation(case, frames=36)

    assert result["status"] == "skipped"
    assert result["animation_paths"] == []
    assert "物理时间步" in result["note"]
    assert result["source_regime"] == "transient"


@pytest.mark.parametrize("renderer", [viz.render_case, viz.render_animation])
def test_render_rejects_visual_geometry_different_from_cfd_surface(tmp_path, renderer):
    case = tmp_path / "case"
    (case / "constant" / "polyMesh").mkdir(parents=True)
    (case / "constant" / "triSurface").mkdir()
    (case / "constant" / "triSurface" / "body.stl").write_bytes(b"CFD mesh")
    (tmp_path / "geometry").mkdir()
    (tmp_path / "geometry" / "model.stl").write_bytes(b"Different brand model")
    (case / "1").mkdir()
    (case / "1" / "U").write_text("internalField uniform (30 0 0);\n")

    result = renderer(case)

    assert result["status"] == "failed"
    assert "几何不一致" in result["note"]


def test_result_field_recognizes_positive_scientific_notation_times(tmp_path):
    (tmp_path / "constant" / "polyMesh").mkdir(parents=True)
    (tmp_path / "1e-05").mkdir()
    (tmp_path / "1e-05" / "U").write_text("internalField uniform (1 0 0);\n")
    assert viz._has_result_field(tmp_path)


def test_unknown_solver_cannot_be_inferred_from_comment(tmp_path):
    (tmp_path / "constant" / "polyMesh").mkdir(parents=True)
    (tmp_path / "1").mkdir()
    (tmp_path / "1" / "U").write_text("internalField uniform (1 0 0);\n")
    (tmp_path / "system").mkdir()
    (tmp_path / "system" / "controlDict").write_text(
        "// application simpleFoam;\napplication customSolver;\n")
    result = viz.render_animation(tmp_path)
    assert result["status"] == "failed"
    assert "时间语义" in result["note"]


def test_transient_animation_uses_only_available_physical_times(tmp_path, monkeypatch):
    case = tmp_path / "case"
    (case / "constant" / "polyMesh").mkdir(parents=True)
    for time_name in ("0.1", "0.2", "0.3"):
        (case / time_name).mkdir()
        (case / time_name / "U").write_text(
            "internalField uniform (30 0 0);\n", encoding="utf-8")
    (case / "system").mkdir()
    (case / "system" / "controlDict").write_text(
        "application pimpleFoam;\n", encoding="utf-8")
    captured = {}

    def fake_run(command, **_kwargs):
        captured["command"] = command
        frame_count = int(command[-3])
        frame_dir = Path(command[-1])
        frame_dir.mkdir(parents=True, exist_ok=True)
        for index in range(frame_count):
            Image.new("RGB", (320, 180), (10 + index, 20, 30)).save(
                frame_dir / f"frame_{index:04d}.png")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(viz, "find_pvpython", lambda: Path("pvpython"))
    monkeypatch.setattr(viz.subprocess, "run", fake_run)
    result = viz.render_animation(case, u_free=30, frames=36, fps=12)

    assert result["status"] == "completed"
    assert result["mode"] == "transient"
    assert captured["command"][-3] == "3"
    manifest = json.loads(result["manifest_path"].read_text(encoding="utf-8"))
    assert manifest["requested_frame_count"] == 36
    assert manifest["frame_count"] == 3


def test_animation_template_uses_real_openfoam_velocity_and_honest_labels():
    template = Path(viz.__file__).parent / "pv_templates" / "streamline_animation.py"
    assert template.exists()
    text = template.read_text(encoding="utf-8")
    assert "len(sys.argv) != 7" in text
    assert "CellDatatoPointData" in text
    assert '("Vectors", "vectors"), ("POINTS", "U")' in text
    assert "STEADY CFD FIELD" in text
    assert "TRANSIENT CFD" in text
    assert 'setp(view, ("CameraPosition",), list(position))' in text
    assert "synthetic" not in text.lower()


def test_result_analyst_forwards_paint_and_animation_controls(tmp_path, monkeypatch):
    import aeroforge.agents.result_analyst as analyst_module

    calls = {}
    static_image = tmp_path / "front.png"
    animation = tmp_path / "steady_orbit.gif"
    interactive = tmp_path / "steady_particles.html"

    def fake_render_case(case, **kwargs):
        calls["static"] = (case, kwargs)
        return {"status": "completed", "images": [static_image], "note": ""}

    def fake_render_animation(case, **kwargs):
        calls["animation"] = (case, kwargs)
        return {
            "status": "completed", "animation_paths": [animation],
            "mode": "steady_orbit", "note": "steady orbit",
        }

    def fake_render_interactive(case, **kwargs):
        calls["interactive"] = (case, kwargs)
        return {
            "status": "completed", "interactive_paths": [interactive],
            "note": "interactive orbit",
        }

    monkeypatch.setattr(analyst_module, "render_case", fake_render_case)
    monkeypatch.setattr(analyst_module, "render_animation", fake_render_animation)
    monkeypatch.setattr(analyst_module, "render_interactive", fake_render_interactive)
    monkeypatch.setattr(analyst_module, "generate_markdown_report", lambda report, **_kw: report.markdown_report_path)
    task = core_models.SimulationTask(user_prompt="car 30 m/s", velocity=30.0)
    bbox = core_models.BoundingBox(
        x_min=0, x_max=4, y_min=-1, y_max=1, z_min=0, z_max=1.5)
    geometry = {"geometry": core_models.GeometryInfo(
        stl_path=tmp_path / "task" / "geometry" / "model.stl",
        bbox=bbox, characteristic_length=4.7, source="test")}
    mesh = {"mesh": core_models.MeshReport(
        mesh_path=tmp_path / "case", passed_checkmesh=True)}
    simulation = {"simulation": core_models.SimReport(
        case_dir=tmp_path / "case", converged=True)}

    output = asyncio.run(analyst_module.ResultAnalystAgent().run(
        simulation, {"task": task}, geometry, mesh,
        vehicle_color="#1A80E6", animate=True,
        animation_frames=24, animation_fps=12))

    assert calls["static"][1]["vehicle_color"] == "#1A80E6"
    assert calls["animation"][1]["frames"] == 24
    assert output["report"].animation_paths == [animation]
    assert calls["interactive"][1]["frames"] == 24
    assert output["report"].interactive_paths == [interactive]


def test_markdown_uses_paths_relative_to_report_location(tmp_path):
    result_dir = tmp_path / "case" / "results"
    animation_dir = result_dir / "animation"
    animation_dir.mkdir(parents=True)
    static_image = result_dir / "streamline_hd_front.png"
    gif = animation_dir / "steady_orbit.gif"
    static_image.write_bytes(b"png")
    gif.write_bytes(b"gif")
    report_path = tmp_path / "results" / "report.md"
    task = core_models.SimulationTask(user_prompt="car", velocity=30)
    bbox = core_models.BoundingBox(
        x_min=0, x_max=4, y_min=-1, y_max=1, z_min=0, z_max=1.5)
    report = core_models.FinalReport(
        task=task,
        geometry=core_models.GeometryInfo(
            stl_path=tmp_path / "model.stl", bbox=bbox,
            characteristic_length=4.7, source="test"),
        mesh=core_models.MeshReport(mesh_path=tmp_path / "case"),
        simulation=core_models.SimReport(
            case_dir=tmp_path / "case", converged=True),
        visualization_paths=[static_image], animation_paths=[gif],
        markdown_report_path=report_path,
    )

    generate_markdown_report(report)
    markdown = report_path.read_text(encoding="utf-8")
    assert "../case/results/streamline_hd_front.png" in markdown
    assert "../case/results/animation/steady_orbit.gif" in markdown


def test_encode_mp4_creates_decodable_video_when_opencv_is_available(tmp_path):
    cv2 = pytest.importorskip("cv2")
    assert hasattr(viz, "_encode_mp4")
    frames = []
    for index in range(3):
        frame = tmp_path / f"frame_{index:04d}.png"
        Image.new("RGB", (160, 90), (20 * index, 40, 80)).save(frame)
        frames.append(frame)
    output = tmp_path / "animation.mp4"

    assert viz._encode_mp4(frames, output, fps=3) == output
    capture = cv2.VideoCapture(str(output))
    assert capture.isOpened()
    assert int(capture.get(cv2.CAP_PROP_FRAME_COUNT)) == 3
    assert int(capture.get(cv2.CAP_PROP_FRAME_WIDTH)) == 160
    assert int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT)) == 90
    capture.release()


def test_encode_mp4_supports_unicode_workspace_paths(tmp_path):
    pytest.importorskip("cv2")
    folder = tmp_path / "车辆风场"
    folder.mkdir()
    frames = []
    for index in range(2):
        frame = folder / f"帧_{index:04d}.png"
        Image.new("RGB", (160, 90), (30 * index, 60, 90)).save(frame)
        frames.append(frame)
    output = folder / "环绕动画.mp4"

    assert viz._encode_mp4(frames, output, fps=2) == output
    assert output.stat().st_size > 100
