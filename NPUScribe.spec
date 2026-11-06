# -*- mode: python ; coding: utf-8 -*-
"""Build PyInstaller de NPUScribe (dossier autonome, sans console)."""
import os

from PyInstaller.utils.hooks import collect_all

ROOT = os.path.abspath(os.path.dirname(SPEC))

datas = [(os.path.join(ROOT, "assets", "app.ico"), "assets")]
binaries = []
hiddenimports = ["openvino", "openvino_genai", "openvino_tokenizers",
                 "sounddevice"]

for pkg in ("openvino", "openvino_genai", "openvino_tokenizers",
            "sounddevice", "huggingface_hub", "tqdm"):
    try:
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception as exc:  # noqa: BLE001
        print("collect_all a echoue pour", pkg, exc)

a = Analysis(
    [os.path.join(ROOT, "run.pyw")],
    pathex=[ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["torch", "tensorflow", "matplotlib", "scipy", "pandas",
              "PyQt5", "PySide6", "IPython", "notebook", "pytest"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="NPUScribe",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,                 # UPX casse les DLL OpenVINO
    console=False,
    disable_windowed_traceback=False,
    icon=os.path.join(ROOT, "assets", "app.ico"),
    version=os.path.join(ROOT, "packaging", "version_info.txt"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="NPUScribe",
)
