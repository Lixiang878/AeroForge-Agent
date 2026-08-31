# -*- coding: utf-8 -*-
"""Render field-grounded vehicle-aerodynamics frames with ParaView."""
import math
import os
import sys
import bisect
import builtins
import json

from velocity_sampling import (
    SAMPLING_METHOD, point_field_speed_max, prepare_velocity_sampling,
    validate_sampled_speed,
)

from paraview import servermanager  # noqa: E402
from paraview.simple import (  # noqa: E402
    CellDatatoPointData,
    ColorBy,
    CreateView,
    GetAnimationScene,
    GetColorTransferFunction,
    GetScalarBar,
    OpenFOAMReader,
    Plane,
    ProgrammableSource,
    Render,
    SaveScreenshot,
    SetActiveView,
    Show,
    STLReader,
    Glyph,
    StreamTracer,
    StreamTracerWithCustomSource,
    Text,
    Tube,
)


def setp(obj, keys, value):
    for key in keys:
        try:
            setattr(obj, key, value)
            return True
        except Exception:
            continue
    return False


def colour_by_velocity(display):
    try:
        ColorBy(display, ("POINTS", "U", "Magnitude"))
    except Exception:
        ColorBy(display, ("POINTS", "U"))


def arrow_neutral_colour(display):
    """Make fixed length U-oriented arrows readable; streamlines carry |U|."""
    ColorBy(display, ("POINTS", ""))
    setp(display, ("DiffuseColor", "diffuse_color"), [0.08, 0.17, 0.28])
    setp(display, ("AmbientColor", "ambient_color"), [0.04, 0.10, 0.16])


def incoming_yz_seed(domain_bounds, vehicle_bounds, columns=15, rows=11):
    """Return a finite near-body YZ seed plane inside the CFD mesh.

    The plane is a deliberately finite near-body window, not the full-domain
    inlet.  Its x location is upstream of the STL and must intersect the
    internal mesh; y/z limits are clipped to internalMesh bounds.
    """
    domain = tuple(float(value) for value in domain_bounds)
    vehicle = tuple(float(value) for value in vehicle_bounds)
    if len(domain) != 6 or len(vehicle) != 6:
        raise ValueError("domain and vehicle bounds must contain six values")
    if any(not math.isfinite(value) for value in domain + vehicle):
        raise ValueError("domain and vehicle bounds must be finite")
    dx0, dx1, dy0, dy1, dz0, dz1 = domain
    vx0, vx1, vy0, vy1, vz0, vz1 = vehicle
    vlength, vwidth, vheight = vx1 - vx0, vy1 - vy0, vz1 - vz0
    if min(vlength, vwidth, vheight) <= 0.0 or dx0 >= dx1 or dy0 >= dy1 or dz0 >= dz1:
        raise ValueError("invalid domain or vehicle bounds")
    if int(columns) < 1 or int(rows) < 1:
        raise ValueError("seed plane resolution must be positive")
    x = vx0 - 0.30 * vlength
    if not dx0 < x < dx1:
        raise ValueError("near-body seed plane does not intersect internalMesh")
    eps = builtins.max(1.0e-5, 1.0e-3 * vheight)
    y_min = builtins.max(dy0 + eps, vy0 - 0.20 * vwidth)
    y_max = builtins.min(dy1 - eps, vy1 + 0.20 * vwidth)
    z_min = builtins.max(dz0 + eps, vz0 - eps)
    z_max = builtins.min(dz1 - eps, vz1 + 0.60 * vheight)
    if y_min >= y_max or z_min >= z_max:
        raise ValueError("near-body seed plane has no valid internalMesh area")
    return {
        "x": x,
        "y_min": y_min,
        "y_max": y_max,
        "z_min": z_min,
        "z_max": z_max,
        "x_resolution": int(columns),
        "y_resolution": int(rows),
    }


def find_stl(case):
    for candidate in (
        os.path.join(case, "..", "geometry", "model.stl"),
        os.path.join(case, "constant", "triSurface", "body.stl"),
    ):
        if os.path.exists(candidate):
            return os.path.abspath(candidate)
    raise SystemExit("vehicle STL not found")


_SPEED_LOG_RATIO = 8.0
_PAPER_BG_HEX = "#f6f9fc"


def dynamic_velocity_colour_max(sampled_u_max, observed_u_max=None):
    """Return a padded upper limit from the velocities actually displayed.

    ``u_free`` controls physical transport timing only.  It must not enlarge
    the colour range: a mismatched inlet hint otherwise compresses all real U
    samples into one dark colour.  ``observed_u_max`` is supplied by the
    moving particle subset when available.
    """
    values = [float(sampled_u_max)]
    if observed_u_max is not None:
        values.append(float(observed_u_max))
    if any(not math.isfinite(value) or value <= 0.0 for value in values):
        raise ValueError("observed colour speed maxima must be finite and positive")
    return 1.08 * builtins.max(values)


def velocity_colour_scale_mode(sampled_u_min, colour_u_max):
    """Choose a fixed physical |U| colour scale for a wide speed range."""
    lower = float(sampled_u_min)
    upper = float(colour_u_max)
    if (not math.isfinite(lower) or not math.isfinite(upper)
            or lower < 0.0 or upper <= 0.0 or upper < lower):
        raise ValueError("colour speed limits must be finite, non-negative, and ordered")
    # Keep this helper self-contained: the regression suite executes it without
    # the ParaView template's module-level constants.
    ratio_threshold = float(globals().get("_SPEED_LOG_RATIO", 8.0))
    return "log10" if lower > 0.0 and upper / lower >= ratio_threshold else "linear"


def fetched_streamline_velocity_range(tracers):
    """Return the finite positive and maximum |U| values from StreamTracer."""
    minimum = None
    maximum = 0.0
    for tracer in tracers:
        data = servermanager.Fetch(tracer)
        if data is None:
            continue
        vectors = data.GetPointData().GetArray("U")
        if vectors is None:
            raise ValueError("StreamTracer output is missing the U velocity array")
        for point_index in range(data.GetNumberOfPoints()):
            vector = tuple(float(value) for value in vectors.GetTuple(point_index))
            if len(vector) != 3 or any(not math.isfinite(value) for value in vector):
                raise ValueError("StreamTracer U contains a non-finite vector")
            speed = math.sqrt(builtins.sum(value * value for value in vector))
            maximum = builtins.max(maximum, speed)
            if minimum is None or speed < minimum:
                minimum = speed
    if minimum is None or maximum <= 0.0:
        raise ValueError("StreamTracer output contains no positive velocity")
    return float(minimum), float(maximum)


if len(sys.argv) != 7:
    raise SystemExit(
        "usage: streamline_animation.py CASE UFREE R,G,B FRAMES MODE OUTPUT_DIR")

case = os.path.abspath(sys.argv[1])
u_free = float(sys.argv[2])
body_colour = [float(value) for value in sys.argv[3].split(",")]
frame_count = int(sys.argv[4])
mode = sys.argv[5]
output_dir = os.path.abspath(sys.argv[6])
if mode not in {"steady_orbit", "steady_particles", "transient"}:
    raise SystemExit(f"unsupported animation mode: {mode}")
if len(body_colour) != 3 or any(value < 0.0 or value > 1.0 for value in body_colour):
    raise SystemExit("vehicle colour must contain three RGB values in [0, 1]")
os.makedirs(output_dir, exist_ok=True)

foam = os.path.join(case, "case.foam")
if not os.path.exists(foam):
    open(foam, "w").close()

body = STLReader(FileNames=[find_stl(case)])
body.UpdatePipeline()
bounds = body.GetDataInformation().GetBounds()
if not bounds or bounds[0] > bounds[1]:
    raise SystemExit("empty vehicle STL")
x0, x1, y0, y1, z0, z1 = bounds
length, width, height = x1 - x0, y1 - y0, z1 - z0
cx, cy, cz = 0.5 * (x0 + x1), 0.5 * (y0 + y1), 0.5 * (z0 + z1)

volume = OpenFOAMReader(FileName=foam)
volume.UpdatePipeline()
times = [value for value in list(volume.TimestepValues or []) if value > 0]
if not times:
    raise SystemExit("no non-zero OpenFOAM time available")
if mode == "transient" and len(times) < frame_count:
    raise SystemExit(
        f"transient animation needs {frame_count} physical times, found {len(times)}")

scene = GetAnimationScene()
scene.AnimationTime = times[-1]
volume.UpdatePipeline(times[-1])
c2p = CellDatatoPointData(Input=volume)
setp(c2p, ("ProcessAllArrays",), 1)
c2p.UpdatePipeline(times[-1])
flow_field = prepare_velocity_sampling(c2p, times[-1])
domain_bounds = c2p.GetDataInformation().GetBounds()

view = CreateView("RenderView")
SetActiveView(view)
setp(view, ("ViewSize",), [1280, 720])
setp(view, ("Background", "background"), [0.965, 0.978, 0.990])
setp(view, ("Background2", "background2"), [0.82, 0.885, 0.94])
setp(view, ("UseColorPaletteForBackground",), 0)
setp(view, ("BackgroundColorMode",), "Gradient")
setp(view, ("OrientationAxesVisibility",), 0)
setp(view, ("UseFXAA",), 1)
setp(view, ("MultiSamples",), 8)
setp(view, ("UseDepthPeeling",), 1)
setp(view, ("UseSSAO",), 1)

body_display = Show(body, view)
ColorBy(body_display, ("POINTS", ""))
setp(body_display, ("DiffuseColor", "diffuse_color"), body_colour)
setp(body_display, ("Ambient", "ambient"), 0.48)
setp(body_display, ("Diffuse", "diffuse"), 1.0)
setp(body_display, ("Specular", "specular"), 0.70)
setp(body_display, ("SpecularPower", "specular_power"), 55.0)
if setp(body_display, ("Interpolation",), "PBR"):
    setp(body_display, ("Metallic",), 0.25)
    setp(body_display, ("Roughness",), 0.22)

seed_window = incoming_yz_seed(domain_bounds, (x0, x1, y0, y1, z0, z1))
ground_z = builtins.max(domain_bounds[4] + 1.0e-5, z0 - 0.002 * builtins.max(height, 1.0))
ground = Plane()
ground.Origin = [x0 - 0.55 * length, y0 - 0.65 * width, ground_z]
ground.Point1 = [x1 + 1.35 * length, y0 - 0.65 * width, ground_z]
ground.Point2 = [x0 - 0.55 * length, y1 + 0.65 * width, ground_z]
ground_display = Show(ground, view)
setp(ground_display, ("DiffuseColor", "diffuse_color"), [0.70, 0.75, 0.80])
setp(ground_display, ("Ambient", "ambient"), 0.48)


incoming_seed_plane = Plane()
incoming_seed_plane.Origin = [
    seed_window["x"], seed_window["y_min"], seed_window["z_min"]]
incoming_seed_plane.Point1 = [
    seed_window["x"], seed_window["y_max"], seed_window["z_min"]]
incoming_seed_plane.Point2 = [
    seed_window["x"], seed_window["y_min"], seed_window["z_max"]]
incoming_seed_plane.XResolution = seed_window["x_resolution"]
incoming_seed_plane.YResolution = seed_window["y_resolution"]
incoming_seed_plane.UpdatePipeline()


def add_streams():
    tracer = StreamTracerWithCustomSource(Input=flow_field, SeedSource=incoming_seed_plane)
    setp(tracer, ("Vectors", "vectors"), ("POINTS", "U"))
    setp(tracer, ("IntegrationDirection",), "FORWARD")
    setp(tracer, ("InterpolatorType",), "Interpolator with Cell Locator")
    setp(tracer, ("MaximumSteps", "MaximumNumberOfSteps"), 8000)
    setp(tracer, ("MaximumStreamlineLength",), 8.0 * length)
    setp(tracer, ("TerminalSpeed",), 1.0e-3)
    tube = Tube(Input=tracer)
    setp(tube, ("Radius", "radius"), 0.0008 * builtins.min(width, height))
    setp(tube, ("NumberOfSides", "number_of_sides"), 6)
    display = Show(tube, view)
    colour_by_velocity(display)
    setp(display, ("Opacity", "opacity"), 0.93)
    setp(display, ("Ambient",), 1.0)
    setp(display, ("Diffuse",), 0.0)
    setp(display, ("Specular",), 0.0)
    stream_tracers.append(tracer)
    return display


stream_tracers = []
if mode == "steady_particles":
    stream_opacity = 0.18
else:
    # One YZ seed plane gives uniform coverage of the near-body incoming
    # cross-section instead of three visually misleading streamline layers.
    stream_opacity = 0.62
stream_displays = (add_streams(),)

colour_sample_times = times[-frame_count:] if mode == "transient" else [times[-1]]
try:
    sampled_ranges = []
    source_speed_maxima = []
    for sample_time in colour_sample_times:
        flow_field.UpdatePipeline(sample_time)
        for tracer in stream_tracers:
            tracer.UpdatePipeline(sample_time)
        frame_min, frame_max = fetched_streamline_velocity_range(stream_tracers)
        source_max = point_field_speed_max(flow_field)
        validate_sampled_speed(frame_max, source_max)
        sampled_ranges.append((frame_min, frame_max))
        source_speed_maxima.append(source_max)
    sampled_u_min = builtins.min(value[0] for value in sampled_ranges)
    sampled_u_max = builtins.max(value[1] for value in sampled_ranges)
except ValueError as exc:
    raise SystemExit(f"[animation] cannot determine U colour range: {exc}")
u_max = dynamic_velocity_colour_max(sampled_u_max)
colour_scale_mode = velocity_colour_scale_mode(sampled_u_min, u_max)
colour_scale_min = sampled_u_min
lut = GetColorTransferFunction("U")
colour_preset_applied = False
for preset in ("Viridis (matplotlib)", "Viridis", "Cividis", "Cividis (matplotlib)"):
    try:
        lut.ApplyPreset(preset, False)
        colour_preset_applied = True
        break
    except Exception:
        continue
if not colour_preset_applied:
    midpoint = (math.sqrt(colour_scale_min * u_max)
                if colour_scale_mode == "log10"
                else 0.5 * (colour_scale_min + u_max))
    lut.RGBPoints = [
        colour_scale_min, 0.000, 0.135, 0.304,
        midpoint, 0.126, 0.553, 0.553,
        u_max, 0.993, 0.906, 0.144,
    ]
lut.RescaleTransferFunction(colour_scale_min, u_max)
setp(lut, ("UseLogScale", "use_log_scale"), int(colour_scale_mode == "log10"))
setp(lut, ("AutomaticRescaleRangeMode",), "Never")
for display in stream_displays:
    setp(display, ("LookupTable",), lut)
    setp(display, ("Opacity", "opacity"), stream_opacity)
bar = GetScalarBar(lut, view)
bar.Title = "Speed |U| (m/s)" + (" [log10]" if colour_scale_mode == "log10" else "")
setp(bar, ("ComponentTitle",), "")
setp(bar, ("Orientation",), "Horizontal")
setp(bar, ("WindowLocation",), "Any Location")
setp(bar, ("Position",), [0.54, 0.055])
setp(bar, ("ScalarBarLength",), 0.40)
setp(bar, ("ScalarBarThickness",), 22)
setp(bar, ("TitleFontSize",), 20)
setp(bar, ("LabelFontSize",), 17)
setp(bar, ("AutomaticLabelFormat",), 0)
setp(bar, ("TitleColor",), [0.086, 0.196, 0.290])
setp(bar, ("LabelColor",), [0.086, 0.196, 0.290])
setp(bar, ("LabelFormat",), "%.3g")
setp(bar, ("RangeLabelFormat",), "%.3g")
setp(bar, ("UseCustomLabels",), 1)
colourbar_labels = []
for i in range(5):
    raw_label = (colour_scale_min * (u_max / colour_scale_min) ** (i / 4.0)
                 if colour_scale_mode == "log10"
                 else colour_scale_min + (u_max - colour_scale_min) * i / 4.0)
    # ParaView may bypass LabelFormat for CustomLabels, so store concise
    # three-significant-digit positions directly in the scalar bar.
    colourbar_labels.append(float("{:.3g}".format(raw_label)))
setp(bar, ("CustomLabels",), colourbar_labels)
setp(bar, ("AddRangeLabels",), 0)
setp(bar, ("DrawBackground",), 1)
setp(bar, ("BackgroundColor",), [0.965, 0.978, 0.990])
setp(bar, ("BackgroundOpacity",), 0.94)
setp(bar, ("DrawFrame",), 1)
setp(bar, ("FrameColor",), [0.086, 0.196, 0.290])
setp(bar, ("FrameWidth",), 1)

caption = Text()
caption_display = Show(caption, view)
setp(caption_display, ("WindowLocation",), "Upper Left Corner")
setp(caption_display, ("Color",), [0.086, 0.196, 0.290])
setp(caption_display, ("FontSize",), 18)
setp(caption_display, ("Bold",), 1)

camera = view.GetActiveCamera()
Render(view)


def validate_integration_times(times):
    """Require finite, strictly increasing StreamTracer IntegrationTime."""
    values = [float(value) for value in times]
    if len(values) < 2 or any(not math.isfinite(value) for value in values):
        raise ValueError("IntegrationTime must contain at least two finite samples")
    if any(right <= left for left, right in zip(values, values[1:])):
        raise ValueError("IntegrationTime samples must be strictly increasing")
    return values


def streamline_cell_is_usable(times):
    """Accept only cells with a strictly increasing IntegrationTime axis."""
    try:
        validate_integration_times(times)
    except ValueError:
        return False
    return True


def validate_streamline_sample(transport_time, xyz, velocity):
    """Require one finite 3-D StreamTracer time/position/velocity sample."""
    if velocity is None:
        raise ValueError("StreamTracer output is missing the U velocity array")
    try:
        time_value = float(transport_time)
        position = tuple(float(value) for value in xyz)
        vector = tuple(float(value) for value in velocity)
    except (TypeError, ValueError):
        raise ValueError("StreamTracer time, coordinates, and U must be numeric")
    if len(position) != 3 or len(vector) != 3:
        raise ValueError("StreamTracer coordinates and U must have three components")
    if any(not math.isfinite(value) for value in (time_value,) + position + vector):
        raise ValueError("StreamTracer time, coordinates, and U must be finite")
    return time_value, position, vector


def velocity_magnitude(velocity):
    """Return the finite Euclidean norm used for low-speed arrow filtering."""
    values = tuple(float(value) for value in velocity)
    if len(values) != 3:
        raise ValueError("velocity must be a finite three-component vector")
    for value in values:
        if not math.isfinite(value):
            raise ValueError("velocity must be a finite three-component vector")
    return math.sqrt(builtins.sum(value * value for value in values))


def fetched_streamline_paths(tracers):
    """Read actual StreamTracer coordinates keyed by its IntegrationTime."""
    paths = []
    for tracer in tracers:
        data = servermanager.Fetch(tracer)
        if data is None or not data.GetPoints():
            continue
        integration = data.GetPointData().GetArray("IntegrationTime")
        vectors = data.GetPointData().GetArray("U")
        if integration is None:
            raise ValueError("StreamTracer output is missing IntegrationTime")
        if vectors is None:
            raise ValueError("StreamTracer output is missing the U velocity array")
        for cell_index in range(data.GetNumberOfCells()):
            cell = data.GetCell(cell_index)
            ids = cell.GetPointIds()
            samples = []
            for point_index in range(ids.GetNumberOfIds()):
                point_id = ids.GetId(point_index)
                samples.append(validate_streamline_sample(
                    integration.GetTuple1(point_id),
                    data.GetPoint(point_id),
                    vectors.GetTuple(point_id),
                ))
            if not streamline_cell_is_usable([sample[0] for sample in samples]):
                print(f"[animation] skipped degenerate IntegrationTime cell {cell_index}")
                continue
            if len(samples) >= 2 and samples[-1][0] > samples[0][0]:
                paths.append(samples)
    return paths


def interpolate_sample(path, transport_time):
    """Interpolate coordinates between neighboring actual IntegrationTime values."""
    times = [sample[0] for sample in path]
    index = bisect.bisect_right(times, transport_time)
    if index <= 0:
        return path[0][1], path[0][2]
    if index >= len(path):
        return path[-1][1], path[-1][2]
    left, right = path[index - 1], path[index]
    span = right[0] - left[0]
    weight = 0.0 if span <= 0.0 else (transport_time - left[0]) / span
    position = tuple(left[1][axis] + weight * (right[1][axis] - left[1][axis]) for axis in range(3))
    velocity = tuple(left[2][axis] + weight * (right[2][axis] - left[2][axis]) for axis in range(3))
    return position, velocity


def steady_particle_release_interval(transport_window_s, frame_count=None):
    """Return a dense, frame-independent injection cadence.

    The release schedule is part of the particle model, not a side effect of
    the requested video frame count.  Sixty-four releases per transport cycle
    keep the visible trail continuous at both 30 and 60 fps while preserving
    the single physical IntegrationTime clock used for advection.
    """
    value = float(transport_window_s) / 64.0
    if not math.isfinite(value) or value <= 0.0:
        raise ValueError("transport window must be finite and positive")
    return value


def stable_particle_arrow(path_index, release_index, stride=4):
    """Select arrowheads by stable path/release identity, never point order."""
    path_value = int(path_index)
    release_value = int(release_index)
    stride_value = int(stride)
    if path_value < 0 or release_value < 0 or stride_value < 1:
        raise ValueError("path, release, and stride must be non-negative/positive")
    # The multiplier decorrelates neighboring paths while keeping selection
    # deterministic after IntegrationTime clipping changes point order.
    return (3 * path_value + release_value) % stride_value == 0


def particle_script(points, vertices, lines, include_vertices=True):
    """Create a ProgrammableSource payload with real sampled positions/U."""
    samples = list(points)
    return """import vtk
output = self.GetPolyDataOutput()
points = vtk.vtkPoints()
vectors = vtk.vtkFloatArray()
vectors.SetName('U')
vectors.SetNumberOfComponents(3)
for xyz, velocity in %r:
    points.InsertNextPoint(*xyz)
    vectors.InsertNextTuple3(*velocity)
output.SetPoints(points)
verts = vtk.vtkCellArray()
lines = vtk.vtkCellArray()
if %r:
    for cell in %r:
        verts.InsertNextCell(1)
        verts.InsertCellPoint(cell)
for cell in %r:
    line = vtk.vtkPolyLine()
    line.GetPointIds().SetNumberOfIds(len(cell))
    for point_index, point_id in enumerate(cell):
        line.GetPointIds().SetId(point_index, point_id)
    lines.InsertNextCell(line)
output.SetVerts(verts)
output.SetLines(lines)
output.GetPointData().AddArray(vectors)
output.GetPointData().SetActiveVectors('U')
""" % (samples, bool(include_vertices), list(vertices), list(lines))


def set_camera(position, focal_point):
    frame_scale = builtins.max(1.20 * height, 0.70 * length)
    setp(view, ("CameraFocalPoint",), list(focal_point))
    setp(view, ("CameraPosition",), list(position))
    setp(view, ("CameraViewUp",), [0.0, 0.0, 1.0])
    setp(view, ("CameraParallelProjection",), 1)
    setp(view, ("CameraParallelScale",), frame_scale)
    camera.SetFocalPoint(*focal_point)
    camera.SetPosition(*position)
    camera.SetViewUp(0.0, 0.0, 1.0)
    camera.SetParallelProjection(1)
    camera.SetParallelScale(frame_scale)

particle_paths = []
particle_source = None
particle_display = None
particle_coloured = False
particle_points = None
particle_glyph = None
particle_glyph_display = None
particle_glyph_coloured = False
particle_cycle_duration = None
particle_transport_window = None
particle_release_interval = None
particle_pre_release_duration = None
particle_observed_u_min = None
particle_observed_u_max = None
if mode == "steady_particles":
    particle_paths = fetched_streamline_paths(stream_tracers)
    if not particle_paths:
        raise SystemExit("steady_particles requires StreamTracer IntegrationTime data")
    # All paths share one physical clock.  Each path is displayed only while
    # its own actual IntegrationTime range contains the particle age.
    particle_transport_window = 4.0 * length / builtins.max(u_free, 1.0e-12)
    particle_cycle_duration = particle_transport_window
    particle_positive_speeds = [
        velocity_magnitude(sample[2])
        for path in particle_paths for sample in path
        if velocity_magnitude(sample[2]) > 0.0
    ]
    if not particle_positive_speeds:
        raise SystemExit("steady_particles requires at least one positive U sample")
    particle_observed_u_min = builtins.min(particle_positive_speeds)
    particle_observed_u_max = builtins.max(
        velocity_magnitude(sample[2])
        for path in particle_paths for sample in path)
    # Keep one fixed range for every frame, but include the actual sampled
    # streamline speeds so local acceleration is not silently clipped.
    sampled_u_min = builtins.min(sampled_u_min, particle_observed_u_min)
    u_max = dynamic_velocity_colour_max(sampled_u_max, particle_observed_u_max)
    colour_scale_mode = velocity_colour_scale_mode(sampled_u_min, u_max)
    colour_scale_min = sampled_u_min
    lut.RescaleTransferFunction(colour_scale_min, u_max)
    setp(lut, ("UseLogScale", "use_log_scale"), int(colour_scale_mode == "log10"))
    particle_release_interval = steady_particle_release_interval(
        particle_transport_window, frame_count)
    particle_pre_release_duration = particle_transport_window
    particle_source = ProgrammableSource()
    setp(particle_source, ("OutputDataSetType",), "vtkPolyData")
    particle_source.Script = particle_script([], [], [], include_vertices=False)
    particle_source.UpdatePipeline()
    particle_display = Show(particle_source, view)
    setp(particle_display, ("LookupTable",), lut)
    setp(particle_display, ("LineWidth", "line_width"), 1.5)
    setp(particle_display, ("Opacity", "opacity"), 1.0)
    particle_points = ProgrammableSource()
    setp(particle_points, ("OutputDataSetType",), "vtkPolyData")
    particle_points.Script = particle_script([], [], [], include_vertices=True)
    particle_points.UpdatePipeline()
    particle_glyph = Glyph(Input=particle_points, GlyphType="Arrow")
    setp(particle_glyph, ("OrientationArray", "orientation_array"), ["POINTS", "U"])
    setp(particle_glyph, ("ScaleArray", "scale_array"), ["POINTS", "No scale array"])
    setp(particle_glyph, ("ScaleFactor", "scale_factor"), 0.12 * height)
    # Point selection is performed before Glyph using stable path/release
    # identities.  Glyph must render every selected point; Every Nth Point
    # would renumber the clipped point set on each frame and cause flicker.
    setp(particle_glyph, ("GlyphMode", "glyph_mode"), "All Points")
    particle_glyph.UpdatePipeline()
    particle_glyph_display = Show(particle_glyph, view)
    arrow_neutral_colour(particle_glyph_display)
    setp(particle_glyph_display, ("Opacity", "opacity"), 1.0)


def update_particle_source(transport_elapsed_s):
    """Move particles using one shared elapsed time and actual path samples."""
    if particle_source is None or particle_cycle_duration is None:
        return
    frame_transport_interval = particle_cycle_duration / builtins.max(frame_count - 1, 1)
    # Keep at least two video-frame intervals of history.  The lower bound is
    # what prevents trails from disappearing between adjacent frames when a
    # release happens to fall between render samples.
    trail_duration = builtins.min(
        particle_cycle_duration,
        builtins.max(0.75 * particle_release_interval,
                     2.0 * frame_transport_interval),
    )
    samples = []
    head_samples = []
    lines = []
    # A dense release clock keeps trails continuous; arrowheads are sampled
    # more sparsely so they communicate direction without becoming a white
    # carpet over the smoke lines.
    particle_arrow_stride = 16
    for path_index, path in enumerate(particle_paths):
        release_time = -particle_pre_release_duration
        release_index = 0
        while release_time <= transport_elapsed_s + 1.0e-12:
            age = transport_elapsed_s - release_time
            if path[0][0] <= age <= path[-1][0]:
                trail_start = builtins.max(path[0][0], age - trail_duration)
                trail = [interpolate_sample(path, trail_start)]
                trail.extend(
                    (sample[1], sample[2])
                    for sample in path
                    if trail_start < sample[0] < age
                )
                trail.append(interpolate_sample(path, age))
                point_ids = []
                for position, velocity in trail:
                    point_ids.append(len(samples))
                    samples.append((position, velocity))
                lines.append(point_ids)
                head_position, head_velocity = interpolate_sample(path, age)
                speed = velocity_magnitude(head_velocity)
                if (speed >= 0.02 * builtins.max(u_free, 1.0e-12)
                        and stable_particle_arrow(
                            path_index, release_index, particle_arrow_stride)):
                    head_samples.append((head_position, head_velocity))
            release_time += particle_release_interval
            release_index += 1
    particle_source.Script = particle_script(samples, [], lines, include_vertices=False)
    particle_source.UpdatePipeline()
    head_vertices = list(range(len(head_samples)))
    particle_points.Script = particle_script(
        head_samples, head_vertices, [], include_vertices=True)
    particle_points.UpdatePipeline()
    particle_glyph.UpdatePipeline()


if mode == "transient":
    selected_times = times[-frame_count:]
else:
    selected_times = [times[-1]] * frame_count

for frame_number, time_value in enumerate(selected_times):
    if mode == "transient":
        scene.AnimationTime = time_value
        volume.UpdatePipeline(time_value)
        c2p.UpdatePipeline(time_value)
        flow_field.UpdatePipeline(time_value)
        caption.Text = f"TRANSIENT CFD  |  t = {time_value:g} s"
        position = (cx + 1.55 * length, cy - 1.55 * length, cz + 0.78 * length)
    elif mode == "steady_particles":
        transport_elapsed_s = (
            particle_cycle_duration * frame_number / builtins.max(frame_count - 1, 1)
        )
        update_particle_source(transport_elapsed_s)
        if not particle_coloured:
            colour_by_velocity(particle_display)
            # ColorBy may auto-rescale a shared LUT to the first particle
            # sample. Re-apply the observed field range for every frame.
            lut.RescaleTransferFunction(colour_scale_min, u_max)
            setp(lut, ("AutomaticRescaleRangeMode",), "Never")
            particle_coloured = True
        caption.Text = (
            f"STEADY CFD | TRACER ADVECTION\n"
            f"transport elapsed = {transport_elapsed_s:g} s"
        )
        position = (cx + 1.55 * length, cy - 1.55 * length, cz + 0.78 * length)
    else:
        phase = 2.0 * math.pi * frame_number / frame_count
        radius = 2.25 * length
        position = (
            cx + radius * math.cos(phase),
            cy + 0.72 * radius * math.sin(phase),
            cz + 0.52 * length)
        caption.Text = "STEADY CFD FIELD  |  CAMERA ORBIT"
    focal_point = (cx + 0.18 * length, cy, cz + 0.08 * height)
    set_camera(position, focal_point)
    Render(view)
    print(f"[animation] frame {frame_number + 1}/{frame_count} -> frame_{frame_number:04d}.png")
    SaveScreenshot(
        os.path.join(output_dir, f"frame_{frame_number:04d}.png"),
        view, ImageResolution=[1280, 720], TransparentBackground=0)

metadata = {
    "mode": mode,
    "source_field": "U",
    "interpolation": SAMPLING_METHOD,
    "source_point_speed_max_mps": builtins.max(source_speed_maxima),
    "colour_range_field_times": [float(value) for value in colour_sample_times],
    "seed_surface": "finite near-body YZ plane, not the full-domain inlet",
    "seed_plane": seed_window,
    "seed_plane_resolution": {
        "x_intervals": seed_window["x_resolution"],
        "y_intervals": seed_window["y_resolution"],
        "note": "Plane resolution is in the two in-plane directions; x is fixed",
    },
    "source_field_time": float(times[-1]),
    "source_field_times": [float(value) for value in selected_times],
    "source_field_time_note": (
        "steady OpenFOAM field time/iteration label; not physical transient time"
        if mode == "steady_particles" else "OpenFOAM reader time value"
    ),
    "particle_transport_times_s": (
        [
            float(particle_cycle_duration * frame_number / builtins.max(frame_count - 1, 1))
            for frame_number in range(frame_count)
        ] if mode == "steady_particles" else []
    ),
    "particle_cycle_duration_s": (
        float(particle_cycle_duration) if mode == "steady_particles" else None
    ),
    "release_interval_s": (
        float(particle_release_interval)
        if mode == "steady_particles" else None
    ),
    "release_count_per_transport_cycle": (
        int(round(particle_cycle_duration / particle_release_interval))
        if mode == "steady_particles" else None
    ),
    "injection_release_interval_s": (
        float(particle_release_interval) if mode == "steady_particles" else None
    ),
    "pre_release_duration_s": (
        float(particle_pre_release_duration)
        if mode == "steady_particles" else None
    ),
    "frame_transport_interval_s": (
        float(particle_cycle_duration / builtins.max(frame_count - 1, 1))
        if mode == "steady_particles" else None
    ),
    "trail_duration_s": (
        float(builtins.min(
            particle_cycle_duration,
            builtins.max(
                0.75 * particle_release_interval,
                2.0 * particle_cycle_duration / builtins.max(frame_count - 1, 1),
            ),
        ))
        if mode == "steady_particles" else None
    ),
    "particle_arrow_selection": (
        "stable path/release identity; stride=16; GlyphMode=All Points"
        if mode == "steady_particles" else None
    ),
    "particle_arrow_stride": 16 if mode == "steady_particles" else None,
    "streamline_sampled_u_min_mps": float(sampled_u_min),
    "streamline_sampled_u_max_mps": float(sampled_u_max),
    "particle_observed_u_min_mps": (
        float(particle_observed_u_min)
        if particle_observed_u_min is not None else None
    ),
    "sampled_u_max_mps": (
        float(particle_observed_u_max)
        if particle_observed_u_max is not None else None
    ),
    "colour_scale_mode": colour_scale_mode,
    "colour_scale_min_mps": float(colour_scale_min),
    "colour_scale_max_mps": float(u_max),
    "colour_scale_title": bar.Title,
    "colour_preset": "Viridis with Cividis fallback",
    "colour_scale_source": (
        "observed StreamTracer/particle |U| samples with 8% headroom; "
        "u_free is used only for transport timing"
    ),
    "arrow_length_encoding": (
        "fixed length; orientation=U; arrow colour=neutral; |U|=streamlines/colorbar"
    ),
    "arrow_low_speed_cutoff_mps": (
        float(0.02 * builtins.max(u_free, 1.0e-12))
        if mode == "steady_particles" else None
    ),
    "temporal_sampling_warning": (
        "low-frame QA only; particle transport motion is under-sampled below 33 frames"
        if mode == "steady_particles" and frame_count < 33 else None
    ),
    "display_clipping": (
        "hide particles whose age is outside each path's actual IntegrationTime range"
        if mode == "steady_particles" else None
    ),
    "phase_strategy": (
        "shared elapsed time; each path interpolated by actual IntegrationTime"
        if mode == "steady_particles" else None
    ),
    "integration_method": (
        "StreamTracer IntegrationTime interpolation"
        if mode == "steady_particles" else None
    ),
    "camera_motion": mode == "steady_orbit",
}
with open(os.path.join(output_dir, "animation_metadata.json"), "w", encoding="utf-8") as metadata_file:
    json.dump(metadata, metadata_file, ensure_ascii=False, indent=2)

print(f"[animation] rendered {frame_count} {mode} frames -> {output_dir}")
