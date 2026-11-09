# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, copy_metadata

project_root = Path(SPECPATH)

# Explicitly include only application resources; never bundle local user data.
datas = [
    (str(project_root / "LICENSE"), "."),
    (str(project_root / "NOTICE"), "."),
    (str(project_root / "THIRD_PARTY_NOTICES.md"), "."),
    (str(project_root / "assets" / "app.ico"), "assets"),
    (str(project_root / "assets" / "bitable-template.json"), "assets"),
]
datas += collect_data_files("wechatauto", includes=["assets/**"])
datas += copy_metadata("wechatauto-replica")
binaries = [
    item for item in collect_dynamic_libs("uiautomation")
    if "X86" not in Path(item[0]).name
]

a = Analysis(
    [str(project_root / "app_feishu.py")],
    pathex=[str(project_root), str(project_root / "scripts")],
    binaries=binaries,
    datas=datas,
    hiddenimports=["feishu_config_gui"],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="WeChat-To-Feishu",
    debug=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    icon=str(project_root / "assets" / "app.ico"),
)
