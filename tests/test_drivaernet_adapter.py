from __future__ import annotations

import json

import pytest


def _minimal_repo(tmp_path):
    repo = tmp_path / "DrivAerNet"
    (repo / "ParametricModels").mkdir(parents=True)
    (repo / "train_val_test_splits").mkdir()
    (repo / "README.md").write_text("DrivAerNet++ — CC BY-NC 4.0\n", encoding="utf-8")
    (repo / "LICENSE").write_text("CC BY-NC 4.0\n", encoding="utf-8")
    (repo / "ParametricModels" / "DrivAerNet_ParametricData.csv").write_text(
        "Experiment,A_Car_Length,A_Car_Width\n"
        "E_S_WWC_WM_001,4.5,1.8\n"
        "E_S_WWC_WM_002,4.6,1.9\n",
        encoding="utf-8",
    )
    for name, content in {
        "train_design_ids.txt": "E_S_WWC_WM_001\n",
        "val_design_ids.txt": "E_S_WWC_WM_002\n",
        "test_design_ids.txt": "",
    }.items():
        (repo / "train_val_test_splits" / name).write_text(content, encoding="utf-8")
    return repo


def test_inspect_drivaernet_repo_reads_official_metadata_without_downloading_data(tmp_path):
    from aeroforge.tools.drivaernet_adapter import inspect_drivaernet_repo

    repo = _minimal_repo(tmp_path)
    result = inspect_drivaernet_repo(repo)

    assert result["status"] == "valid"
    assert result["dataset_license"] == "CC BY-NC 4.0"
    assert result["design_count"] == 2
    assert result["split_counts"] == {"train": 1, "val": 1, "test": 0}
    assert result["bulk_download_performed"] is False
    assert result["native_stl_required"] is True


def test_discover_native_stl_matches_design_id_case_insensitively(tmp_path):
    from aeroforge.tools.drivaernet_adapter import discover_native_stl

    dataset = tmp_path / "meshes"
    (dataset / "subset_a").mkdir(parents=True)
    expected = dataset / "subset_a" / "E_S_WWC_WM_001.STL"
    expected.write_bytes(b"solid placeholder\n")

    assert discover_native_stl(dataset, "e_s_wwc_wm_001") == expected.resolve()

    with pytest.raises(FileNotFoundError, match="selected design|native STL"):
        discover_native_stl(dataset, "E_S_WWC_WM_999")


def test_validate_native_stl_returns_a_cfd_quality_gate(tmp_path):
    from aeroforge.tools.mesh_compat import import_trimesh
    trimesh = import_trimesh()
    from aeroforge.tools.drivaernet_adapter import validate_native_stl

    path = tmp_path / "E_S_WWC_WM_001.stl"
    trimesh.creation.box(extents=[4.5, 1.8, 1.4]).export(path)

    result = validate_native_stl(path)

    assert result["status"] == "passed"
    assert result["cfd_ready"] is True
    assert result["watertight"] is True
    assert result["components"] == 1
    assert result["faces"] == 12
    assert result["sha256"]


def test_validate_native_stl_fails_closed_for_non_finite_or_empty_asset(tmp_path):
    from aeroforge.tools.drivaernet_adapter import validate_native_stl

    path = tmp_path / "bad.stl"
    path.write_text("not an STL", encoding="utf-8")

    result = validate_native_stl(path)

    assert result["status"] == "failed"
    assert result["cfd_ready"] is False
    assert result["errors"]
    assert json.dumps(result, ensure_ascii=False)
