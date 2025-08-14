"""Environment hygiene checks for development and CI.

Run manually or integrate into CI to ensure we are using the intended virtualenv
and that required runtime deps (like python-multipart) are importable.

Exit codes:
 0 - all checks passed
 1 - failed (prints reasons)
"""
from __future__ import annotations
import os, sys, importlib, textwrap

REQUIRED_IMPORTS = [
    ("multipart", "Install python-multipart (pip install python-multipart)"),
]

ALLOWED_VENV_MARKERS = [os.sep + '.venv' + os.sep]

def in_expected_venv() -> bool:
    exe = sys.executable
    # Accept running under a path containing .venv segment
    return any(marker in exe for marker in ALLOWED_VENV_MARKERS)

def main() -> int:
    errors = []
    if not in_expected_venv():
        errors.append(f"Interpreter {sys.executable} does not appear to be from project .venv")
    for mod, help_text in REQUIRED_IMPORTS:
        try:
            importlib.import_module(mod)
        except Exception as e:
            errors.append(f"Cannot import {mod}: {e}. {help_text}")
    if errors:
        print("Environment check FAILED:\n" + "\n".join(" - " + e for e in errors))
        return 1
    print("Environment check OK.")
    print(f"Python: {sys.version}")
    print(f"Executable: {sys.executable}")
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
