import asyncio
import pytest
from aeroforge.agents import RequirementParserAgent
@pytest.mark.parametrize('text,velocity,regime',[('风速 30 km/h 稳态',8.333333,'steady'),('velocity 10 m/s transient',10,'transient'),('内流 2 m/s',2,'steady'),('external 5 m/s steady',5,'steady'),('没有速度',1,'steady')])
def test_parser(text,velocity,regime):
 r=asyncio.run(RequirementParserAgent().run(text)); assert r['task'].velocity==pytest.approx(velocity); assert r['task'].regime.value==regime
@pytest.mark.parametrize('text,name,yaw',[
 ('做一辆 宝马X3 的迎风测试，风速 30 km/h','宝马X3',0),
 ('宝马X3 迎风 风速40m/s 风向角30度','宝马X3',30),
 ('Ahmed body 迎风 40 m/s 偏航 15°','Ahmed body',15),
 ('"圆柱绕流" 2 m/s','圆柱绕流',0)])
def test_object_name_and_yaw(text,name,yaw):
 r=asyncio.run(RequirementParserAgent().run(text)); t=r['task']
 assert t.object_name==name; assert t.yaw_angle_deg==pytest.approx(yaw)
