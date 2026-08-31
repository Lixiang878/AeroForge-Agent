"""Traceable access and quality gates for native DrivAerNet++ meshes.

The GitHub repository contains code, metadata, and design splits; the native
STL archive is distributed separately.  This adapter therefore never guesses a
mesh from an ID and never downloads the multi-terabyte dataset.  A selected
local STL must pass the same finite/single-component/watertight gate before it
is handed to the CFD case builder.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import re
import subprocess
from pathlib import Path
from typing import Any

DRIVAERNETPP_REPO_URL = "https://github.com/Mohamedelrefaie/DrivAerNet.git"
DRIVAERNETPP_DATASET_DOI = "doi:10.7910/DVN/OYU2FG"
DRIVAERNETPP_LICENSE = "CC BY-NC 4.0"

__all__ = [
    "DRIVAERNETPP_DATASET_DOI",
    "DRIVAERNETPP_LICENSE",
    "DRIVAERNETPP_REPO_URL",
    "discover_native_stl",
    "inspect_drivaernet_repo",
    "validate_native_stl",
]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_ids(path: Path) -> list[str]:
    if not path.exists():
        return []
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")]


def inspect_drivaernet_repo(repo_dir: str | Path) -> dict[str, Any]:
    """Inspect a local official repository clone without fetching the dataset."""
    root = Path(repo_dir).resolve()
    required = {
        "readme": root / "README.md",
        "license": root / "LICENSE",
        "parametric_csv": root / "ParametricModels" / "DrivAerNet_ParametricData.csv",
        "train_split": root / "train_val_test_splits" / "train_design_ids.txt",
        "val_split": root / "train_val_test_splits" / "val_design_ids.txt",
        "test_split": root / "train_val_test_splits" / "test_design_ids.txt",
    }
    missing = [name for name, path in required.items() if not path.is_file()]
    errors: list[str] = []
    design_ids: list[str] = []
    readme_declared_design_count = None
    if not root.is_dir():
        errors.append(f"repository directory does not exist: {root}")
    if missing:
        errors.append("missing official repository files: " + ", ".join(missing))
    if required["readme"].is_file():
        readme = required["readme"].read_text(encoding="utf-8", errors="replace")
        if "DrivAerNet" not in readme:
            errors.append("README.md does not identify DrivAerNet")
        if "CC BY-NC 4.0" not in readme:
            errors.append("README.md does not identify the DrivAerNet++ dataset license")
        match = re.search(r"(\d[\d,]*)\s+diverse car designs", readme, flags=re.IGNORECASE)
        if match:
            readme_declared_design_count = int(match.group(1).replace(",", ""))
    if required["license"].is_file():
        # The repository LICENSE is the MIT license for code.  The dataset's
        # CC BY-NC terms are declared in README.md, so do not conflate them.
        required["license"].read_text(encoding="utf-8", errors="replace")
    if required["parametric_csv"].is_file():
        try:
            with required["parametric_csv"].open(newline="", encoding="utf-8-sig") as stream:
                reader = csv.DictReader(stream)
                for row in reader:
                    value = (row.get("Experiment") or "").strip()
                    if value:
                        design_ids.append(value)
        except (OSError, csv.Error) as exc:
            errors.append(f"cannot parse parametric CSV: {exc}")
    split_counts = {
        "train": len(_read_ids(required["train_split"])),
        "val": len(_read_ids(required["val_split"])),
        "test": len(_read_ids(required["test_split"])),
    }
    split_id_count = sum(split_counts.values())
    audit_warnings: list[str] = []
    if design_ids and split_id_count and split_id_count != len(set(design_ids)):
        audit_warnings.append(
            f"parameter CSV has {len(set(design_ids))} IDs but splits list {split_id_count} IDs"
        )
    declared_design_count = None
    metadata_path = root / "mlcroissant" / "DrivAerNet_metadata.json"
    if metadata_path.is_file():
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            description = str(metadata.get("description") or "")
            match = re.search(r"(\d[\d,]*)\s+diverse car designs", description)
            if match:
                declared_design_count = int(match.group(1).replace(",", ""))
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            audit_warnings.append("Croissant metadata could not be parsed")
    if (readme_declared_design_count is not None and declared_design_count is not None
            and readme_declared_design_count != declared_design_count):
        audit_warnings.append(
            "README declares "
            f"{readme_declared_design_count} designs but Croissant metadata declares "
            f"{declared_design_count}"
        )
    commit = None
    if root.is_dir():
        try:
            completed = subprocess.run(
                ["git", "-C", str(root), "rev-parse", "HEAD"],
                check=False, capture_output=True, text=True, timeout=15,
                encoding="utf-8", errors="replace",
            )
            if completed.returncode == 0:
                commit = completed.stdout.strip() or None
        except (OSError, subprocess.SubprocessError):
            commit = None
    unique_ids = list(dict.fromkeys(design_ids))
    return {
        "status": "valid" if not errors else "invalid",
        "repository": str(root),
        "repository_url": DRIVAERNETPP_REPO_URL,
        "repository_commit": commit,
        "dataset_license": DRIVAERNETPP_LICENSE,
        "dataset_persistent_id": DRIVAERNETPP_DATASET_DOI,
        "required_files": {name: str(path) for name, path in required.items()},
        "missing_files": missing,
        "errors": errors,
        "design_count": len(unique_ids),
        "split_id_count": split_id_count,
        "readme_declared_design_count": readme_declared_design_count,
        "declared_design_count": declared_design_count,
        "sample_design_ids": unique_ids[:5],
        "split_counts": split_counts,
        "audit_warnings": audit_warnings,
        "bulk_download_performed": False,
        "native_stl_required": True,
        "note": (
            "GitHub clone is metadata/code only; select a licensed native STL from "
            "the Dataverse/Globus dataset and validate it before CFD."
        ),
    }


def discover_native_stl(dataset_dir: str | Path, design_id: str) -> Path:
    """Find one exact design-ID STL in a local DrivAerNet++ data subset."""
    root = Path(dataset_dir).resolve()
    identifier = str(design_id).strip()
    if not identifier or Path(identifier).name != identifier:
        raise ValueError("design_id must be a non-empty file-stem-like identifier")
    if not root.is_dir():
        raise FileNotFoundError(
            f"native STL directory does not exist: {root}; download only a selected "
            "design/subset to the E: workspace, not the full dataset"
        )
    direct_candidates = [root / f"{identifier}.stl", root / f"{identifier}.STL"]
    for candidate in direct_candidates:
        if candidate.is_file():
            return candidate.resolve()
    wanted = identifier.casefold()
    for candidate in root.rglob("*"):
        if candidate.is_file() and candidate.suffix.casefold() == ".stl" \
                and candidate.stem.casefold() == wanted:
            return candidate.resolve()
    raise FileNotFoundError(
        f"selected design {identifier!r} has no native STL under {root}; "
        "download only the selected design/subset from Harvard Dataverse/Globus "
        "and keep it on the E: workspace"
    )


def validate_native_stl(path: str | Path, *, require_watertight: bool = True,
                        require_single_component: bool = True) -> dict[str, Any]:
    """Return a JSON-ready CFD quality gate for one local native STL.

    Invalid assets return ``status=failed`` instead of being silently repaired.
    This is intentional: a visual OBJ/GLB or a voxel reconstruction must not be
    promoted to an engineering mesh by this adapter.
    """
    mesh_path = Path(path).resolve()
    result: dict[str, Any] = {
        "status": "failed",
        "path": str(mesh_path),
        "cfd_ready": False,
        "errors": [],
    }
    if not mesh_path.is_file():
        result["errors"] = [f"STL file does not exist: {mesh_path}"]
        return result
    if mesh_path.suffix.casefold() != ".stl":
        result["errors"] = ["native CFD geometry must use the .stl extension"]
        return result
    result["bytes"] = mesh_path.stat().st_size
    result["sha256"] = _sha256(mesh_path)
    try:
        import numpy as np
        from .mesh_compat import import_trimesh
        trimesh = import_trimesh()
    except ImportError as exc:  # pragma: no cover - optional dependency
        result["errors"] = [f"native STL validation requires trimesh/numpy: {exc}"]
        return result
    try:
        loaded = trimesh.load(mesh_path, force="scene", process=False)
        geometries = list(getattr(loaded, "geometry", {}).values())
        if isinstance(loaded, trimesh.Trimesh):
            geometries = [loaded]
        geometries = [geometry for geometry in geometries
                      if len(getattr(geometry, "vertices", [])) and len(getattr(geometry, "faces", []))]
        if not geometries:
            raise ValueError("no triangles found")
        mesh = trimesh.util.concatenate(geometries) if len(geometries) > 1 else geometries[0]
        # ASCII/binary STL commonly repeats the same vertex for every face.
        # Weld only exact in-memory duplicates for topology checks; the source
        # file itself is never rewritten.
        mesh = mesh.copy()
        mesh.merge_vertices()
        mesh.remove_unreferenced_vertices()
        finite_vertices = bool(np.isfinite(mesh.vertices).all())
        finite_faces = bool(np.isfinite(mesh.faces).all())
        if not finite_vertices or not finite_faces:
            raise ValueError("vertices or faces contain non-finite values")
        face_count = int(len(mesh.faces))
        vertex_count = int(len(mesh.vertices))
        if face_count < 4:
            raise ValueError("STL contains fewer than four triangles")
        extents = [float(value) for value in mesh.extents]
        if any(not math.isfinite(value) or value <= 0.0 for value in extents):
            raise ValueError("STL bounds are empty or non-finite")
        components = int(len(mesh.split(only_watertight=False)))
        watertight = bool(mesh.is_watertight)
        result.update({
            "vertices": vertex_count,
            "faces": face_count,
            "components": components,
            "watertight": watertight,
            "bounds": [[float(value) for value in row] for row in mesh.bounds],
            "extents": extents,
        })
        errors: list[str] = []
        if require_single_component and components != 1:
            errors.append(f"expected one connected component, got {components}")
        if require_watertight and not watertight:
            errors.append("surface is not watertight")
        result["errors"] = errors
        result["status"] = "passed" if not errors else "failed"
        result["cfd_ready"] = not errors
    except Exception as exc:  # trimesh parsers expose several exception types
        result["errors"] = [f"STL quality check failed: {exc}"]
    return result
