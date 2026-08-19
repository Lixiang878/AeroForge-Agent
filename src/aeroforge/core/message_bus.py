from __future__ import annotations
import asyncio, uuid
from dataclasses import dataclass, field
from typing import Any
@dataclass
class Message:
    topic: str; payload: Any; sender: str = "system"; recipient: str | None = None; correlation_id: str = field(default_factory=lambda: uuid.uuid4().hex)
class MessageBus:
    def __init__(self):
        self.queues: dict[str, asyncio.Queue[Message]] = {}; self.log: list[Message] = []
    def register(self, name: str) -> asyncio.Queue[Message]:
        return self.queues.setdefault(name, asyncio.Queue())
    async def send(self, message: Message) -> None:
        self.log.append(message)
        if message.recipient is None: await self.broadcast(message)
        elif message.recipient in self.queues: await self.queues[message.recipient].put(message)
    async def broadcast(self, message: Message) -> None:
        for queue in self.queues.values(): await queue.put(message)
    async def request(self, sender: str, recipient: str, topic: str, payload: Any, timeout: float = 30.0) -> Message:
        correlation = uuid.uuid4().hex; await self.send(Message(topic, payload, sender, recipient, correlation))
        queue = self.register(sender)
        while True:
            msg = await asyncio.wait_for(queue.get(), timeout)
            if msg.correlation_id == correlation: return msg
    async def receive(self, name: str, timeout: float | None = None) -> Message:
        queue = self.register(name)
        return await asyncio.wait_for(queue.get(), timeout) if timeout else await queue.get()
