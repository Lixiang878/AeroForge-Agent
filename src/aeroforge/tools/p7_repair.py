"""Conservative, auditable surface repair for the downloaded XPeng P7 asset.

This module intentionally does not pretend that a decorative OBJ is an
engineering CAD model.  It creates a separate, watertight *candidate* by
voxel filling and marching-cubes reconstruction.  Units and axes remain
unknown, the source remains untouched, and callers must run a fresh
``surfaceCheck``/``checkMesh`` before any CFD use.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

__all__ = ["repair_p7_surface"]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _finite_mesh(source: Path):
    try:
        from .mesh_compat import import_trimesh
        trimesh = import_trimesh()
        import numpy as np
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise RuntimeError("P7 repair requires the optional trimesh dependency") from exc

    loaded = trimesh.load(source, force="scene", process=False)
    if isinstance(loaded, trimesh.Trimesh):
        geometries = [loaded]
    else:
        geometries = list(getattr(loaded, "geometry", {}).values())
    meshes = []
    for geometry in geometries:
        vertices = geometry.vertices
        faces = geometry.faces
        if len(vertices) == 0 or len(faces) == 0:
            continue
        finite_vertices = np.isfinite(vertices).all(axis=1)
        if not bool(finite_vertices.all()):
            # Re-index faces to the finite vertex subset rather than allowing
            # a single invalid material group to poison the complete scene.
            remap = -np.ones(len(vertices), dtype="int64")
            remap[finite_vertices] = np.arange(int(finite_vertices.sum()))
            finite_faces = faces[finite_vertices[faces].all(axis=1)]
            finite_faces = remap[finite_faces]
            geometry = trimesh.Trimesh(
                vertices=vertices[finite_vertices], faces=finite_faces,
                process=False,
            )
        else:
            geometry = geometry.copy()
        # Recent trimesh releases expose nondegenerate_faces as a mask rather
        # than the removed remove_degenerate_faces convenience method.
        try:
            geometry.update_faces(geometry.nondegenerate_faces())
        except AttributeError:  # pragma: no cover - older trimesh
            geometry.remove_degenerate_faces()
        geometry.remove_unreferenced_vertices()
        geometry.merge_vertices()
        if len(geometry.faces):
            meshes.append(geometry)
    if not meshes:
        raise ValueError(f"no finite triangles found in {source}")
    return trimesh.util.concatenate(meshes)


def repair_p7_surface(source_path: str | Path, destination_stl: str | Path,
                      manifest_path: str | Path | None = None,
                      *, pitch: float = 0.10) -> dict:
    """Write a separate watertight P7 candidate using voxel fill.

    ``pitch`` is expressed in the source model's unknown coordinate units.  A
    0.10 default was selected for this asset because it closes the many small
    decorative gaps while retaining the vehicle silhouette.  The result is
    marked non-CFD-ready by design; this function is a repair aid, not a mesh
    acceptance gate.
    """
    source = Path(source_path).resolve()
    destination = Path(destination_stl).resolve()
    if not math.isfinite(float(pitch)) or float(pitch) <= 0.0:
        raise ValueError("pitch must be finite and positive")
    if source == destination:
        raise ValueError("source and destination must be separate files")
    if not source.exists():
        raise FileNotFoundError(source)
    if destination.suffix.lower() != ".stl":
        raise ValueError("destination must use the .stl extension")

    from .mesh_compat import import_trimesh
    trimesh = import_trimesh()

    source_mesh = _finite_mesh(source)
    voxel_grid = source_mesh.voxelized(float(pitch))
    filled_grid = voxel_grid.fill()
    repaired = filled_grid.marching_cubes
    # marching_cubes returns vertices in voxel-index coordinates; restore the
    # source model's coordinate frame before exporting the candidate STL.
    repaired.apply_transform(filled_grid.transform)
    try:
        repaired.update_faces(repaired.nondegenerate_faces())
    except AttributeError:  # pragma: no cover - older trimesh
        repaired.remove_degenerate_faces()
    repaired.remove_unreferenced_vertices()
    repaired.merge_vertices()
    repaired.fix_normals()
    component_count = len(repaired.split(only_watertight=False))
    watertight = bool(repaired.is_watertight)
    if not watertight or component_count != 1:
        raise RuntimeError(
            "voxel reconstruction did not produce one watertight component "
            f"(watertight={watertight}, components={component_count})"
        )

    destination.parent.mkdir(parents=True, exist_ok=True)
    repaired.export(destination, file_type="stl")
    record_path = Path(manifest_path).resolve() if manifest_path else destination.with_suffix(".json")
    record_path.parent.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema_version": 1,
        "asset": "2022 XPeng P7",
        "source": str(source),
        "source_sha256": _sha256(source),
        "output": str(destination),
        "output_sha256": _sha256(destination),
        "method": "voxel_fill_marching_cubes",
        "pitch": float(pitch),
        "source_units": "unknown",
        "source_forward_axis": "unknown",
        "source_is_untouched": True,
        "approximate_reconstruction": True,
        "watertight": watertight,
        "components": component_count,
        "vertices": int(len(repaired.vertices)),
        "faces": int(len(repaired.faces)),
        "cfd_ready": False,
        "next_gate": [
            "confirm units and +X forward axis",
            "run surfaceCheck and inspect normals/self-intersections",
            "build an independent P7 case and verify mesh quality",
        ],
    }
    record_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "status": "completed",
        "source": source,
        "output": destination,
        "manifest": record_path,
        "approximate_reconstruction": True,
        "watertight": watertight,
        "components": component_count,
        "vertices": int(len(repaired.vertices)),
        "faces": int(len(repaired.faces)),
        "cfd_ready": False,
    }
