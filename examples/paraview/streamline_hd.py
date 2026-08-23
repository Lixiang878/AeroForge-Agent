# -*- coding: utf-8 -*-
"""ParaView 高清流线渲染（稳态收敛场）。

在 windtunnel_view.py 基础上的高质量版本：
- 结构化烟线源（上游横向排线，经典风洞烟线）替代随机点云；
- 速度大小按 Cool-Warm 学术色表着色 + 色标图例（U, m/s）；
- 中心纵剖切片（半透明）+ 深色车漆 + 近场地面条带；
- 两个机位：3/4 前侧视（主图）+ 后上方尾流俯视；
- 离屏渲染 2400x1350 PNG（FXAA 反走样）。

用法：
    pvpython examples/paraview/streamline_hd.py            # 自动找 workspace 最新稳态场
    pvpython examples/paraview/streamline_hd.py <case_dir> # 指定算例目录
"""
import glob
import os
import sys

os.environ.setdefault('PARAVIEW_USE_VISRTX', '0')  # VisRTX 对线/半透明渲染不稳

CASE = sys.argv[1] if len(sys.argv) > 1 else None

from paraview.simple import (  # noqa: E402
    OpenFOAMReader, STLReader, StreamTracer, Slice, Show,
    ColorBy, Render, GetActiveView, SaveScreenshot, GetAnimationScene,
    GetScalarBar, GetColorTransferFunction, GetOpacityTransferFunction,
    CellDatatoPointData,
)


def setp(obj, keys, val):
    """ParaView 不同版本属性名不同（CamelCase / snake_case），逐个尝试。"""
    for k in keys:
        try:
            setattr(obj, k, val)
            return True
        except Exception:
            continue
    return False


def find_case():
    if CASE:
        return CASE
    here = os.path.dirname(os.path.abspath(__file__))
    ws = os.path.join(here, '..', '..', 'workspace')
    cands = [d for d in glob.glob(os.path.join(ws, '*', 'case')) + glob.glob(os.path.join(ws, 'diag_*'))
             if glob.glob(os.path.join(d, '[0-9]*')) or glob.glob(os.path.join(d, 'constant', 'polyMesh'))]
    if not cands:
        raise SystemExit('[hd] 未找到算例，请指定 case 目录')
    return max(cands, key=os.path.getmtime)


case = os.path.abspath(find_case())
foam = os.path.join(case, 'case.foam')
if not os.path.exists(foam):
    foam = case
print('[hd] case =', case)

# ---------- 读全场（该版本单独选 patch 返回空，全读后几何裁剪）
vol = OpenFOAMReader()
setp(vol, ('FileName', 'CasePath'), foam)
vol.UpdatePipeline()

# OpenFOAM reader 默认把场放 CellData；流线/切片着色需要点数据
c2p = CellDatatoPointData(Input=vol)
try:
    c2p.ProcessAllArrays = 1
except Exception:
    pass
c2p.UpdatePipeline()

# 收敛末场（多时间步时取最后一个）
scene = GetAnimationScene()
ts = vol.TimestepValues
if ts and len(ts) > 1:
    scene.AnimationTime = ts[-1]

# ---------- 车体：参数化 STL（reader patch 块提取不稳定，STL 最可靠）
stl_path = os.path.join(os.path.dirname(case), 'geometry', 'model.stl')
if not os.path.exists(stl_path):
    stl_path = os.path.join(case, '..', 'geometry', 'model.stl')
if not os.path.exists(stl_path):
    stl_path = os.path.join(case, 'constant', 'triSurface', 'body.stl')
body = STLReader()
setp(body, ('FileName', 'FileNames'), stl_path)
body.UpdatePipeline()
body_disp = Show(body)
setp(body_disp, ('DiffuseColor', 'diffuse_color'), [0.72, 0.08, 0.06])
setp(body_disp, ('Specular', 'specular'), 0.5)
setp(body_disp, ('SpecularPower', 'specular_power'), 30)

# ---------- 近场地面条带
from paraview.simple import ExtractSurface, Clip  # noqa: E402
es = ExtractSurface(Input=vol)
gnd = Clip(Input=es)
gnd.ClipType = 'Box'
setp(gnd.ClipType, ('Position', 'position'), [0.7, 0.0, -0.01])
setp(gnd.ClipType, ('Length', 'length'), [3.4, 1.6, 0.06])
setp(gnd, ('Invert', 'InsideOut'), 1)
gnd_disp = Show(gnd)
setp(gnd_disp, ('DiffuseColor', 'diffuse_color'), [0.30, 0.31, 0.34])

# ---------- 烟线：上游横向排线（经典风洞结构化烟线）
st = StreamTracer(Input=vol, SeedType='Line')
L = st.SeedType
setp(L, ('Point1', 'point1'), [-0.85, -0.16, 0.035])
setp(L, ('Point2', 'point2'), [-0.85, 0.16, 0.035])
setp(L, ('Resolution', 'resolution'), 48)
for _k, _v in (('MaximumNumberOfSteps', 4000), ('MaximumSteps', 4000),
               ('InitialStepLength', 0.0002), ('MaximumStepLength', 0.015),
               ('TerminalSpeed', 'terminal_speed'), ):
    if _k != 'TerminalSpeed':
        setp(st, (_k,), _v)
setp(st, ('TerminalSpeed', 'terminal_speed'), 1e-4)
st_disp = Show(st)
try:
    ColorBy(st_disp, ('POINTS', 'U', 'Magnitude'))
except Exception:
    ColorBy(st_disp, ('POINTS', 'U'))
setp(st_disp, ('LineWidth', 'line_width'), 2.0)

# 第二组烟线：稍高的第二层（体现流向三维性）
st2 = StreamTracer(Input=vol, SeedType='Line')
L2 = st2.SeedType
setp(L2, ('Point1', 'point1'), [-0.85, -0.12, 0.22])
setp(L2, ('Point2', 'point2'), [-0.85, 0.12, 0.22])
setp(L2, ('Resolution', 'resolution'), 36)
for _k, _v in (('MaximumNumberOfSteps', 4000), ('InitialStepLength', 0.0002),
               ('MaximumStepLength', 0.015)):
    setp(st2, (_k,), _v)
st2_disp = Show(st2)
try:
    ColorBy(st2_disp, ('POINTS', 'U', 'Magnitude'))
except Exception:
    ColorBy(st2_disp, ('POINTS', 'U'))
setp(st2_disp, ('LineWidth', 'line_width'), 2.0)

# ---------- 中心纵剖"激光光片"
sl = Slice(Input=vol)
setp(sl.SliceType, ('Origin', 'origin'), [0.5, 0.0, 0.2])
setp(sl.SliceType, ('Normal', 'normal'), [0.0, 1.0, 0.0])
sl_disp = Show(sl)
try:
    ColorBy(sl_disp, ('POINTS', 'U', 'Magnitude'))
except Exception:
    ColorBy(sl_disp, ('POINTS', 'U'))
setp(sl_disp, ('Opacity', 'opacity'), 0.32)

# ---------- 统一速度色表：Cool-Warm 学术色，0-45 m/s
lut = GetColorTransferFunction('U')
lut.ApplyPreset('Cool to Warm (Extended)', False)
lut.RescaleTransferFunction(0.0, 45.0)
op = GetOpacityTransferFunction('U')
try:
    op.Points = [0.0, 0.0, 0.5, 0.0, 45.0, 1.0, 0.5, 0.0]
except Exception:
    pass
for d in (st_disp, st2_disp, sl_disp):
    try:
        d.LookupTable = lut
    except Exception:
        pass

# 色标图例
bar = GetScalarBar(lut, GetActiveView())
bar.Title = 'U (m/s)'
bar.TitleFontSize = 18
bar.LabelFontSize = 15
setp(bar, ('ComponentTitle', 'component_title'), '')
bar.Visibility = 1

# ---------- 视图与机位
view = GetActiveView()
setp(view, ('Background', 'background'), [0.90, 0.92, 0.95])
try:
    view.UseFXAA = 1
except Exception:
    pass


def cam_shot(pos, focal, up, zoom, fname):
    cam = None
    try:
        cam = view.GetActiveCamera()
    except Exception:
        cam = None
    if cam is None:
        print('[hd] 相机不可用，跳过机位', fname)
        return
    cam.SetPosition(*pos)
    cam.SetFocalPoint(*focal)
    cam.SetViewUp(*up)
    try:
        cam.SetViewAngle(38.0)
    except Exception:
        pass
    try:
        cam.Zoom(zoom)
    except Exception:
        pass
    Render()
    out = os.path.join(case, 'results', fname)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    SaveScreenshot(out, view, ImageResolution=[2400, 1350])
    print('[hd] 已保存:', out)


# 机位 1：3/4 前侧视（主图：烟线绕前缘 + 斜面）
cam_shot((1.95, -1.30, 0.60), (0.45, 0.0, 0.16), (0.0, 0.0, 1.0), 1.75,
         'streamline_hd_front.png')

# 机位 2：后上方斜俯视（尾流结构）
cam_shot((2.30, -0.75, 1.15), (1.15, 0.0, 0.12), (0.0, 0.0, 1.0), 1.55,
         'streamline_hd_wake.png')

# 机位 3：正侧视（对称面切片完整呈现）
cam_shot((0.60, -1.85, 0.35), (0.60, 0.0, 0.18), (0.0, 0.0, 1.0), 1.45,
         'streamline_hd_side.png')
