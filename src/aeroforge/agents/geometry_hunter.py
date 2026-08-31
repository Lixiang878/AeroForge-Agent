import hashlib
import re
import shutil
from pathlib import Path
from ..core.models import GeometryInfo, ModelAssetManifest
from ..tools.geometry_tools import create_car_stl,create_cylinder_stl,create_naca_stl,bbox_diagonal
from ..tools.stl_tools import ahmed_body_stl,is_watertight,prepare_stl_for_cfd,read_stl_bbox

_PRODUCTION_VEHICLE_BRANDS = (
    '宝马', 'bmw', '奔驰', 'mercedes', '奥迪', 'audi', '大众', 'volkswagen',
    '丰田', 'toyota', '本田', 'honda', '日产', 'nissan', '特斯拉', 'tesla',
    '比亚迪', 'byd', '蔚来', 'nio', '小鹏', 'xpeng', '问界', 'aito',
    '极氪', 'zeekr', '保时捷', 'porsche', '福特', 'ford', '雪佛兰',
    '凯迪拉克', '沃尔沃', 'volvo', '红旗', '长安', '吉利', '长城',
    '奇瑞', '理想', 'li auto',
)


def _canonical_brand(value: str) -> str:
    compact = re.sub(r"[^a-z0-9\u4e00-\u9fff]", "", value.lower())
    aliases = (
        ('bmw', '宝马'), ('audi', '奥迪'), ('volkswagen', '大众', 'vw'),
        ('xpeng', '小鹏'), ('liauto', '理想'), ('aito', '问界'),
        ('mercedes', '奔驰'), ('toyota', '丰田'), ('honda', '本田'),
        ('nissan', '日产'), ('tesla', '特斯拉'), ('byd', '比亚迪'),
        ('nio', '蔚来'), ('zeekr', '极氪'), ('porsche', '保时捷'),
        ('ford', '福特'), ('volvo', '沃尔沃'),
    )
    for group in aliases:
        if any(alias in compact for alias in group):
            return group[0]
    return compact


class GeometryHunterAgent:
    """获取并预检几何：参数化基准或水密真实 STL，输出单区域 STL + 包围盒。"""
    async def run(self, parsed, **kwargs):
        task=parsed['task']; out=Path(kwargs.get('workspace','workspace'))/task.task_id/'geometry'/'model.stl'; out.parent.mkdir(parents=True,exist_ok=True)
        name=task.object_name.lower()
        is_production_vehicle = any(brand in name for brand in _PRODUCTION_VEHICLE_BRANDS)
        manifest_copy = None
        if task.upload_stl_path:
            if is_production_vehicle and not kwargs.get('model_manifest_path'):
                raise ValueError(
                    f'具体车型“{task.object_name}”必须提供可追溯的模型资产清单 '
                    '(--model-manifest)。')
            upload = Path(task.upload_stl_path)
            if not upload.exists():
                raise FileNotFoundError(f'上传的 STL 不存在: {upload}')
            manifest_path = kwargs.get('model_manifest_path')
            manifest = None
            if manifest_path:
                manifest_source = Path(manifest_path)
                if not manifest_source.exists():
                    raise FileNotFoundError(f'模型资产清单不存在: {manifest_source}')
                manifest = ModelAssetManifest.model_validate_json(
                    manifest_source.read_text(encoding='utf-8'))
                digest = hashlib.sha256()
                with upload.open('rb') as handle:
                    for chunk in iter(lambda: handle.read(1024 * 1024), b''):
                        digest.update(chunk)
                if digest.hexdigest().lower() != manifest.source_sha256.lower():
                    raise ValueError('模型资产清单 SHA-256 与上传文件不一致')
                if is_production_vehicle:
                    requested_brand = next(
                        brand for brand in _PRODUCTION_VEHICLE_BRANDS if brand in name)
                    model_key = re.sub(r'[^a-z0-9\u4e00-\u9fff]', '', manifest.model.lower())
                    requested_key = re.sub(r'[^a-z0-9\u4e00-\u9fff]', '', name)
                    if (_canonical_brand(requested_brand) != _canonical_brand(manifest.manufacturer)
                            or model_key not in requested_key):
                        raise ValueError(
                            f'请求车型 {task.object_name} 与资产清单 '
                            f'{manifest.manufacturer} {manifest.model} 不一致')
                if manifest.source_format.strip().lower() != 'stl':
                    raise ValueError('当前 CFD 导入只支持 source_format=STL')
                if (manifest.forward_axis.upper(), manifest.up_axis.upper()) != ('-X', '+Z'):
                    raise ValueError(
                        '模型资产清单轴向必须为 forward_axis=-X、up_axis=+Z；'
                        '车头应位于上游 x_min，自由流沿 +X，请先统一轴向。')
                if not manifest.derivatives_allowed:
                    raise ValueError('模型许可证未允许为 CFD 进行转换/派生处理')
                manifest_copy = out.parent / 'model_manifest.json'
                shutil.copy2(manifest_source, manifest_copy)
            if not is_watertight(upload):
                raise ValueError(f'STL 必须是封闭表面，无法进入网格阶段: {upload}')
            target_ground = kwargs.get('upload_ground_clearance')
            unit_scale = {'m': 1.0, 'cm': 0.01, 'mm': 0.001}
            units = manifest.units.strip().lower() if manifest else 'm'
            if units not in unit_scale:
                raise ValueError(f'不支持的模型单位: {units}（仅支持 m/cm/mm）')
            requested_scale = kwargs.get('upload_scale')
            scale = (unit_scale[units] if requested_scale is None
                     else float(requested_scale))
            if (manifest and requested_scale is not None
                    and abs(scale - unit_scale[units]) > 1e-12):
                raise ValueError(
                    f'--upload-scale={scale:g} 与资产清单 units={manifest.units} 不一致')
            rotation_z_deg = float(kwargs.get('upload_rotation_z_deg', 0.0))
            bbox = prepare_stl_for_cfd(
                upload,
                out,
                target_ground_z=(float(target_ground)
                                 if target_ground is not None else None),
                scale=scale,
                rotation_z_deg=rotation_z_deg,
            )
            source = (f'{manifest.manufacturer} {manifest.model} '
                      f'({manifest.license_id})' if manifest else
                      str(kwargs.get('geometry_source_label', 'upload')))
        elif 'ahmed' in name:
            slant=25.0
            import re as _re
            m=_re.search(r'(\d+(?:\.\d+)?)\s*(?:°|度|deg)',task.object_name)
            if m: slant=float(m.group(1))
            ahmed_body_stl(out,slant_angle_deg=slant); source=f'parametric_ahmed_{slant:g}deg'
        elif 'naca' in name: create_naca_stl(out); source='parametric_naca'
        elif 'cylinder' in name: create_cylinder_stl(out); source='parametric_cylinder'
        elif is_production_vehicle:
            raise ValueError(
                f'具体车型“{task.object_name}”需要用户提供有授权且封闭的 STL；'
                '不会再静默替换为简化方块车。')
        else: create_car_stl(out); source='parametric_simplified_car'
        if not task.upload_stl_path:
            bbox=read_stl_bbox(out)
            if not is_watertight(out):
                raise ValueError(f'STL 必须是封闭表面，无法进入网格阶段: {out}')
        return {'status':'completed','geometry':GeometryInfo(stl_path=out,bbox=bbox,characteristic_length=bbox_diagonal(bbox),source=source,manifest_path=manifest_copy)}
GeometryHunter=GeometryHunterAgent
