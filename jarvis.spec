# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller build spec for JARVIS.

Build a standalone Windows application:

    pyinstaller --noconfirm jarvis.spec

The result is a one-folder build in ``dist\\JARVIS\\`` containing
``JARVIS.exe``. The Vosk speech model is intentionally **not** bundled: place it
under ``models\\vosk-model-small-en-us-0.15`` next to the executable (see the
README). ``.env``, ``logs\\``, ``data\\``, and ``workspace\\`` are likewise
created beside the executable at runtime.

If the optional voice extras are installed in the build environment, their data
and native libraries (Vosk, PortAudio via sounddevice, the SAPI5 TTS driver) are
collected automatically. Building without them still produces a working app
(the microphone and speech output report a clear message instead).
"""

import importlib.util

from PyInstaller.utils.hooks import collect_all

datas = []
binaries = []
hiddenimports = []

# Collect native libraries and data files for the optional voice packages when
# they are present in the build environment.
for package in ("vosk", "sounddevice"):
    if importlib.util.find_spec(package) is not None:
        pkg_datas, pkg_binaries, pkg_hiddenimports = collect_all(package)
        datas += pkg_datas
        binaries += pkg_binaries
        hiddenimports += pkg_hiddenimports

# Windows SAPI5 text-to-speech driver and its COM dependency are imported
# dynamically by pyttsx3, so PyInstaller cannot see them on its own.
hiddenimports += ["pyttsx3.drivers", "pyttsx3.drivers.sapi5"]

a = Analysis(
    ["app/main.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "numpy", "pytest"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="JARVIS",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="JARVIS",
)
