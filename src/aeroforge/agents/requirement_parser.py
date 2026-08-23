from __future__ import annotations
import re
from pathlib import Path
from ..core.models import SimulationTask, FlowType, Regime
_STRIP_WORDS = ("做|一[辆个款只]|仿真|模拟|测试|计算|CFD|风洞|稳态|瞬态|不可压|工况|可视化|流线|图|一下|的|进行|情况|条件下|给|我|请|帮忙|风速|风向")
# 车型/物体关键词：命中即作为对象名核心（覆盖常见真实诉求）
_OBJ_KW = (r"(?:Ahmed(?:\s*body)?|NACA\s?\d{3,4}|圆柱|圆球|球体|方块|方柱|翼型|圆柱绕流|球绕流"
           r"|宝马|奔驰|奥迪|大众|丰田|本田|日产|特斯拉|Tesla|比亚迪|蔚来|小鹏|问界|极氪"
           r"|保时捷|Porsche|福特|雪佛兰|凯迪拉克|沃尔沃|红旗|长安|吉利|长城|奇瑞|理想ONE|car|cylinder|sphere)")


def _extract_object_name(text: str) -> str:
    """对象名三级提取：引号 > 关键词词典 > 去停用词兜底。"""
    om = re.search(r"[\"“”']([^\"“”']+)[\"“”']", text)
    if om:
        return om.group(1).strip()
    km = re.search(rf"{_OBJ_KW}[\w\-]*", text)
    if km:
        name = km.group(0).strip()
        m2 = re.match(r"\s+([A-Za-z0-9][\w\-]*)", text[km.end():])
        if m2 and re.search(r"[\u4e00-\u9fff]", name):
            name += m2.group(1)  # 中文关键词后跟型号：'宝马 X3' -> '宝马X3'
        # 中文与字母数字之间的空格合并（'Ahmed body' 保持原样）
        name = re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[A-Za-z0-9])|(?<=[A-Za-z0-9])\s+(?=[\u4e00-\u9fff])", "", name)
        return name
    t = re.sub(r"[0-9]+(?:\.[0-9]+)?\s*(?:km/h|m/s|°|度|deg|米|米每秒)", " ", text)
    t = re.sub(r"(?:风向角|迎风角|迎风|偏航|攻角|yaw)\s*[0-9.]+\s*(?:°|度|deg)", " ", t, flags=re.I)
    t = re.sub(_STRIP_WORDS, " ", t)
    return re.sub(r"\s+", " ", t).strip(" ，。,.") or "generic object"


class RequirementParserAgent:
    """自然语言 → 结构化任务。支持：对象名（引号/车型关键词/裸文本）、
    风速（m/s / km/h）、风向角（迎风/偏航 N°）、内流/瞬态关键词、STL 上传透传。"""
    async def run(self, prompt, **kwargs):
        text=str(prompt); warnings=[]
        vm=re.search(r"([0-9]+(?:\.[0-9]+)?)\s*(km/h|m/s)", text, re.I)
        velocity=float(vm.group(1))/3.6 if vm and vm.group(2).lower()=="km/h" else (float(vm.group(1)) if vm else 1.0)
        if not vm: warnings.append("未识别速度，使用 1.0 m/s")
        object_name=_extract_object_name(text)
        flow=FlowType.INTERNAL_FLOW if re.search(r"内流|管道|internal",text,re.I) else FlowType.EXTERNAL_AERODYNAMICS
        regime=Regime.TRANSIENT if re.search(r"瞬态|非定常|transient",text,re.I) else Regime.STEADY
        yaw=0.0
        ym=(re.search(r"(?:风向角|迎风角|迎风|偏航|攻角|yaw)[^0-9]{0,6}([0-9]+(?:\.[0-9]+)?)\s*(?:°|度|deg)",text,re.I)
            or re.search(r"([0-9]+(?:\.[0-9]+)?)\s*(?:°|度|deg)\s*(?:风向|迎风|偏航)",text,re.I))
        if ym: yaw=float(ym.group(1))
        upload=kwargs.get('upload_stl_path')
        return {"status":"completed","task":SimulationTask(user_prompt=text,object_name=object_name,velocity=velocity,
                                                            yaw_angle_deg=yaw,flow_type=flow,regime=regime,
                                                            upload_stl_path=Path(upload) if upload else None),"warnings":warnings}
RequirementParser=RequirementParserAgent
