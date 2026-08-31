# -*- coding: utf-8 -*-
"""Render an STL-only geometry preview without presenting it as a CFD result.

Usage:
    pvpython geometry_preview.py <model.stl> <output.png>
"""
import os
import sys

os.environ.setdefault("PARAVIEW_USE_VISRTX", "0")

if len(sys.argv) < 3:
    raise SystemExit("usage: geometry_preview.py <model.stl> <output.png>")

stl_path = os.path.abspath(sys.argv[1])
output_path = os.path.abspath(sys.argv[2])

from paraview.simple import (  # noqa: E402
    Box,
    CreateView,
    Render,
    SaveScreenshot,
    SetActiveView,
    Show,
    STLReader,
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


body = STLReader()
setp(body, ("FileName", "FileNames"), stl_path)
body.UpdatePipeline()
bounds = body.GetDataInformation().GetBounds()
if not bounds or bounds[0] > bounds[1]:
    raise SystemExit(f"empty or invalid STL: {stl_path}")

x0, x1, y0, y1, z0, z1 = bounds
length, width, height = x1 - x0, y1 - y0, z1 - z0
cx, cy = 0.5 * (x0 + x1), 0.5 * (y0 + y1)

view = CreateView("RenderView")
SetActiveView(view)
setp(view, ("UseGradientBackground",), 1)
setp(view, ("Background", "background"), [0.012, 0.020, 0.036])
setp(view, ("Background2", "background2"), [0.12, 0.17, 0.23])
setp(view, ("OrientationAxesVisibility",), 0)
setp(view, ("UseFXAA",), 1)
setp(view, ("MultiSamples",), 8)
setp(view, ("UseSSAO",), 1)
setp(view, ("SSAORadius",), 0.08 * height)
setp(view, ("SSAOIntensity",), 0.65)

display = Show(body, view)
setp(display, ("DiffuseColor", "diffuse_color"), [0.065, 0.16, 0.28])
setp(display, ("Ambient", "ambient"), 0.24)
setp(display, ("Diffuse", "diffuse"), 0.80)
setp(display, ("Specular", "specular"), 0.55)
setp(display, ("SpecularPower", "specular_power"), 65.0)
if setp(display, ("Interpolation",), "PBR"):
    setp(display, ("Metallic",), 0.45)
    setp(display, ("Roughness",), 0.26)

# A shallow neutral plinth gives scale and contact cues.  It is geometry-only,
# not a pressure/velocity plane.
plinth = Box()
plinth.XLength = 1.65 * length
plinth.YLength = 2.6 * width
plinth.ZLength = max(0.012 * height, 0.004)
plinth.Center = [cx, cy, z0 - 0.55 * plinth.ZLength]
plinth_display = Show(plinth, view)
setp(plinth_display, ("DiffuseColor", "diffuse_color"), [0.12, 0.14, 0.17])
setp(plinth_display, ("Ambient", "ambient"), 0.35)
setp(plinth_display, ("Specular", "specular"), 0.12)

# Initialise the renderer before setting the camera; ParaView may reset the
# first camera to include every newly-created source otherwise.
Render(view)
camera = view.GetActiveCamera()
focal = [cx, cy, z0 + 0.42 * height]
position = [cx - 1.15 * length, cy - 1.75 * width,
            z0 + 0.78 * height]
frame_scale = max(1.25 * height, 0.68 * length)
setp(view, ("CameraFocalPoint",), focal)
setp(view, ("CameraPosition",), position)
setp(view, ("CameraViewUp",), [0.0, 0.0, 1.0])
setp(view, ("CameraParallelProjection",), 1)
setp(view, ("CameraParallelScale",), frame_scale)
camera.SetFocalPoint(*focal)
camera.SetPosition(*position)
camera.SetViewUp(0.0, 0.0, 1.0)
camera.SetParallelProjection(1)
camera.SetParallelScale(frame_scale)
Render(view)
os.makedirs(os.path.dirname(output_path), exist_ok=True)
SaveScreenshot(output_path, view, ImageResolution=[2400, 1350],
               TransparentBackground=0)
print("[geometry-preview] bounds:", bounds)
print("[geometry-preview] saved:", output_path)
