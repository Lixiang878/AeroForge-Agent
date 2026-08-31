from pathlib import Path

import pytest


def test_p7_repair_builds_watertight_candidate_and_auditable_manifest(tmp_path):
    from aeroforge.tools.mesh_compat import import_trimesh
    trimesh = import_trimesh()
    from aeroforge.tools.p7_repair import repair_p7_surface

    source = tmp_path / "open_box.glb"
    box = trimesh.creation.box(extents=(2.0, 1.0, 0.6))
    # Deliberately remove two triangles: the repair must close a surface gap.
    box.update_faces([index for index in range(len(box.faces)) if index not in {0, 1}])
    box.remove_unreferenced_vertices()
    box.export(source)
    destination = tmp_path / "candidate.stl"
    manifest = tmp_path / "candidate.json"

    result = repair_p7_surface(source, destination, manifest, pitch=0.08)

    assert result["status"] == "completed"
    assert result["approximate_reconstruction"] is True
    assert result["cfd_ready"] is False
    assert result["watertight"] is True
    assert destination.exists() and destination.stat().st_size > 84
    assert manifest.exists()
    record = manifest.read_text(encoding="utf-8")
    assert '"method": "voxel_fill_marching_cubes"' in record
    assert '"pitch": 0.08' in record
    # Binary STL stores each facet independently; processing merges the
    # repeated float32 vertices with the same tolerance used by CFD tools.
    repaired = trimesh.load(destination, force="mesh", process=True)
    assert repaired.is_watertight
    assert float(repaired.bounds[:, 0].max() - repaired.bounds[:, 0].min()) < 4.0


def test_p7_repair_rejects_non_positive_pitch(tmp_path):
    from aeroforge.tools.p7_repair import repair_p7_surface

    with pytest.raises(ValueError, match="pitch"):
        repair_p7_surface(tmp_path / "missing.glb", tmp_path / "out.stl", pitch=0)
