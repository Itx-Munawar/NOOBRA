# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for NOOBRA. Build with:  pyinstaller noobra.spec"""

block_cipher = None

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=[
        ("core", "core"),
        ("ai", "ai"),
        ("tools", "tools"),
        ("voice", "voice"),
        ("memory", "memory"),
        ("security", "security"),
        ("ui", "ui"),
        ("assets", "assets"),
        (".env.example", "."),
    ],
    hiddenimports=[
        "PySide6", "PySide6.QtCore", "PySide6.QtGui", "PySide6.QtWidgets",
        "dotenv", "requests", "playwright", "pyautogui", "send2trash",
        "faster_whisper", "edge_tts", "sounddevice",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="NOOBRA",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="NOOBRA",
)
