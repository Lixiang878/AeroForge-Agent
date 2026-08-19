import asyncio
import pytest
from aeroforge.agents import RequirementParserAgent
@pytest.mark.parametrize('text,velocity,regime',[('风速 30 km/h 稳态',8.333333,'steady'),('velocity 10 m/s transient',10,'transient'),('内流 2 m/s',2,'steady'),('external 5 m/s steady',5,'steady'),('没有速度',1,'steady')])
def test_parser(text,velocity,regime):
 r=asyncio.run(RequirementParserAgent().run(text)); assert r['task'].velocity==pytest.approx(velocity); assert r['task'].regime.value==regime
