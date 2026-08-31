from __future__ import annotations

import pytest


def _dataset():
    return {
        "body": {
            "vertices": [
                [-1.0, -0.5, 0.0], [1.0, -0.5, 0.0],
                [1.0, 0.5, 0.0], [-1.0, 0.5, 0.0],
                [-1.0, -0.5, 0.6], [1.0, -0.5, 0.6],
                [1.0, 0.5, 0.6], [-1.0, 0.5, 0.6],
            ],
            "faces": [
                [0, 1, 2], [0, 2, 3], [4, 6, 5], [4, 7, 6],
                [0, 4, 5], [0, 5, 1], [1, 5, 6], [1, 6, 2],
                [2, 6, 7], [2, 7, 3], [3, 7, 4], [3, 4, 0],
            ],
        },
        "streamlines": [[
            {"time": 0.0, "position": [-1.2, 0.0, 0.4], "velocity": [2.0, 0.0, 0.0]},
            {"time": 0.4, "position": [-0.2, 0.0, 0.4], "velocity": [2.2, 0.0, 0.0]},
            {"time": 0.8, "position": [3.0, 0.0, 0.4], "velocity": [1.8, 0.0, 0.0]},
        ]],
        "u_max_mps": 2.4,
        "transport_window_s": 0.8,
    }


def test_interactive_figure_has_orbit_drag_colorbar_and_animation_frames():
    pytest.importorskip("plotly")
    from aeroforge.tools.interactive_viz import build_interactive_figure

    figure = build_interactive_figure(_dataset(), frames=4, fps=10)

    assert figure.layout.scene.dragmode == "orbit"
    assert any(trace.type == "mesh3d" for trace in figure.data)
    arrows = [trace for trace in figure.data if trace.name == "U 方向箭头"]
    assert arrows and arrows[0].type == "scatter3d"
    assert arrows[0].mode == "lines"
    assert arrows[0].line.color == "#17324d"
    assert not any(trace.type == "cone" for trace in figure.data)
    assert len(arrows[0].x) <= 128 * 15
    colorbar_traces = [
        trace for trace in figure.data
        if getattr(getattr(trace, "marker", None), "showscale", False)
    ]
    assert colorbar_traces
    assert colorbar_traces[0].marker.colorbar.title.text == "|U| (m/s)"
    assert colorbar_traces[0].marker.colorbar.thickness >= 24
    assert colorbar_traces[0].marker.colorbar.outlinewidth >= 1
    assert len(figure.frames) == 4
    assert figure.layout.sliders[0].currentvalue.prefix == "输运时间: "
    assert figure.layout.paper_bgcolor == "#f6f9fc"
    assert figure.layout.scene.bgcolor == "#f6f9fc"


def test_interactive_view_uses_vehicle_focused_ratio_and_detail_cameras():
    pytest.importorskip("plotly")
    from aeroforge.tools.interactive_viz import build_interactive_figure

    figure = build_interactive_figure(_dataset(), frames=4, fps=10)

    assert figure.layout.scene.aspectmode == "manual"
    assert figure.layout.scene.aspectratio.x > figure.layout.scene.aspectratio.y
    assert figure.layout.scene.aspectratio.y > figure.layout.scene.aspectratio.z
    assert figure.layout.scene.camera.center.x == pytest.approx(0.15)
    camera_labels = [
        button.label
        for button in figure.layout.updatemenus[1].buttons
    ]
    assert "后视镜" in camera_labels
    assert "车尾细节" in camera_labels
    detail_traces = [
        trace for trace in figure.data
        if trace.name in {"后视镜细节", "车尾分离区"}
    ]
    assert len(detail_traces) == 2
    assert all(trace.type == "scatter3d" and trace.mode == "lines"
               for trace in detail_traces)
    assert figure.layout.meta["wake_diagnostics"]["status"] == "balanced"


def test_velocity_colourscale_is_blue_to_red_for_speed():
    from aeroforge.tools.interactive_viz import _VELOCITY_COLORSCALE

    assert _VELOCITY_COLORSCALE[0][1].lower() in {"#2166ac", "#2c7bb6"}
    assert _VELOCITY_COLORSCALE[-1][1].lower() in {"#d73027", "#b2182b"}
    assert len(_VELOCITY_COLORSCALE) >= 5


def test_interactive_module_keeps_all_output_on_case_volume(tmp_path):
    from aeroforge.tools.interactive_viz import interactive_output_paths

    outputs = interactive_output_paths(tmp_path / "case")
    assert outputs["html"].is_relative_to(tmp_path / "case")
    assert outputs["data"].is_relative_to(tmp_path / "case")
    assert outputs["html"].name == "steady_particles.html"


def test_exporter_merges_stl_points_before_browser_decimation():
    from pathlib import Path

    exporter = (Path(__file__).resolve().parents[1]
                / "src/aeroforge/tools/pv_templates/export_streamline_data.py")
    assert "vtkCleanPolyData" in exporter.read_text(encoding="utf-8")
    assert "Merge coincident points" in exporter.read_text(encoding="utf-8")


def test_speed_scale_uses_physical_log_ticks_for_wide_dynamic_range():
    from aeroforge.tools.interactive_viz import speed_scale_config

    config = speed_scale_config([1.0, 2.0, 4.0, 100.0], 100.0)

    assert config["mode"] == "log10"
    assert config["vmin_mps"] == 1.0
    assert config["vmax_mps"] == 100.0
    assert config["tick_mps"] == [1.0, 2.0, 5.0, 10.0, 20.0, 50.0, 100.0]


def test_speed_scale_does_not_expand_beyond_observed_field_for_dynamic_range():
    from aeroforge.tools.interactive_viz import speed_scale_config

    config = speed_scale_config([12.83630216, 30.0, 39.1192214], 171.18432)

    assert config["mode"] == "linear"
    assert config["vmax_mps"] == pytest.approx(42.2487591)
    assert config["vmin_mps"] == pytest.approx(12.83630216)


def test_small_physical_speeds_do_not_get_a_one_metre_per_second_floor():
    from aeroforge.tools.interactive_viz import speed_scale_config

    config = speed_scale_config([0.02, 0.03, 0.05])
    assert config["vmin_mps"] == 0.02
    assert config["vmax_mps"] == pytest.approx(0.054)


def test_interactive_manifest_contract_includes_wake_diagnostic_gate(tmp_path):
    from aeroforge.tools.interactive_viz import _wake_diagnostic_manifest

    result = _wake_diagnostic_manifest(_dataset(), downstream_x=0.5)
    assert result["status"] == "balanced"
    assert result["source_field_time"] is None


def test_interactive_streamlines_and_moving_trails_use_local_speed_colours():
    pytest.importorskip("plotly")
    from aeroforge.tools.interactive_viz import build_interactive_figure

    figure = build_interactive_figure(_dataset(), frames=4, fps=10)
    streamline = figure.data[1]
    assert list(streamline.line.color) == pytest.approx([2.0, 2.2, 1.8])
    assert streamline.line.cmin == 1.8
    assert streamline.line.cmax == pytest.approx(2.376)
    moving = figure.frames[0].data[0]
    assert not isinstance(moving.line.color, str)
    assert moving.line.cmin == streamline.line.cmin
    assert moving.line.cmax == streamline.line.cmax


def test_animation_default_fps_is_faster_but_exactly_gif_safe():
    from aeroforge.tools.windtunnel_viz import DEFAULT_ANIMATION_FPS

    assert DEFAULT_ANIMATION_FPS == 40
    assert 1000 / DEFAULT_ANIMATION_FPS == 25
