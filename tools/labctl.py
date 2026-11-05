"""Shim so labctl runs from a checkout without installing: python -X utf8 tools/labctl.py <cmd>"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from academy_server.labctl import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
