"""バージョン番号を出す（package.bat が使う）"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import svwb  # noqa: E402

print(svwb.__version__)
