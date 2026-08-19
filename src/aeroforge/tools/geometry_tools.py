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
    for a,b in zip(prof,prof[1:]): _quad(t,(a[0],a[1],-span/2),(b[0],b[1],-span/2),(b[0],b[1],span/2),(a[0],a[1],span/2))
    for z in (-span/2,span/2):
        c=(sum(x for x,y in prof)/len(prof),sum(y for x,y in prof)/len(prof),z)
        for a,b in zip(prof,prof[1:]): t.append((c,(a[0],a[1],z),(b[0],b[1],z)))
    return write_ascii_stl(path,t,'naca'+str(code))
def car_triangles(length=4.7,width=1.9,height=1.7):
    L,W=length/2,width/2; z=height*.48; t=[]
    for box in [[(-L,-W,0),(L,-W,0),(L,W,0),(-L,W,0),(-L,-W,z),(L,-W,z),(L,W,z),(-L,W,z)],[(-L*.42,-W*.78,z),(L*.42,-W*.78,z),(L*.42,W*.78,z),(-L*.42,W*.78,z),(-L*.32,-W*.65,height),(L*.32,-W*.65,height),(L*.32,W*.65,height),(-L*.32,W*.65,height)]]:
        for ids in ((0,1,2,3),(4,7,6,5),(0,4,5,1),(1,5,6,2),(2,6,7,3),(3,7,4,0)): _quad(t,*[box[i] for i in ids])
    return t
def create_car_stl(path,length=4.7,width=1.9,height=1.7): return write_ascii_stl(path,car_triangles(length,width,height),'car')
def generate_geometry(kind,output_path,**kwargs):
    k=str(kind).lower().replace('-','_')
    if k in ('car','automobile'): return create_car_stl(output_path,**kwargs)
    if k in ('naca','airfoil','naca4'): return create_naca_stl(output_path,**kwargs)
    if k in ('cylinder','cyl'): return create_cylinder_stl(output_path,**kwargs)
    raise ValueError(f'unsupported geometry kind: {kind}')
def validate_stl(stl_path):
    p=Path(stl_path); text=p.read_text(encoding='ascii',errors='ignore'); verts=[]
    for line in text.splitlines():
        m=re.search(r'vertex\s+([-+\deE.]+)\s+([-+\deE.]+)\s+([-+\deE.]+)',line)
        if m: verts.append(tuple(float(x) for x in m.groups()))
    if not verts: raise ValueError(f'No STL vertices found: {p}')
    xs,ys,zs=zip(*verts); bbox=BoundingBox(x_min=min(xs),x_max=max(xs),y_min=min(ys),y_max=max(ys),z_min=min(zs),z_max=max(zs))
    return bbox
def bbox_diagonal(bbox): return math.sqrt((bbox.x_max-bbox.x_min)**2+(bbox.y_max-bbox.y_min)**2+(bbox.z_max-bbox.z_min)**2)
generate_car_stl=create_car_stl; generate_naca_stl=create_naca_stl; generate_cylinder_stl=create_cylinder_stl
