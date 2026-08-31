# -*- coding: utf-8 -*-
"""Render three deterministic, field-grounded external-aerodynamics views.

The vehicle is rendered as a neutral material while a finite near-body YZ
seed-plane's streamlines are coloured by the *actual* OpenFOAM velocity field.
Direction arrows use the same plane and a fixed length. No synthetic flow
field is generated.

Usage:
    pvpython streamline_hd.py <case_dir> [u_free_mps]
"""
import os
import sys
import math
import builtins
import json

from velocity_sampling import (
    SAMPLING_METHOD, point_field_speed_max, prepare_velocity_sampling,
    validate_sampled_speed,
)

from paraview import servermanager  # noqa: E402

os.environ.setdefault("PARAVIEW_USE_VISRTX", "0")

CASE = sys.argv[1] if len(sys.argv) > 1 else None
UFREE = float(sys.argv[2]) if len(sys.argv) > 2 else None
BODY_COLOUR = ([float(value) for value in sys.argv[3].split(",")]
               if len(sys.argv) > 3 else [0.065, 0.16, 0.28])
if not CASE:
    raise SystemExit("usage: streamline_hd.py <case_dir> [u_free_mps]")
if len(BODY_COLOUR) != 3 or any(value < 0.0 or value > 1.0 for value in BODY_COLOUR):
    raise SystemExit("vehicle colour must contain three RGB values in [0, 1]")

from paraview.simple import (  # noqa: E402
    CellDatatoPointData,
    ColorBy,
    CreateView,
    GetAnimationScene,
    GetColorTransferFunction,
    GetScalarBar,
    Glyph,
    OpenFOAMReader,
    Plane,
    Render,
    ResampleWithDataset,
    SaveScreenshot,
    SetActiveView,
    Show,
    STLReader,
    StreamTracerWithCustomSource,
    Tube,
)


def setp(obj, keys, value):
    """Set the first property name supported by the installed ParaView."""
    for key in keys:
        try:
            setattr(obj, key, value)
            return True
        except Exception:
            continue
    return False


def find_stl(case):
    candidates = (
        os.path.join(case, "..", "geometry", "model.stl"),
        os.path.join(case, "constant", "triSurface", "body.stl"),
    )
    for candidate in candidates:
        if os.path.exists(candidate):
            return os.path.abspath(candidate)
    raise SystemExit("[hd] vehicle STL not found")


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


def static_velocity_color_max(sampled_u_max):
    """Choose a data-driven colour limit from finite tracer samples.

    The inlet speed is a physical boundary-condition hint, not a colour
    limit.  Using it here can expand the lookup table far beyond the values
    actually present on the traced streamlines and make the whole field look
    monochromatic.  Keep a small headroom above the observed maximum so the
    endpoint is not clipped, while retaining the source units (m/s).
    """
    sampled = float(sampled_u_max)
    if not math.isfinite(sampled) or sampled <= 0.0:
        raise ValueError("sampled StreamTracer U maximum must be finite and positive")
    return 1.08 * sampled


def velocity_colour_scale_mode(sampled_u_min, colour_u_max):
    """Use log10 only when a positive speed range is genuinely wide."""
    lower = float(sampled_u_min)
    upper = float(colour_u_max)
    if not math.isfinite(lower) or lower < 0.0:
        raise ValueError("sampled StreamTracer speed minimum must be non-negative")
    if not math.isfinite(upper) or upper <= 0.0 or upper < lower:
        raise ValueError("colour speed limits must be finite and ordered")
    return "log10" if lower > 0.0 and upper / lower >= 8.0 else "linear"


def fetched_streamline_velocity_range(tracers):
    """Fetch actual StreamTracer U arrays and return their finite speed range."""
    if not tracers:
        raise ValueError("no StreamTracer available for static U colour scale")
    minimum = None
    maximum = None
    for tracer in tracers:
        data = servermanager.Fetch(tracer)
        if data is None or not data.GetPoints():
            raise ValueError("StreamTracer output is empty; cannot sample U")
        vectors = data.GetPointData().GetArray("U")
        if vectors is None:
            raise ValueError("StreamTracer output is missing the U velocity array")
        for point_id in range(data.GetNumberOfPoints()):
            vector = tuple(float(value) for value in vectors.GetTuple(point_id))
            if len(vector) != 3 or any(not math.isfinite(value) for value in vector):
                raise ValueError("StreamTracer U samples must be finite 3-D vectors")
            speed = math.sqrt(builtins.sum(value * value for value in vector))
            minimum = speed if minimum is None else builtins.min(minimum, speed)
            maximum = speed if maximum is None else builtins.max(maximum, speed)
    if (minimum is None or maximum is None or not math.isfinite(minimum)
            or not math.isfinite(maximum) or maximum <= 0.0):
        raise ValueError("StreamTracer U samples contain no positive finite speed")
    return minimum, maximum


def fetched_streamline_velocity_max(tracers):
    """Backward-compatible maximum-speed helper."""
    return fetched_streamline_velocity_range(tracers)[1]


def incoming_yz_seed(domain_bounds, vehicle_bounds, columns=15, rows=11):
    """Return a finite near-body YZ plane, not the full-domain inlet."""
    domain = tuple(float(value) for value in domain_bounds)
    vehicle = tuple(float(value) for value in vehicle_bounds)
    if len(domain) != 6 or len(vehicle) != 6:
        raise ValueError("domain and vehicle bounds must contain six values")
    if any(not math.isfinite(value) for value in domain + vehicle):
        raise ValueError("domain and vehicle bounds must be finite")
    dx0, dx1, dy0, dy1, dz0, dz1 = domain
    vx0, vx1, vy0, vy1, vz0, vz1 = vehicle
    length, width, height = vx1 - vx0, vy1 - vy0, vz1 - vz0
    if min(length, width, height) <= 0.0 or dx0 >= dx1 or dy0 >= dy1 or dz0 >= dz1:
        raise ValueError("invalid domain or vehicle bounds")
    if int(columns) < 1 or int(rows) < 1:
        raise ValueError("seed plane resolution must be positive")
    x = vx0 - 0.30 * length
    if not dx0 < x < dx1:
        raise ValueError("near-body seed plane does not intersect internalMesh")
    eps = max(1.0e-5, 1.0e-3 * height)
    y_min = max(dy0 + eps, vy0 - 0.20 * width)
    y_max = min(dy1 - eps, vy1 + 0.20 * width)
    z_min = max(dz0 + eps, vz0 - eps)
    z_max = min(dz1 - eps, vz1 + 0.60 * height)
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


case = os.path.abspath(CASE)
foam = os.path.join(case, "case.foam")
if not os.path.exists(foam):
    open(foam, "w").close()
stl_path = find_stl(case)
print("[hd] case:", case)

# Query VTK bounds instead of expanding a large STL into Python objects.
body = STLReader()
setp(body, ("FileName", "FileNames"), stl_path)
body.UpdatePipeline()
bounds = body.GetDataInformation().GetBounds()
if not bounds or bounds[0] > bounds[1]:
    raise SystemExit(f"[hd] invalid or empty STL: {stl_path}")
x0, x1, y0, y1, z0, z1 = bounds
length, width, height = x1 - x0, y1 - y0, z1 - z0
cx, cy = 0.5 * (x0 + x1), 0.5 * (y0 + y1)
print(f"[hd] body L={length:.3f} W={width:.3f} H={height:.3f}")

# Stream tracing and smooth plane colouring require point data. Select the
# final written time before updating the cell-to-point conversion.
volume = OpenFOAMReader(FileName=foam)
volume.UpdatePipeline()
scene = GetAnimationScene()
times = volume.TimestepValues
if times and len(times) > 1:
    scene.AnimationTime = times[-1]
    volume.UpdatePipeline(times[-1])

c2p = CellDatatoPointData(Input=volume)
setp(c2p, ("ProcessAllArrays",), 1)
c2p.UpdatePipeline(scene.AnimationTime)
flow_field = prepare_velocity_sampling(c2p, scene.AnimationTime)
source_u_max = point_field_speed_max(flow_field)
domain_bounds = c2p.GetDataInformation().GetBounds()
if not domain_bounds or domain_bounds[0] > domain_bounds[1]:
    raise SystemExit("[hd] OpenFOAM internal mesh is empty")
ground_z = domain_bounds[4] + max(1.0e-5, 2.0e-4 * height)
seed_window = incoming_yz_seed(domain_bounds, (x0, x1, y0, y1, z0, z1))
print("[hd] finite near-body YZ seed plane (not the full-domain inlet):", seed_window)

if UFREE is None or UFREE <= 0:
    UFREE = 40.0

view = CreateView("RenderView")
SetActiveView(view)
setp(view, ("Background", "background"), [0.965, 0.978, 0.990])
setp(view, ("Background2", "background2"), [0.82, 0.885, 0.94])
setp(view, ("UseColorPaletteForBackground",), 0)
setp(view, ("BackgroundColorMode",), "Gradient")
setp(view, ("OrientationAxesVisibility",), 0)
setp(view, ("UseFXAA",), 1)
setp(view, ("MultiSamples",), 8)
setp(view, ("UseDepthPeeling",), 1)
setp(view, ("MaximumNumberOfPeels",), 100)
setp(view, ("OcclusionRatio",), 0.01)
setp(view, ("UseSSAO",), 1)
setp(view, ("SSAORadius",), 0.055 * height)
setp(view, ("SSAOIntensity",), 0.65)
setp(view, ("ViewSize",), [2400, 1350])

# Neutral metallic body: scalar colours remain reserved for field data.
body_display = Show(body, view)
ColorBy(body_display, ("POINTS", ""))
setp(body_display, ("DiffuseColor", "diffuse_color"), BODY_COLOUR)
setp(body_display, ("Ambient", "ambient"), 0.24)
setp(body_display, ("Diffuse", "diffuse"), 0.80)
setp(body_display, ("Specular", "specular"), 0.55)
setp(body_display, ("SpecularPower", "specular_power"), 65.0)
if setp(body_display, ("Interpolation",), "PBR"):
    setp(body_display, ("Metallic",), 0.40)
    setp(body_display, ("Roughness",), 0.28)

# Finite ground patch avoids a full-domain opaque sheet.
ground = Plane()
ground.Origin = [x0 - 0.65 * length, y0 - 0.78 * width, ground_z]
ground.Point1 = [x1 + 1.55 * length, y0 - 0.78 * width, ground_z]
ground.Point2 = [x0 - 0.65 * length, y1 + 0.78 * width, ground_z]
ground.XResolution = 2
ground.YResolution = 2
ground_display = Show(ground, view)
setp(ground_display, ("DiffuseColor", "diffuse_color"), [0.70, 0.75, 0.80])
setp(ground_display, ("Ambient", "ambient"), 0.48)
setp(ground_display, ("Specular", "specular"), 0.10)


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


stream_tracers = []


def make_stream_tubes():
    tracer = StreamTracerWithCustomSource(Input=flow_field, SeedSource=incoming_seed_plane)
    # STLReader may leave its surface normals as ParaView's global active
    # vectors.  Select the actual CFD velocity explicitly for every tracer;
    # otherwise only whichever seed is created after ColorBy(U) is valid.
    setp(tracer, ("Vectors", "vectors"), ("POINTS", "U"))
    setp(tracer, ("IntegrationDirection",), "FORWARD")
    setp(tracer, ("InterpolatorType",), "Interpolator with Cell Locator")
    setp(tracer, ("MaximumSteps", "MaximumNumberOfSteps"), 8000)
    setp(tracer, ("MaximumStreamlineLength",), 8.0 * length)
    setp(tracer, ("TerminalSpeed", "terminal_speed"), 1.0e-3)
    tube = Tube(Input=tracer)
    setp(tube, ("Radius", "radius"), 0.0020 * min(width, height))
    setp(tube, ("NumberOfSides", "number_of_sides"), 6)
    display = Show(tube, view)
    colour_by_velocity(display)
    setp(display, ("Opacity", "opacity"), 0.72)
    setp(display, ("Ambient",), 1.0)
    setp(display, ("Diffuse",), 0.0)
    setp(display, ("Specular",), 0.0)
    stream_tracers.append(tracer)
    return display


stream_displays = (make_stream_tubes(),)

try:
    sampled_u_min, sampled_u_max = fetched_streamline_velocity_range(stream_tracers)
    validate_sampled_speed(sampled_u_max, source_u_max)
except ValueError as exc:
    raise SystemExit(f"[hd] cannot determine static U colour range: {exc}")
UMAX = static_velocity_color_max(sampled_u_max)
COLOUR_MODE = velocity_colour_scale_mode(sampled_u_min, UMAX)
COLOUR_MIN = sampled_u_min
print(f"[hd] sampled |U| range: {sampled_u_min:.6g} .. {sampled_u_max:.6g} m/s; "
      f"colour range: {COLOUR_MIN:.6g} .. {UMAX:.6g} m/s ({COLOUR_MODE})")

# Use the same finite incoming plane for sparse direction arrows.  The arrow
# length is fixed (no magnitude scaling); only colour encodes |U|.
seed_sampled = ResampleWithDataset(
    SourceDataArrays=flow_field, DestinationMesh=incoming_seed_plane)
seed_sampled.UpdatePipeline()
seed_arrows = Glyph(Input=seed_sampled, GlyphType="Arrow")
setp(seed_arrows, ("OrientationArray", "orientation_array"), ["POINTS", "U"])
setp(seed_arrows, ("ScaleArray", "scale_array"), ["POINTS", "No scale array"])
setp(seed_arrows, ("ScaleFactor", "scale_factor"), 0.10 * height)
setp(seed_arrows, ("GlyphMode", "glyph_mode"), "Every Nth Point")
setp(seed_arrows, ("Stride", "stride"), 4)
seed_arrows.UpdatePipeline()
arrow_display = Show(seed_arrows, view)
arrow_neutral_colour(arrow_display)
setp(arrow_display, ("Opacity", "opacity"), 0.95)

# One perceptually ordered colour scale for every field-bearing object.
lut = GetColorTransferFunction("U")
preset_applied = False
for preset in ("Viridis (matplotlib)", "Viridis", "Cividis", "Cividis (matplotlib)"):
    try:
        lut.ApplyPreset(preset, False)
        preset_applied = True
        break
    except Exception:
        continue
if not preset_applied:
    midpoint = (math.sqrt(COLOUR_MIN * UMAX)
                if COLOUR_MODE == "log10"
                else 0.50 * (COLOUR_MIN + UMAX))
    lut.RGBPoints = [
        COLOUR_MIN, 0.000, 0.135, 0.304,
        midpoint, 0.126, 0.553, 0.553,
        UMAX, 0.993, 0.906, 0.144,
    ]
lut.RescaleTransferFunction(COLOUR_MIN, UMAX)
setp(lut, ("UseLogScale", "use_log_scale"), int(COLOUR_MODE == "log10"))
setp(lut, ("AutomaticRescaleRangeMode",), "Never")
for display in stream_displays:
    setp(display, ("LookupTable",), lut)

bar = GetScalarBar(lut, view)
bar.Title = "Speed |U| (m/s)" + (" [log10]" if COLOUR_MODE == "log10" else "")
setp(bar, ("ComponentTitle", "component_title"), "")
setp(bar, ("Orientation",), "Horizontal")
setp(bar, ("WindowLocation",), "Any Location")
setp(bar, ("Position",), [0.54, 0.055])
setp(bar, ("ScalarBarLength",), 0.40)
setp(bar, ("ScalarBarThickness",), 22)
setp(bar, ("TitleFontSize",), 20)
setp(bar, ("LabelFontSize",), 17)
setp(bar, ("AutomaticLabelFormat",), 0)
setp(bar, ("LabelFormat",), "%.3g")
setp(bar, ("RangeLabelFormat",), "%.3g")
setp(bar, ("UseCustomLabels",), 1)
colourbar_labels = []
for i in range(5):
    raw_label = (COLOUR_MIN * (UMAX / COLOUR_MIN) ** (i / 4.0)
                 if COLOUR_MODE == "log10"
                 else COLOUR_MIN + (UMAX - COLOUR_MIN) * i / 4.0)
    # ParaView may bypass LabelFormat for CustomLabels, so store concise
    # three-significant-digit positions directly in the scalar bar.
    colourbar_labels.append(float("{:.3g}".format(raw_label)))
setp(bar, ("CustomLabels",), colourbar_labels)
setp(bar, ("AddRangeLabels",), 0)
setp(bar, ("TitleColor",), [0.08, 0.16, 0.24])
setp(bar, ("LabelColor",), [0.08, 0.16, 0.24])
setp(bar, ("DrawBackground",), 1)
setp(bar, ("BackgroundColor",), [0.965, 0.978, 0.990])
setp(bar, ("BackgroundOpacity",), 0.90)
setp(bar, ("DrawFrame",), 1)
bar.Visibility = 1


def save_shot(position, focal_point, filename):
    camera = view.GetActiveCamera()
    frame_scale = max(1.20 * height, 0.70 * length)
    # Set both the RenderView proxy properties and the VTK camera.  The proxy
    # is what ParaView reapplies on the first Render after a pipeline update;
    # setting only GetActiveCamera() lets that render silently ResetCamera().
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
    Render(view)
    output = os.path.join(case, "results", filename)
    os.makedirs(os.path.dirname(output), exist_ok=True)
    SaveScreenshot(output, view, ImageResolution=[2400, 1350],
                   TransparentBackground=0)
    print("[hd] saved:", output)


# The first render lets ParaView initialise the renderer.  Without this
# bootstrap render, ParaView 5.13 may reset the first user camera to include
# every streamline source, producing a tiny vehicle in the hero frame.
Render(view)

# The solver convention is flow from x-min to x-max.
save_shot(
    (cx - 1.28 * length, cy - 1.48 * width, z0 + 0.78 * height),
    (cx + 0.05 * length, cy, z0 + 0.43 * height),
    "streamline_hd_front.png",
)
save_shot(
    (cx + 1.40 * length, cy - 1.30 * width, z0 + 1.02 * height),
    (x1 + 0.36 * length, cy, z0 + 0.52 * height),
    "streamline_hd_wake.png",
)
save_shot(
    (cx + 0.12 * length, cy - 3.25 * width, z0 + 0.61 * height),
    (cx + 0.22 * length, cy, z0 + 0.46 * height),
    "streamline_hd_side.png",
)

with open(os.path.join(case, "results", "static_velocity_metadata.json"), "w", encoding="utf-8") as handle:
    json.dump({
        "source_field": "U", "source_field_time": float(scene.AnimationTime),
        "u_free_mps": UFREE, "interpolation": SAMPLING_METHOD,
        "source_point_speed_max_mps": source_u_max,
        "sampled_u_min_mps": sampled_u_min, "sampled_u_max_mps": sampled_u_max,
        "colour_scale_min_mps": COLOUR_MIN, "colour_scale_max_mps": UMAX,
        "colour_scale_mode": COLOUR_MODE, "colour_scale_title": bar.Title,
        "colour_scale_source": "full-resolution streamline U samples plus 8% headroom",
        "seed_plane": seed_window,
    }, handle, indent=2)
