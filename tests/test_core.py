import asyncio
from aeroforge.core import MessageBus,State,StateMachine
from aeroforge.core.message_bus import Message
def test_bus():
 async def run():
  b=MessageBus(); b.register('x'); await b.send(Message('t',1,recipient='x')); return (await b.receive('x')).payload
 assert asyncio.run(run())==1
def test_state():
 s=StateMachine(); s.transition(State.PARSING); assert s.state==State.PARSING
