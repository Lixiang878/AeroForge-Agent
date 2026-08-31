import math

import pytest

from aeroforge.tools.pv_templates.velocity_sampling import (
    preserved_sample_indices,
    validate_sampled_speed,
)


def test_interpolation_cannot_create_a_velocity_above_the_source_field():
    validate_sampled_speed(35.85, 43.9123)
    validate_sampled_speed(43.9123001, 43.9123)
    with pytest.raises(ValueError, match="source field"):
        validate_sampled_speed(158.504, 43.9123)


@pytest.mark.parametrize("sampled,source", [(math.nan, 40), (30, math.inf), (-1, 40), (30, 0)])
def test_invalid_speed_evidence_is_rejected(sampled, source):
    with pytest.raises(ValueError):
        validate_sampled_speed(sampled, source)


def test_browser_downsampling_preserves_real_speed_extrema_and_endpoints():
    speeds = [30.0] * 401
    speeds[77], speeds[293] = 43.0, 0.4
    indices = preserved_sample_indices(speeds, 140)
    assert {0, 77, 293, 400}.issubset(indices)
    assert indices == sorted(set(indices))
    assert len(indices) <= 140
    assert indices == preserved_sample_indices(speeds, 140)


def test_small_streamlines_are_not_downsampled():
    assert preserved_sample_indices([10, 20, 30], 140) == [0, 1, 2]
