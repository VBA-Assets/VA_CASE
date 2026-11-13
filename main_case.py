"""VA Case の起動スクリプト（ソースから使うとき。Mac もこれで起動する）。

使い方：python main_case.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from va_case.case.app import main  # noqa: E402

if __name__ == "__main__":
    main()
