# -*- coding: utf-8 -*-
"""生成「风洞流线视角」ParaView 状态文件（.pvsm）。

双击生成的 .pvsm（或 ParaView 里 File -> Load State）即自动打开对应
.foam 算例，并带好：上游烟线（StreamTracer 流线，按速度着色）、
中心纵剖光片、车体、近场地面、3/4 机位。时间轴按播放键即动态流线。

用法：pvpython examples/paraview/save_state.py
"""
import glob
import os

from paraview.simple import (  # noqa: E402
    OpenFOAMReader, STLReader, StreamTracer, Slice, Show,
    ColorBy, Render, GetActiveView, GetAnimationScene, SaveState,
    ExtractSurface, Clip,
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
print('[state] case =', case)

# ---------- 体数据（流线/光片用）
vol = OpenFOAMReader()
setp(vol, ('FileName', 'CasePath'), foam)
vol.UpdatePipeline()

# ---------- 车体 STL（红色车漆）
stl_path = os.path.join(os.path.dirname(case), 'geometry', 'model.stl')
body = STLReader()
setp(body, ('FileName', 'FileNames'), stl_path)
body_disp = Show(body)
setp(body_disp, ('DiffuseColor', 'diffuse_color'), [0.85, 0.12, 0.10])

# ---------- 近场地面条带
es = ExtractSurface(Input=vol)
gnd = Clip(Input=es)
gnd.ClipType = 'Box'
setp(gnd.ClipType, ('Position', 'position'), [0.7, 0.0, -0.01])
setp(gnd.ClipType, ('Length', 'length'), [3.2, 1.6, 0.06])
setp(gnd, ('Invert', 'InsideOut'), 1)
gnd_disp = Show(gnd)
setp(gnd_disp, ('DiffuseColor', 'diffuse_color'), [0.35, 0.35, 0.38])

# ---------- 风的流线（烟线）：上游点云种子，按速度着色
st = StreamTracer(Input=vol, SeedType='Point Cloud')
setp(st.SeedType, ('NumberOfPoints', 'number_of_points'), 80)
setp(st.SeedType, ('Center', 'center'), [-0.9, 0.0, 0.20])
setp(st.SeedType, ('Radius', 'radius'), 0.30)
for _k, _v in (('MaximumNumberOfSteps', 4000), ('MaximumSteps', 4000),
               ('InitialStepLength', 0.0002), ('MaximumStepLength', 0.02)):
    setp(st, (_k,), _v)
st_disp = Show(st)
try:
    ColorBy(st_disp, ('POINTS', 'U', 'Magnitude'))
except Exception:
    ColorBy(st_disp, ('POINTS', 'U'))
setp(st_disp, ('LineWidth', 'line_width'), 2.0)

# ---------- 中心纵剖光片（y=0，半透明）
sl = Slice(Input=vol)
setp(sl.SliceType, ('Origin', 'origin'), [0.5, 0.0, 0.2])
setp(sl.SliceType, ('Normal', 'normal'), [0.0, 1.0, 0.0])
sl_disp = Show(sl)
try:
    ColorBy(sl_disp, ('POINTS', 'U', 'Magnitude'))
except Exception:
    ColorBy(sl_disp, ('POINTS', 'U'))
setp(sl_disp, ('Opacity', 'opacity'), 0.30)

# ---------- 机位与背景
view = GetActiveView()
setp(view, ('Background', 'background'), [0.88, 0.90, 0.93])
try:
    cam = view.GetActiveCamera()
    cam.SetPosition(1.9, -1.35, 0.62)
    cam.SetFocalPoint(0.45, 0.0, 0.16)
    cam.SetViewUp(0.0, 0.0, 1.0)
except Exception:
    pass
Render()

# ---------- 保存状态文件
out_pvsm = os.path.join(case, 'results', 'windtunnel_streamlines.pvsm')
SaveState(out_pvsm)
print('[state] saved ->', out_pvsm)
print('[state] 在 ParaView 中双击该文件（或 File->Load State），按播放键看动态流线')
