# -*- coding: utf-8 -*-
"""从 latestTime 继续瞬态 pimpleFoam 计算（中断恢复用）。

把 controlDict 的 startFrom 改为 latestTime 后继续求解到 endTime，
已有的时间帧保留，ParaView 时间轴自动接上。

用法：pvpython 不需要；直接
    python examples/resume_transient.py [--task task_XXXX]
"""
import argparse
import glob
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'src'))

from aeroforge.core.runtime_bridge import RuntimeBridge  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--task', default=None)
    args = ap.parse_args()

    ws = Path('workspace')
    if args.task:
        case = ws / args.task / 'case'
    else:
        cands = [p for p in ws.glob('task_*') if (p / 'case' / 'log.pimpleFoam').exists()]
        if not cands:
            print('[resume] 未找到跑过 pimpleFoam 的算例')
            return 2
        case = max(cands, key=lambda p: p.stat().st_mtime) / 'case'

    ctrl = case / 'system' / 'controlDict'
    text = ctrl.read_text(encoding='utf-8')
    text = re.sub(r'startFrom\s+\w+;', 'startFrom       latestTime;', text)
    ctrl.write_text(text, encoding='utf-8')
    print('[resume] case =', case, '（startFrom latestTime）')

    bridge = RuntimeBridge()
    if not bridge.available:
        print('[resume] 无 OpenFOAM 运行时')
        return 2
    res = bridge.run(['pimpleFoam'], cwd=case, timeout=14400)
    print('[resume] pimpleFoam rc =', res.get('returncode'))
    return 0 if res.get('returncode') == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
