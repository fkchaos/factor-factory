"""pytest 根 conftest：把项目根加入 sys.path，使 `import factors/data/engine` 可用。"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
