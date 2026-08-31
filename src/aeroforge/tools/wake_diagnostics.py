"""Auditable lateral-bias diagnostics for exported steady CFD streamlines.

The viewer must not "straighten" a wake by translating or mirroring samples.
This module measures the field that ParaView exported, reports the likely source
of a one-sided wake, and leaves the input dataset untouched.  The thresholds
are deliberately explicit so a paper or review can distinguish an inlet
cross-flow from a downstream wake-centre offset.
"""
from __future__ import annotations

import math
from statistics import median
from typing import Any

__all__ = ["wake_bias_metrics"]


_DEFAULT_SEED_MEAN_RATIO = 0.02
_DEFAULT_SEED_RMS_RATIO = 0.02
_DEFAULT_DOWNSTREAM_OFFSET_RATIO = 0.15


def _finite_vector(sample: dict[str, Any], key: str) -> list[float]:
    value = sample.get(key)
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise ValueError(f"streamline sample {key} must be a 3-D vector")
    result = [float(component) for component in value]
    if any(not math.isfinite(component) for component in result):
        raise ValueError(f"streamline sample {key} contains non-finite values")
    return result


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else float("nan")


def wake_bias_metrics(dataset: dict[str, Any], *, u_free: float | None = None,
                      downstream_x: float | None = None,
                      seed_mean_ratio_threshold: float = _DEFAULT_SEED_MEAN_RATIO,
                      seed_rms_ratio_threshold: float = _DEFAULT_SEED_RMS_RATIO,
                      downstream_offset_ratio_threshold: float = _DEFAULT_DOWNSTREAM_OFFSET_RATIO) -> dict[str, Any]:
    """Measure inlet cross-flow and wake-centre offset from a streamline export.

    ``downstream_x`` defaults to 0.75 body lengths behind the body.  Every
    exported sample past that plane contributes to the centre estimate, while
    a separate endpoint estimate guards against a long, uneven streamline
    dominating the result.  A ``lateral_bias_detected`` status means that the
    displayed wake is materially off-centre in the sampled field; it is not a
    claim that the solver is converged or that the mesh is physically valid.
    ``inlet_crossflow_detected`` is kept separate because a symmetric ±Uy
    profile can have cross-flow RMS without causing a one-sided wake.
    """
    if not isinstance(dataset, dict):
        raise ValueError("dataset must be a mapping")
    body = dataset.get("body") or {}
    vertices = body.get("vertices") or []
    if len(vertices) < 3:
        raise ValueError("wake diagnostics need body vertices")
    coords: list[list[float]] = []
    for vertex in vertices:
        if not isinstance(vertex, (list, tuple)) or len(vertex) != 3:
            raise ValueError("body vertices must be finite 3-D points")
        point = [float(component) for component in vertex]
        if any(not math.isfinite(component) for component in point):
            raise ValueError("body vertices must be finite 3-D points")
        coords.append(point)
    xs = [point[0] for point in coords]
    ys = [point[1] for point in coords]
    z_values = [point[2] for point in coords]
    xmin, xmax = min(xs), max(xs)
    ymin, ymax = min(ys), max(ys)
    zmin, zmax = min(z_values), max(z_values)
    length = max(xmax - xmin, 1.0e-12)
    width = max(ymax - ymin, 1.0e-12)
    body_center_y = 0.5 * (ymin + ymax)

    paths = dataset.get("streamlines") or []
    if not isinstance(paths, list) or not paths:
        raise ValueError("wake diagnostics need streamline paths")
    nonempty_paths: list[list[dict[str, Any]]] = []
    all_speeds: list[float] = []
    for path in paths:
        if not isinstance(path, list) or not path:
            continue
        checked: list[dict[str, Any]] = []
        for sample in path:
            if not isinstance(sample, dict):
                raise ValueError("streamline samples must be mappings")
            position = _finite_vector(sample, "position")
            velocity = _finite_vector(sample, "velocity")
            speed = math.sqrt(sum(component * component for component in velocity))
            checked.append({"position": position, "velocity": velocity, "speed": speed})
            all_speeds.append(speed)
        if checked:
            nonempty_paths.append(checked)
    if not nonempty_paths:
        raise ValueError("wake diagnostics need non-empty streamline paths")

    reference = dataset.get("u_free_mps") if u_free is None else u_free
    if reference is None:
        reference = max(all_speeds) if all_speeds else 0.0
        reference_source = "sampled_speed_max"
    else:
        reference = float(reference)
        reference_source = "u_free_mps"
    if not math.isfinite(float(reference)) or float(reference) <= 0.0:
        raise ValueError("wake diagnostic reference speed must be finite and positive")
    reference = float(reference)

    seed_samples = [min(path, key=lambda item: item["position"][0])
                    for path in nonempty_paths]
    seed_uy = [sample["velocity"][1] for sample in seed_samples]
    seed_mean = _mean(seed_uy)
    seed_rms = math.sqrt(_mean([value * value for value in seed_uy]))
    seed_mean_ratio = abs(seed_mean) / reference
    seed_rms_ratio = seed_rms / reference

    if downstream_x is None:
        downstream_x_value = xmax + 0.75 * length
        downstream_source = "body_xmax_plus_0.75L"
    else:
        downstream_x_value = float(downstream_x)
        if not math.isfinite(downstream_x_value):
            raise ValueError("downstream_x must be finite")
        downstream_source = "explicit"
    downstream_samples = [
        sample for path in nonempty_paths for sample in path
        if sample["position"][0] >= downstream_x_value
    ]
    downstream_endpoints = [path[-1] for path in nonempty_paths
                            if path[-1]["position"][0] >= downstream_x_value]
    if downstream_samples:
        downstream_y = [sample["position"][1] for sample in downstream_samples]
        centre_y_mean = _mean(downstream_y)
        centre_y_median = float(median(downstream_y))
        centre_offset = centre_y_mean - body_center_y
        centre_offset_ratio = abs(centre_offset) / width
    else:
        centre_y_mean = float("nan")
        centre_y_median = float("nan")
        centre_offset = float("nan")
        centre_offset_ratio = float("nan")
    if downstream_endpoints:
        endpoint_y = [sample["position"][1] for sample in downstream_endpoints]
        endpoint_offset_ratio = abs(_mean(endpoint_y) - body_center_y) / width
        endpoint_y_mean = _mean(endpoint_y)
        endpoint_y_median = float(median(endpoint_y))
    else:
        endpoint_offset_ratio = float("nan")
        endpoint_y_mean = float("nan")
        endpoint_y_median = float("nan")

    thresholds = {
        "seed_mean_crossflow_ratio": float(seed_mean_ratio_threshold),
        "seed_rms_crossflow_ratio": float(seed_rms_ratio_threshold),
        "downstream_offset_ratio": float(downstream_offset_ratio_threshold),
    }
    if any(not math.isfinite(value) or value < 0.0 for value in thresholds.values()):
        raise ValueError("wake diagnostic thresholds must be finite and non-negative")
    if not downstream_samples:
        status = "insufficient_downstream_samples"
        interpretation = "下游筛选面没有有效流线样本，不能判断尾流是否偏侧。"
    elif (seed_mean_ratio > thresholds["seed_mean_crossflow_ratio"]
          or centre_offset_ratio > thresholds["downstream_offset_ratio"]
          or (math.isfinite(endpoint_offset_ratio)
              and endpoint_offset_ratio > thresholds["downstream_offset_ratio"])):
        status = "lateral_bias_detected"
        interpretation = (
            "检测到入口横向速度均值或下游尾流中心偏移；应优先检查入口边界、网格、"
            "地面/车体对称性及稳态收敛，不能在可视化层人为对称化。"
        )
    elif seed_rms_ratio > thresholds["seed_rms_crossflow_ratio"]:
        status = "inlet_crossflow_detected"
        interpretation = (
            "入口存在横向速度波动，但下游中心仍基本居中；这不等同于单侧尾流，"
            "应结合入口剖面和湍流设置审查。"
        )
    else:
        status = "balanced"
        interpretation = "采样入口与下游尾流中心均在阈值内，未检测到显著单侧偏移。"

    def _finite_or_none(value: float) -> float | None:
        return float(value) if math.isfinite(value) else None

    return {
        "diagnostic_version": 1,
        "status": status,
        "bias_detected": status == "lateral_bias_detected",
        "source_field_time": dataset.get("source_field_time"),
        "reference_speed_mps": reference,
        "reference_speed_source": reference_source,
        "body_bounds": {
            "x": [float(xmin), float(xmax)],
            "y": [float(ymin), float(ymax)],
            "z": [float(zmin), float(zmax)],
        },
        "body_center_y_m": float(body_center_y),
        "body_width_m": float(width),
        "downstream_x_m": float(downstream_x_value),
        "downstream_plane_source": downstream_source,
        "sample_count_seed": len(seed_samples),
        "sample_count_downstream": len(downstream_samples),
        "sample_count_downstream_endpoints": len(downstream_endpoints),
        "seed_crossflow_mean_mps": float(seed_mean),
        "seed_crossflow_rms_mps": float(seed_rms),
        "seed_crossflow_mean_ratio": float(seed_mean_ratio),
        "seed_crossflow_rms_ratio": float(seed_rms_ratio),
        "downstream_center_y_mean_m": _finite_or_none(centre_y_mean),
        "downstream_center_y_median_m": _finite_or_none(centre_y_median),
        "downstream_center_offset_m": _finite_or_none(centre_offset),
        "downstream_center_offset_ratio": _finite_or_none(centre_offset_ratio),
        "downstream_endpoint_y_mean_m": _finite_or_none(endpoint_y_mean),
        "downstream_endpoint_y_median_m": _finite_or_none(endpoint_y_median),
        "downstream_endpoint_offset_ratio": _finite_or_none(endpoint_offset_ratio),
        "thresholds": thresholds,
        "interpretation": interpretation,
        "data_unchanged": True,
    }
