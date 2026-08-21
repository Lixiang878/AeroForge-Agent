# -*- coding: utf-8 -*-
"""ParaView「风洞测试视角」一键配置脚本。

把 OpenFOAM 算例渲染成汽车风洞实验的经典画面：
- 隐藏计算域外壁：只保留车体+近场地面（ExtractSurface + 盒裁剪）；
- 上游"烟线"：流线束（StreamTracer，按速度着色）；
- 中心纵剖"激光光片"：y=0 切片（按速度着色）；
- 车体表面按压力 p 着色（类似压敏漆）；
- 3/4 前侧机位相机 + 浅色背景；
- 自动保存截图到 results/windtunnel_view.png。

用法（任选其一）：
1) 命令行（推荐）：pvpython examples/paraview/windtunnel_view.py
2) ParaView GUI：Tools -> Python Shell，先 CASE=r'<case目录>' 再
   exec(open(r'<本文件路径>').read())
   （不设置 CASE 时自动取 workspace 下最新含瞬态帧的算例）

动画：GUI 中运行后按播放键逐帧播放（切片/车体表面随时间变化；流线每帧
重算较慢，看动态尾流建议先隐藏流线只播切片）。
"""
import glob
import os

CASE = globals().get('CASE', None)

from paraview.simple import (  # noqa: E402
    OpenFOAMReader, STLReader, StreamTracer, Slice, Show,
    ColorBy, Render, GetActiveView, SaveScreenshot, GetAnimationScene,
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
    cands = [d for d in glob.glob(os.path.join(ws, 'task_*', 'case'))
             if glob.glob(os.path.join(d, '[0-9]*.[0-9]*'))]
    if not cands:
        raise SystemExit('[windtunnel] 未找到含瞬态帧的算例，请先运行 animate_ahmed.py')
    return max(cands, key=os.path.getmtime)


case = find_case()
foam = os.path.join(case, 'case.foam')
if not os.path.exists(foam):
    foam = case
print('[windtunnel] case =', case)

# ---------- 读取全部区域（该版本单独选 patch 会返回空，故全读后用几何裁剪）
vol = OpenFOAMReader()
setp(vol, ('FileName', 'CasePath'), foam)
vol.UpdatePipeline()

# 取较后帧（尾流已发展）
scene = GetAnimationScene()
ts = vol.TimestepValues
if ts and len(ts) > 1:
    scene.AnimationTime = ts[len(ts) * 2 // 3]

# ---------- 车体：直接读参数化 STL（该版本 OpenFOAM reader 的 patch 块
#             提取不稳定，STL 几何最可靠）；深色车漆质感
stl_path = os.path.join(os.path.dirname(case), 'geometry', 'model.stl')
if not os.path.exists(stl_path):
    stl_path = os.path.join(case, '..', 'geometry', 'model.stl')
body = STLReader()
setp(body, ('FileName', 'FileNames'), stl_path)
body.UpdatePipeline()
body_disp = Show(body)
setp(body_disp, ('DiffuseColor', 'diffuse_color'), [0.85, 0.12, 0.10])
setp(body_disp, ('Opacity', 'opacity'), 1.0)

# ---------- 近场地面条带：从全表面裁剪出车下地面，提供“路面”语境
from paraview.simple import ExtractSurface, Clip  # noqa: E402
es = ExtractSurface(Input=vol)
gnd = Clip(Input=es)
gnd.ClipType = 'Box'
setp(gnd.ClipType, ('Position', 'position'), [0.7, 0.0, -0.01])
setp(gnd.ClipType, ('Length', 'length'), [3.2, 1.6, 0.06])
setp(gnd, ('Invert', 'InsideOut'), 1)
gnd_disp = Show(gnd)
setp(gnd_disp, ('DiffuseColor', 'diffuse_color'), [0.35, 0.35, 0.38])

# ---------- 上游烟线：流线束
st = StreamTracer(Input=vol, SeedType='Point Cloud')
setp(st.SeedType, ('NumberOfPoints', 'number_of_points'), 60)
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

# ---------- 中心激光光片：y=0 纵剖切片
sl = Slice(Input=vol)
setp(sl.SliceType, ('Origin', 'origin'), [0.5, 0.0, 0.2])
setp(sl.SliceType, ('Normal', 'normal'), [0.0, 1.0, 0.0])
sl_disp = Show(sl)
try:
    ColorBy(sl_disp, ('POINTS', 'U', 'Magnitude'))
except Exception:
    ColorBy(sl_disp, ('POINTS', 'U'))
setp(sl_disp, ('Opacity', 'opacity'), 0.30)

# ---------- 背景与机位：浅色试验段背景；3/4 前侧机位
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
    try:
        cam.SetViewAngle(40.0)
    except Exception:
        pass
    try:
        cam.Zoom(1.8)   # 拉近主体
    except Exception:
        pass
Render()

out_png = os.path.join(case, 'results', 'windtunnel_view.png')
os.makedirs(os.path.dirname(out_png), exist_ok=True)
SaveScreenshot(out_png, view, ImageResolution=[1600, 1000])
print('[windtunnel] 截图已保存:', out_png)
print('[windtunnel] GUI 中按播放键可逐帧播放动态过程')
