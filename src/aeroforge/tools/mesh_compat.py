"""Small runtime guard for optional trimesh imports on Windows.

Some Anaconda/Python 3.12 builds make ``platform.system()`` perform a slow WMI
query.  Trimesh probes that value while importing its optional Blender backend,
so a fresh worker can appear to hang before it ever reads an STL.  Seeding the
standard-library uname cache with the already-known Windows platform keeps the
import deterministic and does not alter solver or mesh semantics.
"""
from __future__ import annotations

from typing import Any

__all__ = ["import_trimesh", "prime_windows_platform_cache"]


def prime_windows_platform_cache() -> None:
    """Avoid the slow WMI branch in Anaconda's ``platform.system()`` call."""
    import platform

    if getattr(platform, "_uname_cache", None) is None:
        platform._uname_cache = platform.uname_result("Windows", "", "", "", "")


def import_trimesh() -> Any:
    """Import trimesh without triggering a blocking Windows WMI probe."""
    prime_windows_platform_cache()
    import trimesh

    return trimesh
