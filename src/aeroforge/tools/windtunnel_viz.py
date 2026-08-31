"""高清风洞可视化：调用 pvpython 对真实收敛场离屏渲染烟线图。

诚实边界：没有收敛场或找不到 pvpython 时返回 skipped 并说明原因，
绝不用合成场伪造 CFD 图像（v0.2.0 的 viz_tools 曾用假场画图，v0.4.0 移除）。
"""
from __future__ import annotations

import glob
import hashlib
import json
import math
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

__all__ = [
    "DEFAULT_ANIMATION_FPS", "find_pvpython", "parse_vehicle_color",
    "render_animation", "render_case", "read_freestream",
]

DEFAULT_ANIMATION_FPS = 40

_TEMPLATE = Path(__file__).parent / "pv_templates" / "streamline_hd.py"
_ANIMATION_TEMPLATE = Path(__file__).parent / "pv_templates" / "streamline_animation.py"
_VIEWS = ("front", "wake", "side")


def parse_vehicle_color(value: str) -> tuple[float, float, float]:
    """Convert a ``#RRGGBB`` vehicle-paint value to ParaView RGB floats."""
    match = re.fullmatch(r"#?([0-9a-fA-F]{6})", value.strip())
    if not match:
        raise ValueError("vehicle color must use #RRGGBB")
    rgb = match.group(1)
    return tuple(int(rgb[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


def _encode_mp4(frame_paths: list[Path], output: Path, fps: int) -> Path | None:
    """Encode an MP4 when OpenCV is available; GIF remains the baseline output."""
    try:
        import cv2
        import numpy as np
    except ImportError:
        return None

    def read_frame(path: Path):
        data = np.fromfile(str(path), dtype=np.uint8)
        return cv2.imdecode(data, cv2.IMREAD_COLOR)

    first = read_frame(frame_paths[0])
    if first is None:
        return None
    height, width = first.shape[:2]
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = tempfile.NamedTemporaryFile(
        prefix=".aeroforge-", suffix=".mp4", dir=output.parent, delete=False)
    temporary_path = Path(temporary.name)
    temporary.close()
    try:
        writer = cv2.VideoWriter(
            str(temporary_path), cv2.VideoWriter_fourcc(*"mp4v"), fps,
            (width, height))
        try:
            if not writer.isOpened():
                return None
            for path in frame_paths:
                frame = read_frame(path)
                if frame is None or frame.shape[:2] != (height, width):
                    return None
                writer.write(frame)
        finally:
            writer.release()
        if not temporary_path.exists() or temporary_path.stat().st_size <= 100:
            return None
        shutil.copy2(temporary_path, output)
        return output
    finally:
        temporary_path.unlink(missing_ok=True)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _geometry_evidence(case: Path) -> dict:
    cfd_surface = case / "constant" / "triSurface" / "body.stl"
    visual_surface = case.parent / "geometry" / "model.stl"
    if not visual_surface.exists():
        visual_surface = cfd_surface
    cfd_hash = _sha256_file(cfd_surface) if cfd_surface.exists() else None
    visual_hash = _sha256_file(visual_surface) if visual_surface.exists() else None
    if cfd_hash is not None and visual_hash is not None and cfd_hash != visual_hash:
        raise ValueError("渲染几何与 CFD 求解表面几何不一致，禁止把其他车型外观叠到当前风场")
    return {
        "cfd_surface_path": str(cfd_surface), "cfd_surface_sha256": cfd_hash,
        "visual_surface_path": str(visual_surface), "visual_surface_sha256": visual_hash,
    }


def _result_time_dirs(case: Path) -> list[Path]:
    steps = []
    for entry in case.iterdir():
        if not entry.is_dir() or not (entry / "U").exists():
            continue
        try:
            value = float(entry.name)
        except ValueError:
            continue
        if math.isfinite(value) and value > 0:
            steps.append(entry)
    return sorted(steps, key=lambda entry: float(entry.name))


def find_pvpython() -> Path | None:
    """定位 pvpython：PATH 优先，其次常见安装目录。"""
    exe = shutil.which("pvpython") or shutil.which("pvpython.exe")
    if exe:
        return Path(exe)
    pats = [
        r"C:/Program Files/ParaView*/bin/pvpython.exe",
        r"C:/Program Files (x86)/ParaView*/bin/pvpython.exe",
        r"D:/Program Files/ParaView*/bin/pvpython.exe",
        r"E:/Program Files/ParaView*/bin/pvpython.exe",
        r"D:/ParaView*/bin/pvpython.exe",
        r"E:/ParaView*/bin/pvpython.exe",
    ]
    for pat in pats:
        hits = sorted(glob.glob(pat))
        if hits:
            return Path(hits[-1])
    return None


def read_freestream(case_dir: str | Path) -> float | None:
    """从 0/U 的 uniform 向量读入口速度模长。"""
    f = Path(case_dir) / "0" / "U"
    if not f.exists():
        return None
    m = re.search(
        r"uniform\s*\(\s*([-+\d.eE]+)\s+([-+\d.eE]+)\s+([-+\d.eE]+)\s*\)",
        f.read_text(encoding="utf-8", errors="ignore"))
    if not m:
        return None
    return math.sqrt(sum(float(g) ** 2 for g in m.groups()))


def _has_result_field(case: Path) -> bool:
    """求解器是否写出过非零时刻的 U 场（0/ 是初始场，不算）。"""
    if not (case / "constant" / "polyMesh").exists():
        return False
    return bool(_result_time_dirs(case))


def render_case(case_dir: str | Path, u_free: float | None = None,
                timeout: float = 900.0,
                vehicle_color: str = "#102947") -> dict:
    """渲染三机位高清烟线图。

    返回 {"status": completed|skipped|failed, "images": [Path...], "note": str}。
    """
    case = Path(case_dir).resolve()
    if not case.exists():
        return {"status": "skipped", "images": [],
                "note": f"算例目录不存在: {case}"}
    if not _has_result_field(case):
        return {"status": "skipped", "images": [],
                "note": "缺少非零时刻 U 结果场，跳过可视化"}
    try:
        _geometry_evidence(case)
    except ValueError as exc:
        return {"status": "failed", "images": [], "note": str(exc)}
    pv = find_pvpython()
    if pv is None:
        return {"status": "skipped", "images": [],
                "note": "未找到 pvpython，高清渲染跳过（安装 ParaView 后自动启用）"}
    if u_free is None or u_free <= 0:
        u_free = read_freestream(case) or 40.0
    colour_arg = ",".join(f"{component:.6f}"
                          for component in parse_vehicle_color(vehicle_color))
    output_paths = {
        v: case / "results" / f"streamline_hd_{v}.png" for v in _VIEWS
    }
    previous_mtimes = {
        path: path.stat().st_mtime_ns for path in output_paths.values() if path.exists()
    }
    try:
        proc = subprocess.run(
            [str(pv), str(_TEMPLATE), str(case), f"{u_free:g}", colour_arg],
            capture_output=True, text=True, timeout=timeout, encoding="utf-8",
            errors="replace")
    except subprocess.TimeoutExpired:
        return {"status": "failed", "images": [],
                "note": f"渲染超时（>{timeout:g}s）"}
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "")[-400:]
        return {"status": "failed", "images": [], "note": tail.strip()}
    imgs = []
    for p in output_paths.values():
        if (p.exists() and p.stat().st_size > 20_000
                and p.stat().st_mtime_ns > previous_mtimes.get(p, -1)):
            imgs.append(p)
    if len(imgs) == len(_VIEWS):
        return {"status": "completed", "images": imgs, "note": ""}
    tail = (proc.stderr or proc.stdout or "")[-400:]
    return {"status": "failed", "images": imgs,
            "note": tail.strip() or "渲染未生成全部新的视图产物"}


def render_animation(case_dir: str | Path, u_free: float | None = None,
                     vehicle_color: str = "#102947", frames: int = 120,
                     fps: int = DEFAULT_ANIMATION_FPS, timeout: float = 1800.0,
                     mode: str = "auto") -> dict:
    """Render field-grounded motion without conflating solver and playback time."""
    case = Path(case_dir).resolve()
    if not case.exists():
        return {"status": "skipped", "animation_paths": [],
                "note": f"算例目录不存在: {case}"}
    if not _has_result_field(case):
        return {"status": "skipped", "animation_paths": [],
                "note": "缺少非零时刻 U，跳过真实场动画"}
    try:
        geometry_evidence = _geometry_evidence(case)
    except ValueError as exc:
        return {"status": "failed", "animation_paths": [], "note": str(exc)}
    if frames < 2 or fps <= 0:
        return {"status": "failed", "animation_paths": [],
                "note": "动画帧数必须 >= 2，fps 必须 > 0"}
    if mode not in {"auto", "steady_particles", "steady_orbit", "transient"}:
        return {"status": "failed", "animation_paths": [],
                "note": f"不支持的动画模式: {mode}"}
    pv = find_pvpython()
    if pv is None:
        return {"status": "skipped", "animation_paths": [],
                "note": "未找到 pvpython，真实场动画跳过"}
    if u_free is None or u_free <= 0:
        u_free = read_freestream(case) or 40.0
    control = case / "system" / "controlDict"
    control_text = (control.read_text(encoding="utf-8", errors="ignore")
                    if control.exists() else "")
    result_steps = _result_time_dirs(case)
    field_times = [float(entry.name) for entry in result_steps]
    control_without_comments = re.sub(r"/\*.*?\*/|//[^\n]*", "", control_text, flags=re.S)
    application = re.search(r"\bapplication\s+(\w+)\s*;", control_without_comments)
    source_solver = application.group(1) if application else None
    if source_solver not in {"simpleFoam", "pimpleFoam"}:
        return {"status": "failed", "animation_paths": [],
                "note": "无法从 controlDict 确认 simpleFoam/pimpleFoam，拒绝猜测时间语义"}
    source_regime = "transient" if source_solver == "pimpleFoam" else "steady"
    if mode == "auto":
        mode = "transient" if source_regime == "transient" else "steady_particles"
    if (mode == "transient") != (source_regime == "transient"):
        return {"status": "failed", "animation_paths": [],
                "source_regime": source_regime,
                "note": f"动画模式 {mode} 与源求解器 {source_solver} 的时间语义不一致"}
    if source_regime == "transient" and len(field_times) < 3:
        return {"status": "skipped", "animation_paths": [],
                "source_regime": source_regime,
                "note": f"瞬态算例只有 {len(field_times)} 个非零 U 物理时间步；至少需 3 个，不回退为稳态"}
    actual_frames = (min(frames, len(field_times))
                     if mode == "transient" else frames)
    selected_field_times = (field_times[-actual_frames:] if mode == "transient"
                            else [field_times[-1]] * actual_frames)
    time_deltas = [b - a for a, b in zip(selected_field_times, selected_field_times[1:])]
    snapshot_time_warped = (mode == "transient" and any(
        not math.isclose(delta, time_deltas[0], rel_tol=1e-6, abs_tol=1e-12)
        for delta in time_deltas))
    colour_arg = ",".join(f"{component:.6f}"
                          for component in parse_vehicle_color(vehicle_color))
    frame_dir = case / "results" / "animation" / mode / "frames"
    frame_dir.mkdir(parents=True, exist_ok=True)
    expected = [
        frame_dir / f"frame_{index:04d}.png" for index in range(actual_frames)
    ]
    previous_mtimes = {
        path: path.stat().st_mtime_ns for path in expected if path.exists()
    }
    metadata_path = frame_dir / "animation_metadata.json"
    metadata_mtime = metadata_path.stat().st_mtime_ns if metadata_path.exists() else -1
    try:
        proc = subprocess.run(
            [str(pv), str(_ANIMATION_TEMPLATE), str(case), f"{u_free:g}",
             colour_arg, str(actual_frames), mode, str(frame_dir)],
            capture_output=True, text=True, timeout=timeout, encoding="utf-8",
            errors="replace")
    except subprocess.TimeoutExpired:
        return {"status": "failed", "animation_paths": [], "mode": mode,
                "note": f"动画渲染超时（>{timeout:g}s）"}
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "")[-500:]
        return {"status": "failed", "animation_paths": [], "mode": mode,
                "note": tail.strip() or "ParaView 动画渲染失败"}
    fresh = [
        path for path in expected
        if path.exists() and path.stat().st_size > 100
        and path.stat().st_mtime_ns > previous_mtimes.get(path, -1)
    ]
    if len(fresh) != actual_frames:
        return {"status": "failed", "animation_paths": [], "mode": mode,
                "note": f"只生成 {len(fresh)}/{actual_frames} 张新动画帧"}
    metadata = {}
    particle_advection = None
    if metadata_path.exists() and metadata_path.stat().st_mtime_ns > metadata_mtime:
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            metadata = {}
    if mode == "steady_particles":
        try:
            transport_times = [float(value) for value in metadata["particle_transport_times_s"]]
            if (len(transport_times) != actual_frames
                    or any(not math.isfinite(value) or value < 0 for value in transport_times)
                    or any(right <= left for left, right in zip(transport_times, transport_times[1:]))):
                raise ValueError("粒子输运时间必须有限、递增且与帧数一致")
            increments = [right - left for left, right in zip(transport_times, transport_times[1:])]
            if any(not math.isclose(value, increments[0], rel_tol=1e-7, abs_tol=1e-10)
                   for value in increments):
                raise ValueError("粒子必须使用全局统一输运时钟")
            if not math.isclose(float(metadata["source_field_time"]), field_times[-1]):
                raise ValueError("粒子元数据所绑定的源场时刻不一致")
            particle_advection = {
                **metadata,
                "transport_seconds_per_video_second": increments[0] * fps,
                "scope": "massless tracers in a frozen steady RANS mean velocity field; no turbulent fluctuations, diffusion or smoke dynamics",
            }
        except (KeyError, TypeError, ValueError) as exc:
            return {"status": "failed", "animation_paths": [], "mode": mode,
                    "note": f"缺少有效且新鲜的粒子输运时间证据: {exc}"}
    try:
        from PIL import Image

        images = [Image.open(path).convert("RGB") for path in fresh]
        sizes = {image.size for image in images}
        if len(sizes) != 1:
            raise ValueError("动画帧尺寸不一致")
        gif_path = case / "results" / "animation" / f"{mode}.gif"
        images[0].save(
            gif_path, save_all=True, append_images=images[1:],
            duration=max(1, round(1000 / fps)), loop=0, optimize=False,
            disposal=2)
        for image in images:
            image.close()
        with Image.open(gif_path) as encoded_gif:
            gif_durations = []
            for index in range(encoded_gif.n_frames):
                encoded_gif.seek(index)
                gif_durations.append(encoded_gif.info.get("duration", 0))
    except Exception as exc:
        return {"status": "failed", "animation_paths": [], "mode": mode,
                "note": f"动画合成失败: {exc}"}
    animation_paths = [gif_path]
    mp4_path = _encode_mp4(
        fresh, case / "results" / "animation" / f"{mode}.mp4", fps)
    if mp4_path is not None:
        animation_paths.append(mp4_path)
    gif_frame_times = [sum(gif_durations[:index]) / 1000.0
                       for index in range(len(gif_durations))]
    animation_evidence = [{
        "path": str(gif_path), "sha256": _sha256_file(gif_path),
        "format": "GIF", "frame_count": len(gif_durations),
        "frame_durations_ms": gif_durations, "video_frame_times_s": gif_frame_times,
        "duration_s": sum(gif_durations) / 1000.0,
    }]
    if mp4_path is not None:
        import cv2
        capture = cv2.VideoCapture(str(mp4_path))
        encoded_fps = capture.get(cv2.CAP_PROP_FPS)
        encoded_frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        capture.release()
        animation_evidence.append({
            "path": str(mp4_path), "sha256": _sha256_file(mp4_path),
            "format": "MP4", "codec": "mp4v", "frame_count": encoded_frames,
            "fps": encoded_fps, "duration_s": encoded_frames / encoded_fps if encoded_fps > 0 else None,
            "video_frame_times_s": [index / encoded_fps for index in range(encoded_frames)] if encoded_fps > 0 else [],
        })
    if particle_advection is not None:
        for encoded in animation_evidence:
            encoded_times = encoded["video_frame_times_s"]
            encoded["transport_seconds_per_video_second"] = (
                (transport_times[-1] - transport_times[0]) / (encoded_times[-1] - encoded_times[0])
                if len(encoded_times) == actual_frames and encoded_times[-1] > encoded_times[0]
                else None)
    note = {
        "steady_orbit": "稳态场相机环绕；流线来自真实 U，不代表瞬态尾流演化",
        "steady_particles": "冻结稳态 U 场中的示踪粒子输运；粒子运动不代表湍流随时间演化",
        "transient": "按真实 pimpleFoam 物理时间步渲染的瞬态 CFD 场；等帧率播放快照，画面时间标签为准",
    }[mode]
    if mode == "transient" and actual_frames < frames:
        note += f"；请求 {frames} 帧，算例仅有 {actual_frames} 个可用物理时间步"
    if mp4_path is None:
        note += "；当前环境未生成 MP4，已保留 GIF"
    manifest_path = frame_dir.parent / "render_manifest.json"
    manifest_path.write_text(json.dumps({
        "schema_version": 1,
        "case": str(case),
        "field": "U",
        "convergence_status": "not_evaluated_by_renderer; pipeline gates required for engineering use",
        "geometry": geometry_evidence,
        "template_sha256": _sha256_file(_ANIMATION_TEMPLATE),
        "sampling_template_sha256": _sha256_file(_ANIMATION_TEMPLATE.with_name("velocity_sampling.py")),
        "source_fields": [
            {"path": str(step / "U"), "sha256": _sha256_file(step / "U")}
            for step in (result_steps[-actual_frames:] if mode == "transient" else result_steps[-1:])
        ],
        "source_solver": source_solver,
        "source_regime": source_regime,
        "source_field_time_kind": "physical_seconds" if source_regime == "transient" else "solver_iteration",
        "source_field_times": field_times[-actual_frames:] if mode == "transient" else [field_times[-1]],
        "frame_source_field_times": metadata.get("source_field_times", selected_field_times),
        "video_frame_times_s": [index / fps for index in range(actual_frames)],
        "particle_advection": particle_advection,
        "snapshot_time_warped": snapshot_time_warped,
        "camera_motion": mode == "steady_orbit",
        "u_free_m_s": u_free,
        "mode": mode,
        "interpretation": note,
        "vehicle_color": vehicle_color.upper(),
        "requested_frame_count": frames,
        "frame_count": actual_frames,
        "fps": fps,
        "resolution": list(next(iter(sizes))),
        "frames": [
            {"path": str(path), "sha256": _sha256_file(path)} for path in fresh
        ],
        "animations": animation_evidence,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"status": "completed", "animation_paths": animation_paths,
            "frame_paths": fresh, "manifest_path": manifest_path,
            "mode": mode, "note": note}
