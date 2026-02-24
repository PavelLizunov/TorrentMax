# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for TorrentMax standalone build."""

import os
import sys
import sysconfig

site_packages = sysconfig.get_path('purelib')
lt_dir = os.path.join(site_packages, 'libtorrent')

# libtorrent native DLLs that must be bundled
lt_binaries = []
for dll in ['__init__.cp310-win_amd64.pyd', 'libcrypto-1_1-x64.dll', 'libssl-1_1-x64.dll']:
    path = os.path.join(lt_dir, dll)
    if os.path.isfile(path):
        lt_binaries.append((path, 'libtorrent'))

a = Analysis(
    ['torrentmax/main.py'],
    pathex=['.'],
    binaries=lt_binaries,
    datas=[],
    hiddenimports=[
        'libtorrent',
        'psutil',
        'pyqtgraph',
        'pyqtgraph.graphicsItems',
        'pyqtgraph.graphicsItems.PlotItem',
        'pyqtgraph.graphicsItems.ViewBox',
        'pyqtgraph.graphicsItems.PlotCurveItem',
        'numpy',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=['pyi_rth_libtorrent.py'],
    excludes=[
        # Trim unnecessary Qt modules to reduce size
        'PyQt6.QtWebEngine',
        'PyQt6.QtWebEngineWidgets',
        'PyQt6.QtWebEngineCore',
        'PyQt6.QtDesigner',
        'PyQt6.QtHelp',
        'PyQt6.QtMultimedia',
        'PyQt6.QtMultimediaWidgets',
        'PyQt6.Qt3DCore',
        'PyQt6.Qt3DExtras',
        'PyQt6.Qt3DRender',
        'PyQt6.QtBluetooth',
        'PyQt6.QtNfc',
        'PyQt6.QtPositioning',
        'PyQt6.QtSensors',
        'PyQt6.QtSerialPort',
        'PyQt6.QtSql',
        'PyQt6.QtTest',
        'PyQt6.QtTextToSpeech',
        'PyQt6.QtQml',
        'PyQt6.QtQuick',
        'PyQt6.QtQuickWidgets',
        'PyQt6.QtRemoteObjects',
        'PyQt6.QtWebSockets',
        'PyQt6.QtXml',
        'PyQt6.QtDBus',
        # Other unused
        'tkinter',
        'unittest',
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='TorrentMax',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,       # No console window (GUI app)
    disable_windowed_traceback=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='TorrentMax',
)
