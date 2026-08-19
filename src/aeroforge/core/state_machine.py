from __future__ import annotations
import json
from enum import Enum
from pathlib import Path
class State(str, Enum):
    PENDING="PENDING"; PARSING="PARSING"; GEOMETRY="GEOMETRY"; MESH="MESH"; CONFIG="CONFIG"; RUNNING="RUNNING"; POST="POST"; COMPLETED="COMPLETED"; FAILED="FAILED"
_TRANSITIONS={State.PENDING:{State.PARSING},State.PARSING:{State.GEOMETRY,State.FAILED},State.GEOMETRY:{State.MESH,State.FAILED},State.MESH:{State.CONFIG,State.FAILED},State.CONFIG:{State.RUNNING,State.FAILED},State.RUNNING:{State.POST,State.FAILED},State.POST:{State.COMPLETED,State.FAILED}}
class StateMachine:
    def __init__(self, state: State=State.PENDING): self.state=state
    def transition(self, target: State):
        if target not in _TRANSITIONS.get(self.state,set()) and target != self.state: raise ValueError(f"非法状态迁移: {self.state} -> {target}")
        self.state=target; return self.state
    def save(self,path:Path): path.write_text(json.dumps({'state':self.state.value},ensure_ascii=False),encoding='utf-8')
    @classmethod
    def load(cls,path:Path): return cls(State(json.loads(path.read_text(encoding='utf-8'))['state']))
