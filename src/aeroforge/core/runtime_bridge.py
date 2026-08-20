"""OpenFOAM 运行时桥接：native / WSL / 不可用（dry-run）三态。

设计边界：
- 找不到任何 OpenFOAM 运行时 -> `RuntimeInfo.available == False`，
  上层显式降级为 dry-run，绝不伪装成"已收敛的 CFD"。
- Windows 本机通过 WSL 调用（要求 WSL 内装有 OpenFOAM，如 openfoam2412）；
  Linux 本机直接调用 PATH 中的求解器。
- 路径转换经 `wslpath -u`，失败时用规则回退（盘符 -> /mnt/<drv>）。
"""
from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

__all__ = ["RuntimeInfo", "RuntimeBridge", "detect_runtime"]

_WSL_LS_TIMEOUT = 60.0  # WSL 冷启动可能较慢，预留足够超时
# wsl.exe 的重定向输出/警告横幅可能为 UTF-16，统一用 utf-8+replace 避免解码崩溃
_CAPTURE_KW = dict(capture_output=True, text=True, encoding="utf-8", errors="replace")


@dataclass
class RuntimeInfo:
    """探测结果：后端类型、版本、bashrc 路径（WSL）。"""

    backend: str = "unavailable"  # native | wsl | unavailable
    version: str = ""
    bashrc: str = ""              # WSL 内的 OpenFOAM etc/bashrc 绝对路径
    solver_path: str = ""
    detail: str = ""

    @property
    def available(self) -> bool:
        return self.backend != "unavailable"


def _wsl_exe() -> str | None:
    return shutil.which("wsl") or shutil.which("wsl.exe")


def detect_runtime(timeout: float = _WSL_LS_TIMEOUT, force: bool = False) -> RuntimeInfo:
    """探测可用的 OpenFOAM 运行时（native 优先，其次 WSL）。

    结果进程内缓存（WSL 探测较慢）；force=True 强制重新探测。
    """
    global _DETECT_CACHE
    if _DETECT_CACHE is not None and not force:
        return _DETECT_CACHE
    info = _detect_runtime_uncached(timeout)
    if info.available:
        _DETECT_CACHE = info
    return info


_DETECT_CACHE: RuntimeInfo | None = None


def _detect_runtime_uncached(timeout: float) -> RuntimeInfo:
    local = shutil.which("simpleFoam")
    if local:
        return RuntimeInfo(backend="native", solver_path=local,
                           detail="OpenFOAM found on PATH")

    wsl = _wsl_exe()
    if wsl and os.name == "nt":
        versions: list[str] = []
        for attempt in range(2):  # WSL 冷启动重试一次
            try:
                ls = subprocess.run(
                    [wsl, "-e", "bash", "-lc", "ls -1 /usr/lib/openfoam 2>/dev/null"],
                    timeout=timeout, **_CAPTURE_KW)
                versions = [ln.strip() for ln in ls.stdout.splitlines()
                            if re.fullmatch(r"openfoam\d+", ln.strip())]
                break
            except subprocess.TimeoutExpired:
                continue
            except OSError:
                break
        try:
            if versions:
                ver = sorted(versions)[-1]
                bashrc = f"/usr/lib/openfoam/{ver}/etc/bashrc"
                chk = subprocess.run(
                    [wsl, "-e", "bash", "-lc",
                     f"source {bashrc} && command -v simpleFoam"],
                    timeout=timeout, **_CAPTURE_KW)
                if chk.returncode == 0 and chk.stdout.strip():
                    return RuntimeInfo(backend="wsl", version=ver, bashrc=bashrc,
                                       solver_path=chk.stdout.strip(),
                                       detail="OpenFOAM via WSL")
        except (OSError, subprocess.TimeoutExpired):
            pass
    return RuntimeInfo(detail="no OpenFOAM runtime detected (native or WSL)")


class RuntimeBridge:
    """统一执行层：把 OpenFOAM 工具调用路由到可用后端。

    用法：
        bridge = RuntimeBridge()
        if bridge.available():
            res = bridge.run(["blockMesh"], cwd=case_dir, log_path=log)
        else:
            ...  # dry-run 分支
    """

    def __init__(self, info: RuntimeInfo | None = None):
        self.info = info if info is not None else detect_runtime()

    @property
    def available(self) -> bool:
        return self.info.available

    # ---------------------------------------------------------- 路径转换
    def runtime_path(self, path: str | Path) -> str:
        """把 Windows 路径转为运行环境路径（native 下原样返回绝对路径）。"""
        path = Path(path).resolve()  # wslpath 只接受绝对路径
        if self.info.backend != "wsl":
            return str(path)
        try:
            out = subprocess.run(
                [_wsl_exe(), "-e", "wslpath", "-u", str(path)],
                timeout=15.0, **_CAPTURE_KW)
            if out.returncode == 0 and out.stdout.strip():
                return out.stdout.strip()
        except (OSError, subprocess.TimeoutExpired):
            pass
        return self._fallback_wsl_path(str(path))

    @staticmethod
    def _fallback_wsl_path(win: str) -> str:
        """规则回退：E:\\a\\b -> /mnt/e/a/b（含空格/中文保持原样）。"""
        if re.match(r"^[A-Za-z]:[\\/]", win):
            drive, rest = win[:1].lower(), win[2:]
            return f"/mnt/{drive}" + rest.replace("\\", "/")
        return win.replace("\\", "/")

    # ---------------------------------------------------------- 命令执行
    def run(self, argv: list[str], cwd: str | Path,
            log_path: str | Path | None = None,
            timeout: float = 7200.0) -> dict:
        """执行 OpenFOAM 工具，stdout/stderr 汇入日志文件。

        返回 {"returncode", "log_path", "backend"}；dry-run 时不执行并
        返回 {"dry_run": True, ...}。
        """
        if not self.available:
            return {"dry_run": True, "returncode": None,
                    "backend": "unavailable", "log_path": None}

        cwd = Path(cwd)
        cwd.mkdir(parents=True, exist_ok=True)
        exe_name = Path(argv[0]).name.replace(" ", "_")
        log = Path(log_path) if log_path else cwd / f"log.{exe_name}"

        if self.info.backend == "native":
            cmd: list[str] = list(argv)
            with log.open("w", encoding="utf-8", errors="replace") as fh:
                proc = subprocess.run(
                    cmd, cwd=cwd, stdout=fh, stderr=subprocess.STDOUT,
                    text=True, timeout=timeout, check=False)
        else:
            # 日志在 WSL 内部重定向（wsl.exe 自身的重定向会把输出转成
            # UTF-16，导致日志不可读），Windows 侧直接可读 /mnt 路径。
            rcwd = self.runtime_path(cwd)
            rlog = self.runtime_path(log)
            script = (f"source {self.info.bashrc} && "
                      f"cd {shlex.quote(rcwd)} && "
                      + " ".join(shlex.quote(a) for a in argv)
                      + f" > {shlex.quote(rlog)} 2>&1")
            proc = subprocess.run(
                [_wsl_exe(), "-e", "bash", "-lc", script],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=timeout, check=False)
        return {"dry_run": False, "returncode": proc.returncode,
                "backend": self.info.backend, "log_path": str(log)}
