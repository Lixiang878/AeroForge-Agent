from pathlib import Path
import ast
import builtins
import math
import pytest


ROOT = Path(__file__).resolve().parents[1]
ANIMATION = ROOT / "src" / "aeroforge" / "tools" / "pv_templates" / "streamline_animation.py"
HD = ROOT / "src" / "aeroforge" / "tools" / "pv_templates" / "streamline_hd.py"


def test_hd_uses_one_incoming_yz_plane_and_small_fixed_direction_arrows():
    text = HD.read_text(encoding="utf-8")

    assert "StreamTracerWithCustomSource" in text
    assert "incoming_yz_seed" in text
    assert "Glyph" in text and "Arrow" in text
    assert "No scale array" in text
    assert "OrientationArray" in text and '"POINTS", "U"' in text
    assert "SeedType=\"Line\"" not in text
    assert "arrow_neutral_colour" in text
    assert "fixed length" in text
    assert "servermanager.Fetch" in text
    assert "static_velocity_color_max" in text
    assert "UMAX = 1.08 * UFREE" not in text
    assert "velocity_colour_scale_mode" in text
    assert "UseLogScale" in text
    assert "#2166ac" in text and "#d73027" in text


def test_paraview_templates_use_explicit_blue_to_red_speed_scale():
    for template in (ANIMATION, HD):
        text = template.read_text(encoding="utf-8")
        assert "#2166ac" in text
        assert "#d73027" in text
        assert "Viridis" not in text
        assert "Cividis" not in text


def test_both_templates_describe_finite_near_body_plane_not_full_domain_inlet():
    for template in (ANIMATION, HD):
        text = template.read_text(encoding="utf-8")
        assert "full-domain" in text
        assert "domain_bounds" in text


def _hd_pure_helpers():
    tree = ast.parse(HD.read_text(encoding="utf-8"))
    nodes = [node for node in tree.body
             if isinstance(node, ast.FunctionDef)
             and node.name in {"static_velocity_color_max", "velocity_colour_scale_mode"}]
    namespace = {"builtins": builtins, "math": math}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(HD), "exec"), namespace)
    return namespace


def test_static_color_scale_uses_observed_velocity_range_not_inlet_hint():
    namespace = _hd_pure_helpers()
    helper = namespace["static_velocity_color_max"]
    assert helper(39.1192214) == pytest.approx(42.2487591)
    assert helper(158.5) == pytest.approx(171.18)
    assert helper(0.05) == pytest.approx(0.054)
    with pytest.raises(ValueError):
        helper(math.nan)


def test_static_color_scale_switches_to_log_for_wide_positive_range():
    helper = _hd_pure_helpers()["velocity_colour_scale_mode"]
    assert helper(1.0, 100.0) == "log10"
    assert helper(20.0, 100.0) == "linear"
