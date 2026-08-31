from __future__ import annotations
import math, re
from pathlib import Path
from typing import Iterable, Sequence
from ..core.models import BoundingBox

def _normal(a,b,c):
    u=[b[i]-a[i] for i in range(3)]; v=[c[i]-a[i] for i in range(3)]
    n=(u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0]); d=math.sqrt(sum(x*x for x in n)) or 1
    return tuple(x/d for x in n)
def write_ascii_stl(path, triangles: Iterable[Sequence[Sequence[float]]], name='aeroforge'):
    p=Path(path); p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('w',encoding='ascii') as f:
        f.write(f'solid {name}\n')
        for tri in triangles:
            a,b,c=[tuple(float(x) for x in q[:3]) for q in tri]; n=_normal(a,b,c)
            f.write(f' facet normal {n[0]:.8g} {n[1]:.8g} {n[2]:.8g}\n  outer loop\n')
            for q in (a,b,c): f.write(f'   vertex {q[0]:.8g} {q[1]:.8g} {q[2]:.8g}\n')
            f.write('  endloop\n endfacet\n')
        f.write(f'endsolid {name}\n')
    return p.resolve()
def _quad(t,a,b,c,d): t.extend(((a,b,c),(a,c,d)))
def cylinder_triangles(radius=.5,height=1,segments=32):
    t=[]
    for i in range(segments):
        a=2*math.pi*i/segments; b=2*math.pi*(i+1)/segments
        p=(radius*math.cos(a),radius*math.sin(a),0); q=(radius*math.cos(b),radius*math.sin(b),0)
        r=(q[0],q[1],height); s=(p[0],p[1],height); _quad(t,p,q,r,s); t.extend((((0,0,0),q,p),((0,0,height),s,r)))
    return t
def create_cylinder_stl(path,radius=.5,height=1,segments=32): return write_ascii_stl(path,cylinder_triangles(radius,height,segments),'cylinder')
def naca4_coordinates(code='0012',points=80):
    if not re.fullmatch(r'\d{4}',str(code)): raise ValueError('NACA code must be four digits')
    m,p,t=int(code[0])/100,int(code[1])/10,int(code[2:])/100; xs=[(1-math.cos(math.pi*i/(points-1)))/2 for i in range(points)]; up=[]; lo=[]
    for x in xs:
        yt=5*t*(.2969*math.sqrt(x)-.126*x-.3516*x*x+.2843*x**3-.1015*x**4)
        if m and p and x<p: yc=m/p**2*(2*p*x-x*x); dy=2*m/p**2*(p-x)
        elif m and p: yc=m/(1-p)**2*((1-2*p)+2*p*x-x*x); dy=2*m/(1-p)**2*(p-x)
        else: yc=dy=0
        th=math.atan(dy); up.append((x-yt*math.sin(th),yc+yt*math.cos(th))); lo.append((x+yt*math.sin(th),yc-yt*math.cos(th)))
    return list(reversed(up))+lo[1:-1]
def create_naca_stl(path,code='0012',chord=1,span=.02,points=80):
    prof=[(x*chord,y*chord) for x,y in naca4_coordinates(code,points)]; t=[]
    # 闭合尾缘；原实现只连接相邻点，留下 upper/lower trailing-edge 的
    # 6 条单边，surfaceCheck 会把翼型判为 open surface。
    profile_edges = zip(prof, prof[1:] + prof[:1])
    for a,b in profile_edges: _quad(t,(a[0],a[1],-span/2),(b[0],b[1],-span/2),(b[0],b[1],span/2),(a[0],a[1],span/2))
    for z in (-span/2,span/2):
        c=(sum(x for x,y in prof)/len(prof),sum(y for x,y in prof)/len(prof),z)
        for a,b in zip(prof, prof[1:] + prof[:1]):
            # x-y 轮廓为 CCW：上端盖法向 +z，下端盖需反转为 -z。
            t.append((c,(a[0],a[1],z),(b[0],b[1],z)) if z > 0
                     else (c,(b[0],b[1],z),(a[0],a[1],z)))
    return write_ascii_stl(path,t,'naca'+str(code))
def car_triangles(length=4.7,width=1.9,height=1.7,ground_clearance=0.12):
    if length <= 0 or width <= 0 or height <= 0 or ground_clearance < 0:
        raise ValueError('car dimensions must be positive and ground_clearance non-negative')
    L,W=length/2,width/2
    z0=ground_clearance; z=ground_clearance + height*.48; z_top=ground_clearance + height
    # 车身与座舱必须构成一个联合边界。旧实现把两个完整盒子叠在一起，
    # surfaceCheck 会报告两个 disconnected parts，snappy 可能把内部重叠面
    # 当成额外壁面。这里去掉接口底面并用矩形环连接，保留一个封闭壳体。
    lower = [(-L,-W,z0),(L,-W,z0),(L,W,z0),(-L,W,z0),
             (-L,-W,z),(L,-W,z),(L,W,z),(-L,W,z)]
    inner = [(-L*.42,-W*.78,z),(L*.42,-W*.78,z),
             (L*.42,W*.78,z),(-L*.42,W*.78,z)]
    top = [(-L*.32,-W*.65,z_top),(L*.32,-W*.65,z_top),
           (L*.32,W*.65,z_top),(-L*.32,W*.65,z_top)]
    t=[]
    # 车身底面与四个侧面（顶面由下面的环补齐）
    for ids in ((0,3,2,1),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)):
        _quad(t,*[lower[i] for i in ids])
    # 车身顶部环：外圈与座舱底圈共用精确顶点
    outer = lower[4:8]
    for a,b,c,d in ((outer[0],outer[1],inner[1],inner[0]),
                    (outer[1],outer[2],inner[2],inner[1]),
                    (outer[2],outer[3],inner[3],inner[2]),
                    (outer[3],outer[0],inner[0],inner[3])):
        _quad(t,a,b,c,d)
    # 座舱四侧与车顶，不再生成隐藏的底面
    for a,b,c,d in ((inner[0],inner[1],top[1],top[0]),
                    (inner[1],inner[2],top[2],top[1]),
                    (inner[2],inner[3],top[3],top[2]),
                    (inner[3],inner[0],top[0],top[3])):
        _quad(t,a,b,c,d)
    _quad(t,*top)
    return t
def create_car_stl(path,length=4.7,width=1.9,height=1.7,ground_clearance=0.12):
    return write_ascii_stl(path,car_triangles(length,width,height,ground_clearance),'car')
def generate_geometry(kind,output_path,**kwargs):
    k=str(kind).lower().replace('-','_')
    if k in ('car','automobile'): return create_car_stl(output_path,**kwargs)
    if k in ('naca','airfoil','naca4'): return create_naca_stl(output_path,**kwargs)
    if k in ('cylinder','cyl'): return create_cylinder_stl(output_path,**kwargs)
    raise ValueError(f'unsupported geometry kind: {kind}')
def validate_stl(stl_path):
    # 统一走 stl_tools 的 ASCII/binary 解析器；旧实现只读 ASCII，
    # 上传常见的 binary STL 会被误报为空几何。
    from .stl_tools import read_stl_bbox
    return read_stl_bbox(Path(stl_path))
def bbox_diagonal(bbox): return math.sqrt((bbox.x_max-bbox.x_min)**2+(bbox.y_max-bbox.y_min)**2+(bbox.z_max-bbox.z_min)**2)
generate_car_stl=create_car_stl; generate_naca_stl=create_naca_stl; generate_cylinder_stl=create_cylinder_stl
