"""Self-contained, field-grounded 3-D wind-tunnel viewer.

The ParaView exporter supplies the actual OpenFOAM ``U`` vectors and
``IntegrationTime`` samples.  This module only assembles those samples into a
Plotly HTML document, so browser orbit/zoom controls never replace the CFD
source with a synthetic field.
"""
from __future__ import annotations

import json
import math
import subprocess
from pathlib import Path

from .windtunnel_viz import (
    DEFAULT_ANIMATION_FPS,
    _geometry_evidence,
    _has_result_field,
    _sha256_file,
    find_pvpython,
    parse_vehicle_color,
    read_freestream,
)

_EXPORT_TEMPLATE = Path(__file__).parent / "pv_templates" / "export_streamline_data.py"
_RELEASE_COUNT = 64
_SPEED_LOG_RATIO = 8.0
_PAPER_BG = "#f6f9fc"
_PAPER_TEXT = "#16324a"
_PAPER_GRID = "#c7d5e0"
_VELOCITY_COLORSCALE = "Viridis"

__all__ = [
    "build_interactive_figure",
    "interactive_output_paths",
    "render_interactive",
    "speed_scale_config",
]


def interactive_output_paths(case_dir: str | Path) -> dict[str, Path]:
    """Return output paths rooted under the CFD case, never a system temp dir."""
    root = Path(case_dir).resolve() / "results" / "animation" / "interactive"
    return {
        "directory": root,
        "data": root / "streamline_data.json",
        "html": root / "steady_particles.html",
        "manifest": root / "interactive_manifest.json",
    }


def _speed(velocity) -> float:
    values = tuple(float(value) for value in velocity)
    if len(values) != 3 or any(not math.isfinite(value) for value in values):
        raise ValueError("velocity must be a finite 3-D vector")
    return math.sqrt(sum(value * value for value in values))


def _log_tick_values(vmin: float, vmax: float) -> list[float]:
    """Return readable 1/2/5 logarithmic ticks while retaining endpoints."""
    if vmin <= 0 or vmax < vmin:
        raise ValueError("logarithmic colour limits must be positive and ordered")
    candidates = []
    first = math.floor(math.log10(vmin))
    last = math.ceil(math.log10(vmax))
    for exponent in range(first, last + 1):
        scale = 10.0 ** exponent
        candidates.extend(scale * multiplier for multiplier in (1.0, 2.0, 5.0))
    candidates.extend((vmin, vmax))
    result = []
    for value in sorted(value for value in candidates if vmin <= value <= vmax):
        if not result or not math.isclose(value, result[-1], rel_tol=1e-12, abs_tol=1e-12):
            result.append(float(value))
    return result


def _linear_tick_values(vmin: float, vmax: float) -> list[float]:
    """Return five stable ticks spanning the actual non-negative data range."""
    if not math.isfinite(vmin) or not math.isfinite(vmax) or vmin < 0 or vmax <= vmin:
        raise ValueError("linear colour range must be finite and ordered")
    return [float(vmin + (vmax - vmin) * index / 4.0) for index in range(5)]


def speed_scale_config(speeds, upper: float | None = None) -> dict:
    """Describe a readable, physically labelled |U| colour mapping.

    A wide positive dynamic range is displayed on a log10 axis so the common
    low-speed region is not collapsed into the darkest colour.  The observed
    field maximum is authoritative; ``upper`` is only a compatibility hint
    and is never allowed to inflate the range beyond 8% headroom over the
    observed data.  Values remain physical speeds; only the monotone display
    transform changes.
    """
    values = [float(value) for value in speeds]
    if not values or any(not math.isfinite(value) or value < 0.0 for value in values):
        raise ValueError("speeds must contain finite non-negative values")
    positive = [value for value in values if value > 0.0]
    if not positive:
        raise ValueError("speed colour scale needs at least one positive speed")
    observed_max = max(values)
    dynamic_max = 1.08 * observed_max
    if upper is None:
        vmax = dynamic_max
    else:
        requested = float(upper)
        if not math.isfinite(requested) or requested <= 0.0:
            raise ValueError("upper colour hint must be finite and positive")
        # Preserve a caller's tighter valid limit, but never use an inflated
        # inlet/free-stream hint to stretch the colourbar beyond the data.
        vmax = max(observed_max, min(requested, dynamic_max))
    if not math.isfinite(vmax) or vmax <= 0.0:
        raise ValueError("speed colour maximum must be finite and positive")
    positive_floor = min(positive)
    data_floor = min(values)
    if vmax <= data_floor:
        vmax = dynamic_max
    mode = "log10" if data_floor > 0.0 and vmax / positive_floor >= _SPEED_LOG_RATIO else "linear"
    if mode == "log10":
        vmin = positive_floor
        tick_mps = _log_tick_values(vmin, vmax)
        cmin = math.log10(vmin)
        cmax = math.log10(vmax)
        title = "|U| (m/s), log10 scale"
        note = "|U| colour encodes speed on a log10 scale; direction arrows are fixed length"
    else:
        vmin = data_floor
        tick_mps = _linear_tick_values(vmin, vmax)
        cmin = vmin
        cmax = vmax
        title = "|U| (m/s)"
        note = "|U| colour encodes speed linearly; direction arrows are fixed length"
    return {
        "mode": mode,
        "vmin_mps": float(vmin),
        "vmax_mps": float(vmax),
        "cmin": float(cmin),
        "cmax": float(cmax),
        "tick_mps": tick_mps,
        "title": title,
        "note": note,
    }


def _speed_colour_value(speed: float, scale: dict) -> float:
    value = max(float(speed), float(scale["vmin_mps"]))
    return math.log10(value) if scale["mode"] == "log10" else value


def _stable_particle_arrow(path_index: int, release_index: int, stride: int = 4) -> bool:
    path_value = int(path_index)
    release_value = int(release_index)
    stride_value = int(stride)
    if path_value < 0 or release_value < 0 or stride_value < 1:
        raise ValueError("path, release, and stride must be non-negative/positive")
    return (3 * path_value + release_value) % stride_value == 0


def _interpolate(path: list[dict], transport_time: float) -> tuple[list[float], list[float]]:
    """Interpolate position and U on a path's actual IntegrationTime axis."""
    if not path:
        raise ValueError("empty streamline path")
    if transport_time <= path[0]["time"]:
        return list(path[0]["position"]), list(path[0]["velocity"])
    if transport_time >= path[-1]["time"]:
        return list(path[-1]["position"]), list(path[-1]["velocity"])
    for left, right in zip(path, path[1:]):
        if left["time"] <= transport_time <= right["time"]:
            span = right["time"] - left["time"]
            weight = (transport_time - left["time"]) / span if span > 0 else 0.0
            position = [
                left["position"][axis]
                + weight * (right["position"][axis] - left["position"][axis])
                for axis in range(3)
            ]
            velocity = [
                left["velocity"][axis]
                + weight * (right["velocity"][axis] - left["velocity"][axis])
                for axis in range(3)
            ]
            return position, velocity
    return list(path[-1]["position"]), list(path[-1]["velocity"])


def _append_arrow_segments(x_values: list, y_values: list, z_values: list,
                           position: list[float], vector: list[float]) -> None:
    """Append one fixed-length 3-D arrow as line segments.

    Plotly ``Cone`` glyphs are rendered as opaque surfaces and can visually
    merge into a dark sheet when many arrows overlap the STL.  A shaft plus
    arrowhead fins in two orthogonal planes has the same directional meaning while
    remaining lightweight, legible, and free of spherical marker nodes.
    """
    magnitude = math.sqrt(sum(float(component) ** 2 for component in vector))
    if not math.isfinite(magnitude) or magnitude <= 1.0e-12:
        return
    direction = [float(component) / magnitude for component in vector]
    tail = [float(value) for value in position]
    head = [tail[axis] + float(vector[axis]) for axis in range(3)]
    # Pick a reference that is not parallel to the arrow, then construct two
    # perpendicular directions for a compact 3-D arrowhead.
    reference = [0.0, 0.0, 1.0]
    if abs(sum(direction[axis] * reference[axis] for axis in range(3))) > 0.90:
        reference = [0.0, 1.0, 0.0]
    side_a = [
        direction[1] * reference[2] - direction[2] * reference[1],
        direction[2] * reference[0] - direction[0] * reference[2],
        direction[0] * reference[1] - direction[1] * reference[0],
    ]
    side_norm = math.sqrt(sum(component * component for component in side_a))
    if side_norm <= 1.0e-12:
        return
    side_a = [component / side_norm for component in side_a]
    side_b = [
        direction[1] * side_a[2] - direction[2] * side_a[1],
        direction[2] * side_a[0] - direction[0] * side_a[2],
        direction[0] * side_a[1] - direction[1] * side_a[0],
    ]
    head_depth = 0.38 * magnitude
    wing = 0.18 * magnitude
    base = [head[axis] - head_depth * direction[axis] for axis in range(3)]
    fins = []
    for side in (side_a, side_b):
        fins.append([base[axis] + wing * side[axis] for axis in range(3)])
        fins.append([base[axis] - wing * side[axis] for axis in range(3)])
    for start, end in [(tail, head), *((head, fin) for fin in fins)]:
        x_values.extend([start[0], end[0], None])
        y_values.extend([start[1], end[1], None])
        z_values.extend([start[2], end[2], None])


def _arrow_trace(go, paths, u_max: float, arrow_length: float, *, colorbar: bool,
                 scale: dict | None = None):
    tail_x, tail_y, tail_z, speeds = [], [], [], []
    arrow_x, arrow_y, arrow_z = [], [], []
    for path_index, path in enumerate(paths):
        # One small, identity-stable arrow for every fourth streamline keeps
        # direction legible without building opaque glyph sheets in the view.
        if path_index % 4 or not path:
            continue
        sample = path[len(path) // 3]
        speed = _speed(sample["velocity"])
        if speed <= 1.0e-12:
            continue
        position = sample["position"]
        velocity = sample["velocity"]
        vector = [arrow_length * velocity[axis] / speed for axis in range(3)]
        tail_x.append(position[0])
        tail_y.append(position[1])
        tail_z.append(position[2])
        _append_arrow_segments(arrow_x, arrow_y, arrow_z, position, vector)
        speeds.append(speed)
    scale = scale or speed_scale_config(speeds, u_max)
    colour_values = [_speed_colour_value(speed, scale) for speed in speeds]
    colorbar_config = {
        "title": {"text": scale["title"], "font": {"color": _PAPER_TEXT, "size": 14}},
        "thickness": 28,
        "len": 0.72,
        "x": 1.015,
        "y": 0.54,
        "tickfont": {"color": _PAPER_TEXT, "size": 11},
        "tickvals": [_speed_colour_value(value, scale) for value in scale["tick_mps"]],
        "ticktext": [f"{value:.3g}" for value in scale["tick_mps"]],
        "outlinecolor": _PAPER_TEXT,
        "outlinewidth": 1,
        "bgcolor": "rgba(255,255,255,0.88)",
    }
    arrows = go.Scatter3d(
        x=arrow_x, y=arrow_y, z=arrow_z, mode="lines",
        line={"color": "#17324d", "width": 3},
        name="U 方向箭头", hoverinfo="skip", showlegend=False,
    )
    # The arrows are deliberately normalised to a fixed display length, so a
    # transparent speed anchor carries the physical |U| colourbar while the
    # visible arrows remain fixed-length and direction-only.
    speed_anchor = go.Scatter3d(
        x=tail_x, y=tail_y, z=tail_z, mode="markers", marker={
            "size": 0.1, "opacity": 0.0, "color": colour_values,
            "colorscale": _VELOCITY_COLORSCALE, "cmin": scale["cmin"], "cmax": scale["cmax"],
            "showscale": colorbar, "colorbar": colorbar_config,
        }, name="|U| 色标", hoverinfo="skip", showlegend=False,
    )
    return arrows, speed_anchor


def _particle_trace(go, paths, elapsed: float, window: float, frames: int,
                    arrow_length: float, u_free: float, speed_scale: dict):
    interval = window / _RELEASE_COUNT
    trail_duration = min(
        window,
        max(0.75 * interval, 2.0 * window / max(frames - 1, 1)),
    )
    # Keep the HTML payload responsive: all CFD streamlines remain visible,
    # while the moving overlay uses a stable, representative subset.  The
    # subset is identity-based (not frame-order based), so it never flickers.
    path_stride = max(1, math.ceil(len(paths) / 48))
    active_path_count = math.ceil(len(paths) / path_stride)
    release_stride = 4 if active_path_count * _RELEASE_COUNT > 2200 else (
        2 if active_path_count * _RELEASE_COUNT > 900 else 1)
    trail_x, trail_y, trail_z = [], [], []
    trail_colours = []
    arrow_x, arrow_y, arrow_z = [], [], []
    cutoff = 0.02 * max(u_free, 1.0e-12)
    for path_index, path in enumerate(paths):
        if path_index % path_stride:
            continue
        release_time = -window
        release_index = 0
        while release_time <= elapsed + 1.0e-12:
            age = elapsed - release_time
            if release_index % release_stride == 0 and path[0]["time"] <= age <= path[-1]["time"]:
                trail_start = max(path[0]["time"], age - trail_duration)
                trail = [_interpolate(path, trail_start)]
                trail.extend(
                    (sample["position"], sample["velocity"])
                    for sample in path if trail_start < sample["time"] < age
                )
                trail.append(_interpolate(path, age))
                for position, velocity in trail:
                    trail_x.append(position[0])
                    trail_y.append(position[1])
                    trail_z.append(position[2])
                    trail_colours.append(_speed_colour_value(_speed(velocity), speed_scale))
                trail_x.append(None)
                trail_y.append(None)
                trail_z.append(None)
                trail_colours.append(speed_scale["cmin"])
                position, velocity = trail[-1]
                speed = _speed(velocity)
                if speed >= cutoff and _stable_particle_arrow(path_index, release_index, 16):
                    vector = [arrow_length * velocity[axis] / speed for axis in range(3)]
                    _append_arrow_segments(arrow_x, arrow_y, arrow_z, position, vector)
            release_time += interval
            release_index += 1
    line = go.Scatter3d(
        x=trail_x, y=trail_y, z=trail_z, mode="lines",
        line={"color": trail_colours, "width": 3, "colorscale": _VELOCITY_COLORSCALE,
              "cmin": speed_scale["cmin"], "cmax": speed_scale["cmax"]},
        opacity=0.78, name="示踪粒子轨迹", hoverinfo="skip",
    )
    arrows = go.Scatter3d(
        x=arrow_x, y=arrow_y, z=arrow_z, mode="lines",
        line={"color": "#17324d", "width": 3},
        name="粒子方向箭头", hoverinfo="skip", showlegend=False,
    )
    return line, arrows


def u_max_from_paths(paths) -> float:
    values = [_speed(sample["velocity"]) for path in paths for sample in path]
    return max(values) if values else 1.0


def build_interactive_figure(dataset: dict, vehicle_color: str = "#102947",
                             frames: int = 120, fps: int = DEFAULT_ANIMATION_FPS):
    """Build a Plotly orbit viewer from an exported, real-field dataset."""
    if frames < 2 or fps <= 0:
        raise ValueError("frames must be >= 2 and fps must be positive")
    try:
        import plotly.graph_objects as go
    except ImportError as exc:  # pragma: no cover - exercised by deployment env
        raise RuntimeError("interactive viewer requires optional dependency plotly") from exc
    body = dataset.get("body") or {}
    vertices = body.get("vertices") or []
    faces = body.get("faces") or []
    paths = dataset.get("streamlines") or []
    if not vertices or not faces or not paths:
        raise ValueError("interactive dataset needs body triangles and U streamlines")
    parsed_colour = parse_vehicle_color(vehicle_color)
    rgb = "#%02x%02x%02x" % tuple(round(value * 255) for value in parsed_colour)
    xs = [float(point[0]) for point in vertices]
    ys = [float(point[1]) for point in vertices]
    zs = [float(point[2]) for point in vertices]
    if any(not math.isfinite(value) for value in xs + ys + zs):
        raise ValueError("body mesh contains non-finite coordinates")
    face_i = [int(face[0]) for face in faces]
    face_j = [int(face[1]) for face in faces]
    face_k = [int(face[2]) for face in faces]
    u_max = float(dataset.get("u_max_mps") or u_max_from_paths(paths))
    if not math.isfinite(u_max) or u_max <= 0:
        raise ValueError("u_max_mps must be finite and positive")
    speed_values = [_speed(sample["velocity"]) for path in paths for sample in path]
    speed_scale = speed_scale_config(speed_values, u_max)
    bounds = (
        min(xs), max(xs), min(ys), max(ys), min(zs), max(zs),
    )
    length = max(bounds[1] - bounds[0], 1.0e-6)
    height = max(bounds[5] - bounds[4], 1.0e-6)
    arrow_length = 0.08 * height
    body_trace = go.Mesh3d(
        x=xs, y=ys, z=zs, i=face_i, j=face_j, k=face_k,
        color=rgb, opacity=0.96, flatshading=False,
        lighting={"ambient": 0.52, "diffuse": 0.78, "specular": 0.55, "roughness": 0.28},
        lightposition={"x": -2 * length, "y": -3 * length, "z": 2 * length},
        name="车辆外形（CFD STL）", hoverinfo="skip",
    )
    line_traces = []
    for path_index, path in enumerate(paths):
        path_speeds = [_speed(sample["velocity"]) for sample in path]
        line_traces.append(go.Scatter3d(
            x=[sample["position"][0] for sample in path],
            y=[sample["position"][1] for sample in path],
            z=[sample["position"][2] for sample in path],
            mode="lines", line={
                "color": [_speed_colour_value(speed, speed_scale) for speed in path_speeds],
                "colorscale": _VELOCITY_COLORSCALE, "cmin": speed_scale["cmin"],
                "cmax": speed_scale["cmax"], "width": 2,
            },
            opacity=0.62,
            name="U 流线" if path_index == 0 else None,
            customdata=path_speeds, hovertemplate="|U| = %{customdata:.2f} m/s<extra></extra>",
            showlegend=path_index == 0,
        ))
    static_arrows, speed_anchor = _arrow_trace(
        go, paths, u_max, arrow_length, colorbar=True, scale=speed_scale)
    window = float(dataset.get("transport_window_s") or 1.0)
    if not math.isfinite(window) or window <= 0:
        raise ValueError("transport_window_s must be finite and positive")
    # Start with the first physical transport sample; frames then advance on
    # one global clock, exactly as the ParaView animation.
    first_particles = _particle_trace(go, paths, 0.0, window, frames, arrow_length,
                                      float(dataset.get("u_free_mps") or 1.0), speed_scale)
    particle_line_index = 1 + len(line_traces) + 2
    particle_arrow_index = particle_line_index + 1
    data = [body_trace, *line_traces, static_arrows, speed_anchor,
            first_particles[0], first_particles[1]]
    frame_list = []
    transport_times = []
    for frame_index in range(frames):
        elapsed = window * frame_index / max(frames - 1, 1)
        transport_times.append(elapsed)
        particles = _particle_trace(
            go, paths, elapsed, window, frames, arrow_length,
            float(dataset.get("u_free_mps") or 1.0),
            speed_scale,
        )
        frame_list.append(go.Frame(
            name=f"frame_{frame_index:04d}",
            data=[particles[0], particles[1]],
            traces=[particle_line_index, particle_arrow_index],
        ))
    camera = {"eye": {"x": 1.75, "y": -1.85, "z": 0.98}, "up": {"x": 0, "y": 0, "z": 1}}
    frame_duration = max(1, round(1000 / fps))
    slider_steps = [
        {
            "label": f"{elapsed:.3f} s",
            "method": "animate",
            "args": [[f"frame_{index:04d}"], {
                "mode": "immediate",
                "frame": {"duration": 0, "redraw": True},
                "transition": {"duration": 0},
            }],
        }
        for index, elapsed in enumerate(transport_times)
    ]
    figure = go.Figure(data=data, frames=frame_list)
    figure.update_layout(
        title={
            "text": "数值风洞｜稳态 CFD U(x) 示踪粒子",
            "font": {"color": _PAPER_TEXT, "size": 21},
        },
        paper_bgcolor=_PAPER_BG, plot_bgcolor=_PAPER_BG,
        font={"color": _PAPER_TEXT},
        margin={"l": 10, "r": 110, "t": 58, "b": 60},
        showlegend=False,
        uirevision="aeroforge-steady-particles",
        scene={
            "dragmode": "orbit", "aspectmode": "data", "camera": camera,
            "xaxis": {"title": "x (m)", "range": [bounds[0] - 0.45 * length, bounds[1] + 1.20 * length], "gridcolor": _PAPER_GRID, "zerolinecolor": "#8ea5b6", "titlefont": {"color": _PAPER_TEXT}},
            "yaxis": {"title": "y (m)", "range": [bounds[2] - 1.50 * (bounds[3] - bounds[2]), bounds[3] + 1.50 * (bounds[3] - bounds[2])], "gridcolor": _PAPER_GRID, "zerolinecolor": "#8ea5b6", "titlefont": {"color": _PAPER_TEXT}},
            "zaxis": {"title": "z (m)", "range": [bounds[4] - 0.10 * height, bounds[5] + 0.80 * height], "gridcolor": _PAPER_GRID, "zerolinecolor": "#8ea5b6", "titlefont": {"color": _PAPER_TEXT}},
            "bgcolor": _PAPER_BG,
        },
        updatemenus=[
            {
                "type": "buttons", "direction": "right", "x": 0.02, "y": 0.99,
                "showactive": False, "bgcolor": "#e1edf5", "font": {"color": _PAPER_TEXT},
                "buttons": [
                    {"label": "▶ 播放", "method": "animate", "args": [None, {
                        "fromcurrent": True,
                        "frame": {"duration": frame_duration, "redraw": True},
                        "transition": {"duration": 0},
                    }]},
                    {"label": "⏸ 暂停", "method": "animate", "args": [[None], {
                        "mode": "immediate", "frame": {"duration": 0, "redraw": False},
                        "transition": {"duration": 0},
                    }]},
                ],
            },
            {
                "type": "buttons", "direction": "right", "x": 0.25, "y": 0.99,
                "showactive": False, "bgcolor": "#e1edf5", "font": {"color": _PAPER_TEXT},
                "buttons": [
                    {"label": "前视", "method": "relayout", "args": [{"scene.camera": {
                        "eye": {"x": -1.9, "y": -1.1, "z": 0.72}, "up": {"x": 0, "y": 0, "z": 1}}}]},
                    {"label": "尾流", "method": "relayout", "args": [{"scene.camera": {
                        "eye": {"x": 1.9, "y": -1.1, "z": 0.72}, "up": {"x": 0, "y": 0, "z": 1}}}]},
                    {"label": "俯视", "method": "relayout", "args": [{"scene.camera": {
                        "eye": {"x": 0.05, "y": -0.05, "z": 2.55}, "up": {"x": 0, "y": 1, "z": 0}}}]},
                ],
            },
        ],
        sliders=[{
            "active": 0, "x": 0.02, "y": 0.02, "len": 0.72,
            "currentvalue": {"prefix": "输运时间: ", "font": {"color": _PAPER_TEXT}},
            "pad": {"t": 0, "b": 0}, "steps": slider_steps,
        }],
        annotations=[{
            "text": f"{speed_scale['note']}。拖动鼠标旋转，滚轮缩放。",
            "xref": "paper", "yref": "paper", "x": 0.02, "y": 0.055,
            "showarrow": False, "font": {"size": 12, "color": _PAPER_TEXT},
        }],
        meta={"speed_scale": speed_scale},
    )
    return figure


def _write_html(figure, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    figure.write_html(
        str(output), include_plotlyjs=True, full_html=True, auto_play=False,
        config={"scrollZoom": True, "displaylogo": False, "responsive": True},
    )


def render_interactive(case_dir: str | Path, u_free: float | None = None,
                       vehicle_color: str = "#102947", frames: int = 120,
                       fps: int = DEFAULT_ANIMATION_FPS, timeout: float = 1200.0) -> dict:
    """Export real field data and write a self-contained orbit/animation HTML."""
    case = Path(case_dir).resolve()
    if not case.exists():
        return {"status": "skipped", "interactive_paths": [],
                "note": f"算例目录不存在: {case}"}
    if not _has_result_field(case):
        return {"status": "skipped", "interactive_paths": [],
                "note": "缺少非零时刻 U 结果场，跳过交互式可视化"}
    try:
        geometry = _geometry_evidence(case)
    except ValueError as exc:
        return {"status": "failed", "interactive_paths": [], "note": str(exc)}
    if frames < 2 or fps <= 0:
        return {"status": "failed", "interactive_paths": [],
                "note": "交互动画帧数必须 >= 2，fps 必须 > 0"}
    try:
        parse_vehicle_color(vehicle_color)
    except ValueError as exc:
        return {"status": "failed", "interactive_paths": [], "note": str(exc)}
    pv = find_pvpython()
    if pv is None:
        return {"status": "skipped", "interactive_paths": [],
                "note": "未找到 pvpython，交互式真实场导出跳过"}
    try:
        import plotly  # noqa: F401
    except ImportError:
        return {"status": "skipped", "interactive_paths": [],
                "note": "未安装 plotly，交互式可视化跳过（静态 ParaView 结果仍可用）"}
    if u_free is None or u_free <= 0:
        u_free = read_freestream(case) or 40.0
    paths = interactive_output_paths(case)
    paths["directory"].mkdir(parents=True, exist_ok=True)
    previous_data_mtime = paths["data"].stat().st_mtime_ns if paths["data"].exists() else -1
    try:
        process = subprocess.run(
            [str(pv), str(_EXPORT_TEMPLATE), str(case), f"{float(u_free):g}", str(paths["data"])],
            capture_output=True, text=True, timeout=timeout,
            encoding="utf-8", errors="replace",
        )
    except subprocess.TimeoutExpired:
        return {"status": "failed", "interactive_paths": [],
                "note": f"交互式数据导出超时（>{timeout:g}s）"}
    if process.returncode != 0:
        tail = (process.stderr or process.stdout or "")[-600:]
        return {"status": "failed", "interactive_paths": [],
                "note": tail.strip() or "ParaView 交互式数据导出失败"}
    if not paths["data"].exists() or paths["data"].stat().st_mtime_ns <= previous_data_mtime:
        return {"status": "failed", "interactive_paths": [],
                "note": "ParaView 未生成新的交互式 U 数据"}
    try:
        dataset = json.loads(paths["data"].read_text(encoding="utf-8"))
        figure = build_interactive_figure(
            dataset, vehicle_color=vehicle_color, frames=frames, fps=fps,
        )
        speed_values = [_speed(sample["velocity"])
                        for path in dataset.get("streamlines", [])
                        for sample in path]
        speed_scale = speed_scale_config(
            speed_values, float(dataset.get("u_max_mps") or u_max_from_paths(dataset["streamlines"])))
        _write_html(figure, paths["html"])
    except (OSError, ValueError, TypeError, RuntimeError, json.JSONDecodeError) as exc:
        return {"status": "failed", "interactive_paths": [],
                "note": f"交互式 HTML 生成失败: {exc}"}
    manifest = {
        "schema_version": 1,
        "case": str(case),
        "source_field": "U",
        "source_field_time": dataset.get("source_field_time"),
        "source_field_time_note": dataset.get("source_field_time_note"),
        "source_geometry": geometry,
        "template_sha256": _sha256_file(_EXPORT_TEMPLATE),
        "sampling_template_sha256": _sha256_file(_EXPORT_TEMPLATE.with_name("velocity_sampling.py")),
        "viewer_sha256": _sha256_file(Path(__file__)),
        "interpolation": dataset.get("interpolation"),
        "source_point_speed_max_mps": dataset.get("source_point_speed_max_mps"),
        "data_sha256": _sha256_file(paths["data"]),
        "html_sha256": _sha256_file(paths["html"]),
        "vehicle_color": vehicle_color.upper(),
        "frames": int(frames),
        "fps": int(fps),
        "transport_window_s": dataset.get("transport_window_s"),
        "speed_scale": speed_scale,
        "release_count_per_transport_cycle": _RELEASE_COUNT,
        "streamline_count": dataset.get("streamline_count"),
        "body_display_faces": (dataset.get("body") or {}).get("display_faces"),
        "interaction": "Plotly scene.dragmode=orbit; mouse drag rotates, wheel zooms; preset front/wake/top cameras",
        "interpretation": "self-contained browser view of a frozen steady RANS U(x) field; massless tracer playback, not transient turbulence or smoke",
    }
    paths["manifest"].write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    note = "交互式 HTML 已生成：含 |U| 色标、固定长度 U 箭头、鼠标轨道旋转/滚轮缩放和连续示踪粒子播放"
    return {
        "status": "completed", "interactive_paths": [paths["html"]],
        "data_path": paths["data"], "manifest_path": paths["manifest"],
        "note": note,
    }
