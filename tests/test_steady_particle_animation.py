from pathlib import Path
import ast
import bisect
import builtins
import math

import pytest


TEMPLATE = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "aeroforge"
    / "tools"
    / "pv_templates"
    / "streamline_animation.py"
)


def test_steady_particles_mode_is_explicitly_supported():
    text = TEMPLATE.read_text(encoding="utf-8")

    assert '"steady_particles"' in text
    assert "STEADY CFD | TRACER ADVECTION" in text


def test_steady_particles_uses_fetched_streamline_integration_data():
    text = TEMPLATE.read_text(encoding="utf-8")

    assert "servermanager.Fetch" in text
    assert "IntegrationTime" in text
    assert "vtkPoints" in text


def test_animation_uses_one_incoming_yz_seed_plane_and_direction_glyphs():
    text = TEMPLATE.read_text(encoding="utf-8")

    assert "StreamTracerWithCustomSource" in text
    assert "incoming_yz_seed" in text
    assert "XResolution" in text and "YResolution" in text
    assert "Glyph" in text and "Arrow" in text
    assert "No scale array" in text
    assert "OrientationArray" in text and '"POINTS", "U"' in text
    assert '"GlyphMode", "glyph_mode"), "All Points"' in text
    assert "stable_particle_arrow" in text
    assert "RenderPointsAsSpheres" not in text
    assert 'SeedType="Line"' not in text
    assert "arrow_neutral_colour" in text
    assert "fixed length" in text
    assert "UseLogScale" in text
    assert "#2166ac" in text and "#d73027" in text
    assert "f6f9fc" in text


def _pure_helpers():
    tree = ast.parse(TEMPLATE.read_text(encoding="utf-8"))
    wanted = {
        "incoming_yz_seed",
        "velocity_magnitude",
        "streamline_cell_is_usable",
        "validate_integration_times",
        "validate_streamline_sample",
        "interpolate_sample",
        "steady_particle_release_interval",
        "steady_particle_transport_window",
        "stable_particle_arrow",
        "dynamic_velocity_colour_max",
        "velocity_colour_scale_mode",
    }
    nodes = [node for node in tree.body
             if isinstance(node, ast.FunctionDef) and node.name in wanted]
    namespace = {"bisect": bisect, "builtins": builtins, "math": math}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(TEMPLATE), "exec"), namespace)
    return namespace


def test_interpolation_uses_one_global_clock_and_preserves_velocity_ratio():
    helpers = _pure_helpers()
    interpolate = helpers["interpolate_sample"]
    path_u1 = [(0.0, (0.0, 0.0, 0.0), (1.0, 0.0, 0.0)),
               (1.0, (1.0, 0.0, 0.0), (1.0, 0.0, 0.0))]
    path_u2 = [(0.0, (0.0, 0.0, 0.0), (2.0, 0.0, 0.0)),
               (0.5, (1.0, 0.0, 0.0), (2.0, 0.0, 0.0))]

    x1, _ = interpolate(path_u1, 0.5)
    x2, _ = interpolate(path_u2, 0.5)
    assert x1[0] == pytest.approx(0.5)
    assert x2[0] == pytest.approx(1.0)
    assert x2[0] / x1[0] == pytest.approx(2.0)


def test_incoming_seed_plane_is_finite_near_body_and_not_full_inlet():
    seed = _pure_helpers()["incoming_yz_seed"](
        (-15.0, 37.0, -6.0, 6.0, 0.0, 9.0),
        (-0.8, 4.0, -1.0, 1.0, 0.005, 1.52),
    )
    assert seed["x_resolution"] == 15
    assert seed["y_resolution"] == 11
    assert -15.0 < seed["x"] < 37.0
    assert -6.0 < seed["y_min"] < seed["y_max"] < 6.0
    assert 0.0 < seed["z_min"] < seed["z_max"] < 9.0
    assert seed["y_min"] > -6.0 and seed["y_max"] < 6.0


def test_velocity_magnitude_is_a_real_vector_norm_for_arrow_filtering():
    helpers = _pure_helpers()
    assert helpers["velocity_magnitude"]((3.0, 4.0, 0.0)) == pytest.approx(5.0)


def test_animation_colour_scale_switches_only_for_wide_positive_ranges():
    helper = _pure_helpers()["velocity_colour_scale_mode"]
    assert helper(1.0, 100.0) == "log10"
    assert helper(20.0, 100.0) == "linear"
    assert helper(0.0, 100.0) == "linear"


def test_animation_colour_limit_uses_observed_samples_not_free_stream_hint():
    helper = _pure_helpers()["dynamic_velocity_colour_max"]
    assert helper(39.1192214) == pytest.approx(42.2487591)
    assert helper(158.5) == pytest.approx(171.18)
    assert helper(0.05) == pytest.approx(0.054)


def test_degenerate_streamline_cell_is_rejected_without_relaxing_time_gate():
    helpers = _pure_helpers()
    assert helpers["streamline_cell_is_usable"]([0.0, 0.5, 1.0]) is True
    assert helpers["streamline_cell_is_usable"]([0.0, 0.5, 0.5]) is False


@pytest.mark.parametrize("times", [[0.0, 1.0, 0.5], [0.0, math.nan]])
def test_invalid_integration_time_samples_are_rejected(times):
    helpers = _pure_helpers()
    with pytest.raises(ValueError):
        helpers["validate_integration_times"](times)


@pytest.mark.parametrize(
    "xyz,velocity",
    [
        ((0.0, 0.0, 0.0), None),
        ((0.0, math.inf, 0.0), (1.0, 0.0, 0.0)),
        ((0.0, 0.0, 0.0), (1.0, math.nan, 0.0)),
    ],
)
def test_streamline_samples_reject_missing_or_nonfinite_velocity(xyz, velocity):
    helpers = _pure_helpers()
    with pytest.raises(ValueError):
        helpers["validate_streamline_sample"](0.0, xyz, velocity)


def test_release_interval_is_independent_of_render_frame_count():
    helpers = _pure_helpers()
    interval = helpers["steady_particle_release_interval"]
    assert interval(0.8, 8) == pytest.approx(0.8 / 64.0)
    assert interval(0.8, 80) == pytest.approx(0.8 / 64.0)


def test_steady_particle_transport_window_covers_eight_body_lengths():
    helpers = _pure_helpers()
    window = helpers["steady_particle_transport_window"]
    assert window(4.5, 30.0) == pytest.approx(8.0 * 4.5 / 30.0)
    assert window(4.5, 30.0, 4.0) == pytest.approx(4.0 * 4.5 / 30.0)


def test_release_cadence_is_dense_enough_for_smooth_playback():
    helpers = _pure_helpers()
    interval = helpers["steady_particle_release_interval"]
    # The release clock is deliberately independent of video sampling.  At
    # common 36/80-frame previews, one injection may span at most two frames;
    # the production showcase uses 120 frames and is denser still.
    assert interval(0.8, 36) < 2.0 * 0.8 / (36 - 1)
    assert interval(0.8, 80) < 2.0 * 0.8 / (80 - 1)


def test_particle_arrow_selection_is_stable_for_path_release_identity():
    helpers = _pure_helpers()
    select = helpers["stable_particle_arrow"]
    assert select(7, 11, 4) is True
    assert select(7, 12, 4) is False
    # The decision depends on the stable path/release identity, not the
    # transient order of points surviving IntegrationTime clipping.
    assert select(7, 11, 4) is True
    with pytest.raises(ValueError):
        select(0, 0, 0)
