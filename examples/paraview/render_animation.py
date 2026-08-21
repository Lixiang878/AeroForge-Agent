# -*- coding: utf-8 -*-
"""把瞬态算例渲染成风洞视角动画序列帧（pvpython 运行）。

输出 case/results/anim/frame_XXXX.png，随后可用任意工具合成 GIF/MP4。
用法：pvpython examples/paraview/render_animation.py
"""
import glob
import os

from paraview.simple import (  # noqa: E402
    OpenFOAMReader, STLReader, StreamTracer, Slice, Show,
    ColorBy, Render, GetActiveView, SaveScreenshot, GetAnimationScene,
)


def setp(obj, keys, val):
    for k in keys:
        try:
            setattr(obj, k, val)
            return True
        except Exception:
            continue
    return False


here = os.path.dirname(os.path.abspath(__file__))
ws = os.path.join(here, '..', '..', 'workspace')
cands = [d for d in glob.glob(os.path.join(ws, 'task_*', 'case'))
         if glob.glob(os.path.join(d, '[0-9]*.[0-9]*'))]
case = max(cands, key=os.path.getmtime)
foam = os.path.join(case, 'case.foam')
out_dir = os.path.join(case, 'results', 'anim')
os.makedirs(out_dir, exist_ok=True)
print('[anim] case =', case)

vol = OpenFOAMReader()
setp(vol, ('FileName', 'CasePath'), foam)
vol.UpdatePipeline()

# 车体 STL
stl_path = os.path.join(os.path.dirname(case), 'geometry', 'model.stl')
body = STLReader()
setp(body, ('FileName', 'FileNames'), stl_path)
body_disp = Show(body)
setp(body_disp, ('DiffuseColor', 'diffuse_color'), [0.85, 0.12, 0.10])

# 近场地面条带
from paraview.simple import ExtractSurface, Clip  # noqa: E402
es = ExtractSurface(Input=vol)
gnd = Clip(Input=es)
gnd.ClipType = 'Box'
setp(gnd.ClipType, ('Position', 'position'), [0.7, 0.0, -0.01])
setp(gnd.ClipType, ('Length', 'length'), [3.2, 1.6, 0.06])
setp(gnd, ('Invert', 'InsideOut'), 1)
gnd_disp = Show(gnd)
setp(gnd_disp, ('DiffuseColor', 'diffuse_color'), [0.35, 0.35, 0.38])

# 烟线（少量，保证渲染速度）
st = StreamTracer(Input=vol, SeedType='Point Cloud')
setp(st.SeedType, ('NumberOfPoints', 'number_of_points'), 40)
setp(st.SeedType, ('Center', 'center'), [-0.9, 0.0, 0.20])
setp(st.SeedType, ('Radius', 'radius'), 0.28)
for _k, _v in (('MaximumNumberOfSteps', 3000), ('MaximumSteps', 3000),
               ('InitialStepLength', 0.0002), ('MaximumStepLength', 0.02)):
    setp(st, (_k,), _v)
st_disp = Show(st)
try:
    ColorBy(st_disp, ('POINTS', 'U', 'Magnitude'))
except Exception:
    ColorBy(st_disp, ('POINTS', 'U'))
setp(st_disp, ('LineWidth', 'line_width'), 1.5)

# 中心光片
sl = Slice(Input=vol)
setp(sl.SliceType, ('Origin', 'origin'), [0.5, 0.0, 0.2])
setp(sl.SliceType, ('Normal', 'normal'), [0.0, 1.0, 0.0])
sl_disp = Show(sl)
try:
    ColorBy(sl_disp, ('POINTS', 'U', 'Magnitude'))
except Exception:
    ColorBy(sl_disp, ('POINTS', 'U'))
setp(sl_disp, ('Opacity', 'opacity'), 0.30)

view = GetActiveView()
setp(view, ('Background', 'background'), [0.88, 0.90, 0.93])
cam = None
try:
    cam = view.GetActiveCamera()
except Exception:
    cam = None
if cam is not None:
    cam.SetPosition(1.9, -1.35, 0.62)
    cam.SetFocalPoint(0.45, 0.0, 0.16)
    cam.SetViewUp(0.0, 0.0, 1.0)

scene = GetAnimationScene()
ts = list(vol.TimestepValues)
ts = [t for t in ts if t > 0]
print('[anim] frames to render:', len(ts))
for i, t in enumerate(ts):
    scene.AnimationTime = t
    Render()
    SaveScreenshot(os.path.join(out_dir, 'frame_%04d.png' % i),
                   view, ImageResolution=[960, 600])
    print('[anim] rendered', i + 1, '/', len(ts), 't=%.5f' % t)
print('[anim] done ->', out_dir)
