# -*- coding: utf-8 -*-
"""Create a bounded, geometry-only preview payload from an OBJ file.

Non-finite OBJ cells are dropped explicitly.  The result is for visual QA and
is never a CFD wall surface; callers must keep the original OBJ/MTL and audit
the repaired geometry separately.

Usage:
    pvpython export_obj_preview.py MODEL.obj OUTPUT.json [TARGET_REDUCTION]
"""
import json
import math
import os
import sys

import vtk


def finite_clean_mesh(raw):
    points = vtk.vtkPoints()
    polys = vtk.vtkCellArray()
    point_map = {}
    for cell_index in range(raw.GetNumberOfCells()):
        cell = raw.GetCell(cell_index)
        ids = cell.GetPointIds()
        if ids.GetNumberOfIds() < 3:
            continue
        coordinates = [raw.GetPoint(ids.GetId(i)) for i in range(ids.GetNumberOfIds())]
        if any(not math.isfinite(value) for point in coordinates for value in point):
            continue
        for start in range(1, ids.GetNumberOfIds() - 1):
            triangle = [ids.GetId(0), ids.GetId(start), ids.GetId(start + 1)]
            output_ids = []
            for original_id in triangle:
                if original_id not in point_map:
                    point_map[original_id] = points.InsertNextPoint(raw.GetPoint(original_id))
                output_ids.append(point_map[original_id])
            polys.InsertNextCell(3)
            for output_id in output_ids:
                polys.InsertCellPoint(output_id)
    clean = vtk.vtkPolyData()
    clean.SetPoints(points)
    clean.SetPolys(polys)
    return clean


def mesh_payload(clean, target_reduction):
    decimator = vtk.vtkQuadricDecimation()
    decimator.SetInputData(clean)
    decimator.SetTargetReduction(float(target_reduction))
    decimator.Update()
    mesh = decimator.GetOutput()
    if mesh is None or mesh.GetNumberOfPoints() == 0 or mesh.GetNumberOfCells() == 0:
        mesh = clean
    vertices = [
        [float(value) for value in mesh.GetPoint(index)]
        for index in range(mesh.GetNumberOfPoints())
    ]
    faces = []
    ids = vtk.vtkIdList()
    mesh.GetPolys().InitTraversal()
    while mesh.GetPolys().GetNextCell(ids):
        if ids.GetNumberOfIds() == 3:
            faces.append([int(ids.GetId(i)) for i in range(3)])
    if not vertices or not faces:
        raise ValueError("OBJ preview contains no finite triangle cells")
    return {
        "vertices": vertices,
        "faces": faces,
        "display_faces": len(faces),
        "target_reduction": float(target_reduction),
        "bounds": [float(value) for value in mesh.GetBounds()],
    }


if len(sys.argv) not in (3, 4):
    raise SystemExit("usage: export_obj_preview.py MODEL.obj OUTPUT.json [TARGET_REDUCTION]")
source = os.path.abspath(sys.argv[1])
output = os.path.abspath(sys.argv[2])
target_reduction = float(sys.argv[3]) if len(sys.argv) == 4 else 0.78
if not 0.0 <= target_reduction < 1.0:
    raise SystemExit("TARGET_REDUCTION must be in [0, 1)")
reader = vtk.vtkOBJReader()
reader.SetFileName(source)
reader.Update()
raw = reader.GetOutput()
clean = finite_clean_mesh(raw)
payload = mesh_payload(clean, target_reduction)
payload.update({
    "source": source,
    "raw_points": int(raw.GetNumberOfPoints()),
    "raw_cells": int(raw.GetNumberOfCells()),
    "finite_cells": int(clean.GetNumberOfCells()),
})
os.makedirs(os.path.dirname(output), exist_ok=True)
with open(output, "w", encoding="utf-8") as handle:
    json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
print(
    "[obj-preview] %d raw cells -> %d finite display faces -> %s"
    % (payload["raw_cells"], payload["display_faces"], output)
)
