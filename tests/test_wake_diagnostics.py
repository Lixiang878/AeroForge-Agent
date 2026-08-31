from __future__ import annotations

import pytest


def _dataset(lateral_velocity: float = 0.0, lateral_shift: float = 0.0):
    return {
        "u_free_mps": 30.0,
        "source_field_time": 780.0,
        "body": {
            "vertices": [
                [-1.0, -1.0, 0.0], [3.0, -1.0, 0.0],
                [3.0, 1.0, 0.0], [-1.0, 1.0, 0.0],
                [-1.0, -1.0, 1.0], [3.0, -1.0, 1.0],
                [3.0, 1.0, 1.0], [-1.0, 1.0, 1.0],
            ],
            "faces": [
                [0, 1, 2], [0, 2, 3], [4, 6, 5], [4, 7, 6],
                [0, 4, 5], [0, 5, 1], [1, 5, 6], [1, 6, 2],
                [2, 6, 7], [2, 7, 3], [3, 7, 4], [3, 4, 0],
            ],
        },
        "streamlines": [
            [
                {"time": 0.0, "position": [-2.0, -0.8, 0.4],
                 "velocity": [30.0, lateral_velocity, 0.0]},
                {"time": 0.5, "position": [0.0, -0.8 + lateral_shift, 0.4],
                 "velocity": [27.0, lateral_velocity, 0.0]},
                {"time": 1.0, "position": [6.0, -0.8 + lateral_shift, 0.4],
                 "velocity": [24.0, lateral_velocity, 0.0]},
            ],
            [
                {"time": 0.0, "position": [-2.0, 0.8, 0.6],
                 "velocity": [30.0, -lateral_velocity, 0.0]},
                {"time": 0.5, "position": [0.0, 0.8 + lateral_shift, 0.6],
                 "velocity": [27.0, -lateral_velocity, 0.0]},
                {"time": 1.0, "position": [6.0, 0.8 + lateral_shift, 0.6],
                 "velocity": [24.0, -lateral_velocity, 0.0]},
            ],
        ],
    }


def test_wake_diagnostics_identifies_balanced_field_and_reports_source_time():
    from aeroforge.tools.wake_diagnostics import wake_bias_metrics

    result = wake_bias_metrics(_dataset())

    assert result["status"] == "balanced"
    assert result["source_field_time"] == 780.0
    assert result["seed_crossflow_mean_mps"] == pytest.approx(0.0)
    assert result["downstream_center_offset_ratio"] == pytest.approx(0.0)
    assert result["sample_count_downstream"] == 2
    assert result["thresholds"]["downstream_offset_ratio"] == pytest.approx(0.15)


def test_wake_diagnostics_separates_inlet_crossflow_from_wake_offset():
    from aeroforge.tools.wake_diagnostics import wake_bias_metrics

    result = wake_bias_metrics(_dataset(lateral_velocity=0.9, lateral_shift=0.0))

    assert result["status"] == "inlet_crossflow_detected"
    assert result["seed_crossflow_mean_mps"] == pytest.approx(0.0)
    assert result["seed_crossflow_rms_ratio"] == pytest.approx(0.03)
    assert "横向速度" in result["interpretation"]


def test_wake_diagnostics_flags_one_sided_downstream_paths_without_mutating_data():
    from aeroforge.tools.wake_diagnostics import wake_bias_metrics

    dataset = _dataset(lateral_shift=-0.5)
    before = dataset["streamlines"][0][2]["position"][:]
    result = wake_bias_metrics(dataset)

    assert result["status"] == "lateral_bias_detected"
    assert result["downstream_center_offset_ratio"] == pytest.approx(0.25)
    assert dataset["streamlines"][0][2]["position"] == before


def test_wake_diagnostics_requires_body_and_downstream_samples():
    from aeroforge.tools.wake_diagnostics import wake_bias_metrics

    with pytest.raises(ValueError, match="body vertices"):
        wake_bias_metrics({"streamlines": []})

    dataset = _dataset()
    dataset["streamlines"] = [[dataset["streamlines"][0][0]]]
    result = wake_bias_metrics(dataset)
    assert result["status"] == "insufficient_downstream_samples"
    assert result["sample_count_downstream"] == 0
