# -*- coding: utf-8 -*-
"""ParaView 高清风洞流线渲染（稳态收敛场）。

经典风洞烟线构图：
- 中线垂直烟幕（y=0 平面一排种子）+ 两层横向烟线排（不同高度绕流），
  种子位置由 STL 包围盒自动推导（上游 0.35L 处），不再硬编码坐标；
- 速度大小 Cool-Warm 色表 + 自适应量程（1.08 倍自由流速度）；
- 中心纵剖切片半透明衬底；深红车漆；近场地面条带；
- 三机位：3/4 前侧主图 / 后上方尾流 / 正侧视，均按包围盒自动取景；
- 离屏渲染 2400x1350 PNG（FXAA 反走样）。

要点：OpenFOAM reader 输出的场在 CellData，必须经 CellDatatoPointData
后作为 StreamTracer/Slice 的输入，否则流线积分为空、切片无法着色。

用法：
    pvpython streamline_hd.py <case_dir> [u_free_mps]
"""
import os
import re
import sys

os.environ.setdefault('PARAVIEW_USE_VISRTX', '0')  # VisRTX 对线/半透明渲染不稳

CASE = sys.argv[1] if len(sys.argv) > 1 else None
UFREE = float(sys.argv[2]) if len(sys.argv) > 2 else None

from paraview.simple import (  # noqa: E402
    OpenFOAMReader, STLReader, StreamTracer, Slice, Show,
    ColorBy, Render, SaveScreenshot, GetAnimationScene,
    GetScalarBar, GetColorTransferFunction, CellDatatoPointData,
    ExtractSurface, Clip, Tube, CreateView, SetActiveView,
)


def setp(obj, keys, val):
    """ParaView 不同版本属性名不同，逐个尝试。"""
    for k in keys:
        try:
            setattr(obj, k, val)
            return True
        except Exception:
            continue
    return False


def stl_bbox(path):
    """解析 STL 包围盒（纯标准库，自动识别 ASCII / 二进制格式）。"""
    import struct
    with open(path, 'rb') as fh:
        data = fh.read()
    xs, ys, zs = [], [], []
    if data[:5].lower() == b'solid' and b'facet' in data[:2048]:
        pat = re.compile(r'vertex\s+(\S+)\s+(\S+)\s+(\S+)')
        for line in data.decode('ascii', errors='ignore').splitlines():
            m = pat.search(line)
            if m:
                x, y, z = map(float, m.groups())
                xs.append(x); ys.append(y); zs.append(z)
    else:
        # 二进制：80B 头 + uint32 面数 + 每面 50B（12 float32 + uint16）
        n = struct.unpack_from('<I', data, 80)[0]
        if 84 + n * 50 > len(data):
            raise ValueError(f'STL 长度与面数不符: {path}')
        for i in range(n):
            off = 84 + i * 50 + 12  # 跳过法向量
            vx, vy, vz, wx, wy, wz, ux, uy, uz = struct.unpack_from(
                '<9f', data, off)
            xs += (vx, wx, ux); ys += (vy, wy, uy); zs += (vz, wz, uz)
    if not xs:
        raise ValueError(f'STL 无顶点: {path}')
    return min(xs), max(xs), min(ys), max(ys), min(zs), max(zs)


def find_stl(case):
    cands = [
        os.path.join(case, '..', 'geometry', 'model.stl'),
        os.path.join(case, 'constant', 'triSurface', 'body.stl'),
    ]
    for c in cands:
        if os.path.exists(c):
            return os.path.abspath(c)
    raise SystemExit('[hd] 未找到 STL 几何')


case = os.path.abspath(CASE)
foam = os.path.join(case, 'case.foam')
if not os.path.exists(foam):
    open(foam, 'w').close()  # 空标记文件即可让 reader 打开算例
print('[hd] case =', case)

stl = find_stl(case)
x0, x1, y0, y1, z0, z1 = stl_bbox(stl)
L, W, H = x1 - x0, y1 - y0, z1 - z0
cx, cy = 0.5 * (x0 + x1), 0.5 * (y0 + y1)
print(f'[hd] bbox L={L:.2f} W={W:.2f} H={H:.2f}')

# ---------- 全场读取 -> 点数据化
vol = OpenFOAMReader()
setp(vol, ('FileName', 'CasePath'), foam)
vol.UpdatePipeline()
c2p = CellDatatoPointData(Input=vol)
try:
    c2p.ProcessAllArrays = 1
except Exception:
    pass
c2p.UpdatePipeline()

scene = GetAnimationScene()
ts = vol.TimestepValues
if ts and len(ts) > 1:
    scene.AnimationTime = ts[-1]

# ---------- 自适应量程
if UFREE is None:
    UFREE = 40.0
UMAX = 1.08 * UFREE

# ---------- 显式 OpenGL 视图（VisRTX 后端画不出线/半透明，必须绕开）
try:
    view = CreateView('RenderView')
    SetActiveView(view)
    print('[hd] view = RenderView (OpenGL)')
except Exception as e:
    from paraview.simple import GetActiveView
    view = GetActiveView()
    print('[hd] fallback view:', e)

# ---------- 车体（STL 深漆）
body = STLReader()
setp(body, ('FileName', 'FileNames'), stl)
body.UpdatePipeline()
bd = Show(body, view)
setp(bd, ('DiffuseColor', 'diffuse_color'), [0.62, 0.07, 0.07])
setp(bd, ('Specular', 'specular'), 0.55)
setp(bd, ('SpecularPower', 'specular_power'), 40)

# ---------- 地面（域底切片，不透明深色，任何后端都可见）
gsl = Slice(Input=c2p)
gsl.SliceType = 'Plane'
setp(gsl.SliceType, ('Origin', 'origin'), [cx, cy, z0 + 0.002])
setp(gsl.SliceType, ('Normal', 'normal'), [0.0, 0.0, 1.0])
gsd = Show(gsl, view)
setp(gsd, ('DiffuseColor', 'diffuse_color'), [0.30, 0.31, 0.34])
setp(gsd, ('Ambient', 'ambient'), 0.35)

# ---------- 烟线：StreamTracer -> Tube（不透明圆管，Fluent 烟线风格）
def make_smoke(p1, p2, nres):
    st = StreamTracer(Input=c2p, SeedType='Line')
    sd = st.SeedType
    setp(sd, ('Point1', 'point1'), p1)
    setp(sd, ('Point2', 'point2'), p2)
    setp(sd, ('Resolution', 'resolution'), nres)
    setp(st, ('MaximumNumberOfSteps', 'maximum_number_of_steps'), 6000)
    setp(st, ('InitialStepLength', 'initial_step_length'), 0.002)
    setp(st, ('MaximumStepLength', 'maximum_step_length'), 0.02)
    setp(st, ('TerminalSpeed', 'terminal_speed'), 1e-3)
    tb = Tube(Input=st)
    setp(tb, ('Radius', 'radius'), 0.0038)
    setp(tb, ('NumberOfSides', 'number_of_sides'), 8)
    disp = Show(tb, view)
    try:
        ColorBy(disp, ('POINTS', 'U', 'Magnitude'))
    except Exception:
        ColorBy(disp, ('POINTS', 'U'))
    return disp

xs_up = x0 - 0.35 * L           # 上游烟线源
disp_mid = make_smoke((xs_up, cy, z0 + 0.015 * H),
                      (xs_up, cy, z1 + 0.45 * H), 20)
disp_lo = make_smoke((xs_up, y0 + 0.10 * W, z0 + 0.06 * H),
                     (xs_up, y1 - 0.10 * W, z0 + 0.06 * H), 24)
disp_hi = make_smoke((xs_up, y0 + 0.14 * W, z0 + 0.38 * H),
                     (xs_up, y1 - 0.14 * W, z0 + 0.38 * H), 20)

# ---------- 中心纵剖切片（不透明浅色衬底，避免半透明兼容性问题）
sl = Slice(Input=c2p)
sl.SliceType = 'Plane'
setp(sl.SliceType, ('Origin', 'origin'), [cx, cy, 0.45 * H])
setp(sl.SliceType, ('Normal', 'normal'), [0.0, 1.0, 0.0])
sd_ = Show(sl, view)
try:
    ColorBy(sd_, ('POINTS', 'U', 'Magnitude'))
except Exception:
    ColorBy(sd_, ('POINTS', 'U'))

# ---------- 统一色表
lut = GetColorTransferFunction('U')
lut.ApplyPreset('Cool to Warm (Extended)', False)
lut.RescaleTransferFunction(0.0, UMAX)
for d in (disp_mid, disp_lo, disp_hi, sd_):
    try:
        d.LookupTable = lut
    except Exception:
        pass

bar = GetScalarBar(lut, view)
bar.Title = 'U (m/s)'
bar.TitleFontSize = 20
bar.LabelFontSize = 15
setp(bar, ('ComponentTitle', 'component_title'), '')
bar.Visibility = 1

# ---------- 视图外观
ok_bg = setp(view, ('Background', 'background'), [0.93, 0.94, 0.96])
print('[hd] background set:', ok_bg)
try:
    view.UseFXAA = 1
except Exception:
    pass


def cam_shot(pos_off, zoom, fname):
    cam = view.GetActiveCamera()
    cam.SetFocalPoint(cx, cy, 0.42 * H)
    cam.SetPosition(cx + pos_off[0], cy + pos_off[1], 0.42 * H + pos_off[2])
    cam.SetViewUp(0.0, 0.0, 1.0)
    try:
        cam.SetViewAngle(32.0)
    except Exception:
        pass
    try:
        cam.Zoom(zoom)
    except Exception:
        pass
    Render(view)
    out = os.path.join(case, 'results', fname)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    SaveScreenshot(out, view, ImageResolution=[2400, 1350])
    print('[hd] saved:', out)


cam_shot((1.35 * L, -1.75 * W, 0.55 * H), 1.30, 'streamline_hd_front.png')
cam_shot((1.55 * L, -0.95 * W, 1.35 * H), 1.25, 'streamline_hd_wake.png')
cam_shot((0.05 * L, -3.1 * W, 0.28 * H), 1.22, 'streamline_hd_side.png')
