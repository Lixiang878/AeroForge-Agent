"""Shared velocity-sampling safeguards for standalone pvpython templates."""
import math


SAMPLING_METHOD = (
    "post-processing Tetrahedralize + Cell Locator; solver mesh and U unchanged"
)


def prepare_velocity_sampling(point_field, time_value=None):
    """Use piecewise-linear tetrahedra for the rendering interpolation only.

    Native polyhedron interpolation can overshoot the input vector bounds on
    distorted near-wall cells.  Do not rescale or clip U to conceal that error.
    The derived cells are never written back to the OpenFOAM solver mesh.
    """
    from paraview.simple import Tetrahedralize

    sampled = Tetrahedralize(Input=point_field)
    sampled.UpdatePipeline(time_value)
    return sampled


def point_field_speed_max(field):
    array = field.GetDataInformation().GetPointDataInformation().GetArrayInformation("U")
    if array is None:
        raise ValueError("source field has no point-centred U")
    maximum = float(array.GetComponentRange(-1)[1])
    if not math.isfinite(maximum) or maximum <= 0:
        raise ValueError("source field U maximum must be finite and positive")
    return maximum


def validate_sampled_speed(sampled_max, source_max):
    """Reject interpolation overshoot; permit only float32 roundoff."""
    sampled, source = float(sampled_max), float(source_max)
    if (not math.isfinite(sampled) or not math.isfinite(source)
            or sampled < 0 or source <= 0):
        raise ValueError("sampled and source field speeds must be finite and valid")
    if sampled > source * (1.0 + 1.0e-5):
        raise ValueError(
            f"StreamTracer |U|={sampled:.6g} m/s exceeds source field "
            f"maximum={source:.6g} m/s; inspect interpolation before rendering"
        )


def preserved_sample_indices(speeds, limit):
    """Bound browser payloads without dropping a path's true speed extrema."""
    values = [float(value) for value in speeds]
    count = len(values)
    limit = int(limit)
    if limit < 4 or any(not math.isfinite(v) or v < 0 for v in values):
        raise ValueError("speed samples must be finite/non-negative and limit >= 4")
    if count <= limit:
        return list(range(count))
    regular_count = limit - 2
    indices = {round(i * (count - 1) / (regular_count - 1)) for i in range(regular_count)}
    indices.add(min(range(count), key=values.__getitem__))
    indices.add(max(range(count), key=values.__getitem__))
    return sorted(indices)
