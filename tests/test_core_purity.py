"""core/ must stay UI-free: no streamlit/plotly imports (design principle 6.1-1)."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "core"
FORBIDDEN = re.compile(r"^\s*(import|from)\s+(streamlit|plotly)\b", re.MULTILINE)


def test_core_sources_do_not_import_ui_libs():
    offenders = [
        str(p.relative_to(ROOT))
        for p in CORE.rglob("*.py")
        if FORBIDDEN.search(p.read_text(encoding="utf-8"))
    ]
    assert offenders == []


def test_importing_core_does_not_load_ui_libs():
    # Fresh interpreter: import every core module, then inspect sys.modules.
    # Import errors of other agents' in-progress modules are ignored here (their own tests cover them).
    code = (
        "import importlib, pkgutil, sys\n"
        "import core, core.models\n"
        "for m in pkgutil.walk_packages(core.__path__, 'core.'):\n"
        "    try:\n"
        "        importlib.import_module(m.name)\n"
        "    except Exception:\n"
        "        pass\n"
        "bad = sorted(k for k in sys.modules if k.split('.')[0] in ('streamlit', 'plotly'))\n"
        "print(','.join(bad))\n"
    )
    out = subprocess.run(
        [sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, timeout=120, check=True
    )
    assert out.stdout.strip() == ""
