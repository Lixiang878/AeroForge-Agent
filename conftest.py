"""共享测试配置。"""
from pathlib import Path


def pytest_configure(config):
    # pytest.ini 的 --basetemp 指向 workspace/_scratch/pytest；workspace 整体被
    # .gitignore 排除，干净 checkout（CI/新克隆）里父目录不存在会导致所有
    # tmp_path 用例在 setup 阶段 FileNotFoundError。这里先建好。
    basetemp = config.getoption("--basetemp")
    if basetemp:
        Path(basetemp).mkdir(parents=True, exist_ok=True)
