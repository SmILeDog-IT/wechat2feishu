#!/usr/bin/env python3
"""Build the standalone Windows desktop app using the active Python environment."""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys


def main() -> int:
    if sys.platform != "win32":
        raise SystemExit("Build this Windows EXE on Windows.")
    if importlib.util.find_spec("PyInstaller") is None:
        raise SystemExit("Install requirements-build.txt before building.")

    # PyInstaller can otherwise silently omit tkinter and produce an unusable EXE.
    import tkinter
    try:
        tcl = tkinter.Tcl()
        print(f"Tcl runtime: {tcl.eval('info library')}", flush=True)
    except tkinter.TclError as exc:
        raise SystemExit(f"Tcl/Tk initialization failed; use a Windows terminal with working Tk.\n{exc}")

    root = Path(__file__).resolve().parent.parent
    env = os.environ.copy()
    env["PYINSTALLER_CONFIG_DIR"] = str(root / "build" / "pyinstaller-cache")
    subprocess.run(
        [
            sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
            "--distpath", str(root / "dist"),
            "--workpath", str(root / "build" / "pyinstaller"),
            str(root / "wechat-to-feishu.spec"),
        ],
        cwd=root,
        env=env,
        check=True,
    )

    for name in ("README-EXE.md", "LICENSE", "NOTICE", "THIRD_PARTY_NOTICES.md"):
        shutil.copy2(root / name, root / "dist" / name)

    executable = root / "dist" / "WeChat-To-Feishu.exe"
    print(f"\nEXE: {executable}", flush=True)
    print(f"Size: {executable.stat().st_size / 1024 / 1024:.1f} MiB", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
