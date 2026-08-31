# -*- coding: utf-8 -*-
"""Export the actual OpenFOAM U field and a decimated vehicle mesh to JSON.

This script is intentionally run by ``pvpython``.  The regular Python process
does not guess or synthesize a velocity field; it only turns ParaView's
``StreamTracer`` output into a browser-friendly, self-contained dataset.

Usage:
    pvpython export_streamline_data.py CASE UFREE OUTPUT_JSON
"""
import json
import math
import os
import sys

from velocity_sampling import (
    SAMPLING_METHOD, point_field_speed_max, prepare_velocity_sampling,
    preserved_sample_indices, validate_sampled_speed,
)

import vtk
from paraview import servermanager
from paraview.simple import (
    CellDatatoPointData,
    GetAnimationScene,
    OpenFOAMReader,
    Plane,
    STLReader,
    StreamTracerWithCustomSource,
)


def setp(obj, keys, value):
    for key in keys:
        try:
            setattr(obj, key, value)
            return True
        except Exception:
            continue
    return False


def incoming_yz_seed(domain_bounds, vehicle_bounds, columns=15, rows=11):
    domain = tuple(float(value) for value in domain_bounds)
    vehicle = tuple(float(value) for value in vehicle_bounds)
    if len(domain) != 6 or len(vehicle) != 6:
        raise ValueError("domain and vehicle bounds must contain six values")
    if any(not math.isfinite(value) for value in domain + vehicle):
        raise ValueError("domain and vehicle bounds must be finite")
    dx0, dx1, dy0, dy1, dz0, dz1 = domain
    vx0, vx1, vy0, vy1, vz0, vz1 = vehicle
    length = vx1 - vx0
    width = vy1 - vy0
    height = vz1 - vz0
    if min(length, width, height) <= 0 or dx0 >= dx1 or dy0 >= dy1 or dz0 >= dz1:
        raise ValueError("invalid domain or vehicle bounds")
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


def find_stl(case):
    for candidate in (
        os.path.join(case, "..", "geometry", "model.stl"),
        os.path.join(case, "constant", "triSurface", "body.stl"),
    ):
        if os.path.exists(candidate):
            return os.path.abspath(candidate)
    raise SystemExit("vehicle STL not found")


def finite_vector(values):
    vector = [float(value) for value in values]
    if len(vector) != 3 or any(not math.isfinite(value) for value in vector):
        raise ValueError("non-finite 3-D vector in ParaView output")
    return vector


def decimated_mesh(polydata, target_reduction=0.86):
    """Return JSON-ready triangle arrays while bounding browser payload size."""
    triangle_filter = vtk.vtkTriangleFilter()
    triangle_filter.SetInputData(polydata)
    triangle_filter.Update()
    # STL readers may expose every triangle with duplicated point records.
    # Merge coincident points before decimation so Plotly receives a connected
    # surface instead of long cross-triangle facets.
    cleaner = vtk.vtkCleanPolyData()
    cleaner.SetInputData(triangle_filter.GetOutput())
    cleaner.SetTolerance(1.0e-9)
    cleaner.Update()
    source = cleaner.GetOutput()
    decimator = vtk.vtkQuadricDecimation()
    decimator.SetInputData(source)
    decimator.SetTargetReduction(float(target_reduction))
    decimator.Update()
    mesh = decimator.GetOutput()
    if mesh is None or mesh.GetNumberOfPoints() == 0 or mesh.GetNumberOfCells() == 0:
        mesh = source
        reduction = 0.0
    else:
        reduction = 1.0 - mesh.GetNumberOfCells() / max(source.GetNumberOfCells(), 1)
    vertices = [
        [float(value) for value in mesh.GetPoint(index)]
        for index in range(mesh.GetNumberOfPoints())
    ]
    faces = []
    ids = vtk.vtkIdList()
    polys = mesh.GetPolys()
    polys.InitTraversal()
    while polys.GetNextCell(ids):
        if ids.GetNumberOfIds() != 3:
            continue
        faces.append([int(ids.GetId(index)) for index in range(3)])
    if not vertices or not faces:
        raise ValueError("vehicle STL produced no triangle mesh")
    return {
        "vertices": vertices,
        "faces": faces,
        "source_faces": int(source.GetNumberOfCells()),
        "display_faces": len(faces),
        "target_reduction": float(target_reduction),
        "actual_reduction": float(reduction),
    }


def sampled_path(data, cell_index, max_samples=140):
    integration = data.GetPointData().GetArray("IntegrationTime")
    vectors = data.GetPointData().GetArray("U")
    if integration is None or vectors is None:
        raise ValueError("StreamTracer output requires IntegrationTime and U")
    cell = data.GetCell(cell_index)
    ids = cell.GetPointIds()
    raw = []
    for point_index in range(ids.GetNumberOfIds()):
        point_id = ids.GetId(point_index)
        time_value = float(integration.GetTuple1(point_id))
        position = finite_vector(data.GetPoint(point_id))
        velocity = finite_vector(vectors.GetTuple(point_id))
        if not math.isfinite(time_value):
            raise ValueError("non-finite IntegrationTime in StreamTracer output")
        raw.append({
            "time": time_value,
            "position": position,
            "velocity": velocity,
        })
    if len(raw) < 2 or any(
        right["time"] <= left["time"]
        for left, right in zip(raw, raw[1:])
    ):
        return None
    if len(raw) <= max_samples:
        return raw
    selected = preserved_sample_indices([
        math.sqrt(sum(value * value for value in sample["velocity"]))
        for sample in raw
    ], max_samples)
    return [raw[index] for index in selected]


if len(sys.argv) != 4:
    raise SystemExit("usage: export_streamline_data.py CASE UFREE OUTPUT_JSON")

case = os.path.abspath(sys.argv[1])
u_free = float(sys.argv[2])
output_json = os.path.abspath(sys.argv[3])
if not math.isfinite(u_free) or u_free <= 0:
    raise SystemExit("UFREE must be finite and positive")
foam = os.path.join(case, "case.foam")
if not os.path.exists(foam):
    open(foam, "w").close()

body = STLReader(FileNames=[find_stl(case)])
body.UpdatePipeline()
body_bounds = body.GetDataInformation().GetBounds()
if not body_bounds or body_bounds[0] >= body_bounds[1]:
    raise SystemExit("empty vehicle STL")
x0, x1, y0, y1, z0, z1 = [float(value) for value in body_bounds]
length = x1 - x0

volume = OpenFOAMReader(FileName=foam)
volume.UpdatePipeline()
times = [float(value) for value in list(volume.TimestepValues or []) if float(value) > 0]
if not times:
    raise SystemExit("no non-zero OpenFOAM time available")
scene = GetAnimationScene()
scene.AnimationTime = times[-1]
volume.UpdatePipeline(times[-1])
c2p = CellDatatoPointData(Input=volume)
setp(c2p, ("ProcessAllArrays",), 1)
c2p.UpdatePipeline(times[-1])
flow_field = prepare_velocity_sampling(c2p, times[-1])
source_u_max = point_field_speed_max(flow_field)
domain_bounds = c2p.GetDataInformation().GetBounds()
seed_window = incoming_yz_seed(domain_bounds, body_bounds)
seed = Plane()
seed.Origin = [seed_window["x"], seed_window["y_min"], seed_window["z_min"]]
seed.Point1 = [seed_window["x"], seed_window["y_max"], seed_window["z_min"]]
seed.Point2 = [seed_window["x"], seed_window["y_min"], seed_window["z_max"]]
seed.XResolution = seed_window["x_resolution"]
seed.YResolution = seed_window["y_resolution"]
seed.UpdatePipeline()
tracer = StreamTracerWithCustomSource(Input=flow_field, SeedSource=seed)
setp(tracer, ("Vectors", "vectors"), ("POINTS", "U"))
setp(tracer, ("IntegrationDirection",), "FORWARD")
setp(tracer, ("InterpolatorType",), "Interpolator with Cell Locator")
setp(tracer, ("MaximumSteps", "MaximumNumberOfSteps"), 8000)
setp(tracer, ("MaximumStreamlineLength",), 8.0 * length)
setp(tracer, ("TerminalSpeed",), 1.0e-3)
tracer.UpdatePipeline()
stream_data = servermanager.Fetch(tracer)
if stream_data is None or stream_data.GetNumberOfPoints() == 0:
    raise SystemExit("StreamTracer returned no points")
raw_vectors = stream_data.GetPointData().GetArray("U")
if raw_vectors is None:
    raise SystemExit("StreamTracer returned no U vectors")
raw_speeds = [
    math.sqrt(sum(value * value for value in finite_vector(raw_vectors.GetTuple(i))))
    for i in range(stream_data.GetNumberOfPoints())
]
validate_sampled_speed(max(raw_speeds), source_u_max)
paths = []
for cell_index in range(stream_data.GetNumberOfCells()):
    path = sampled_path(stream_data, cell_index)
    if path is not None:
        paths.append(path)
if not paths:
    raise SystemExit("StreamTracer returned no usable IntegrationTime paths")

body_data = servermanager.Fetch(body)
mesh = decimated_mesh(body_data)
speed_values = [
    math.sqrt(sum(value * value for value in sample["velocity"]))
    for path in paths for sample in path
]
positive_speed_values = [value for value in speed_values if value > 0.0]
if not positive_speed_values:
    raise SystemExit("StreamTracer returned no positive U samples")
u_max = max(speed_values)
u_min = min(positive_speed_values)
transport_window = 4.0 * length / max(u_free, 1.0e-12)
payload = {
    "schema_version": 1,
    "case": case,
    "source_field": "U",
    "interpolation": SAMPLING_METHOD,
    "source_point_speed_max_mps": source_u_max,
    "full_resolution_streamline_speed_max_mps": max(raw_speeds),
    "source_field_time": float(times[-1]),
    "source_field_time_note": "steady OpenFOAM field time/iteration label",
    "u_free_mps": float(u_free),
    # The colour range must follow the sampled CFD field.  ``u_free`` is kept
    # separately for tracer transport timing and must not inflate the scale.
    "u_max_mps": float(1.08 * u_max),
    "sampled_u_min_mps": float(u_min),
    "sampled_u_max_mps": float(u_max),
    "transport_window_s": float(transport_window),
    "seed_plane": seed_window,
    "streamline_count": len(paths),
    "streamline_sample_limit": 140,
    "body": mesh,
    "streamlines": paths,
}
os.makedirs(os.path.dirname(output_json), exist_ok=True)
with open(output_json, "w", encoding="utf-8") as handle:
    json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
print(
    "[interactive] exported %d paths, %d/%d body faces -> %s"
    % (len(paths), mesh["display_faces"], mesh["source_faces"], output_json)
)
