# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec file for Fidra.

This spec file configures PyInstaller to build Fidra for both
macOS (.app bundle) and Windows (.exe).

Usage:
    macOS:   pyinstaller fidra.spec
    Windows: pyinstaller fidra.spec

The build will automatically detect the platform and create the
appropriate output format.
"""

import sys
from pathlib import Path

# Detect platform
is_macos = sys.platform == 'darwin'
is_windows = sys.platform == 'win32'

# Get the project root directory
project_root = Path(SPECPATH)

# Define paths
main_script = project_root / 'main.py'
icon_dir = project_root / 'fidra' / 'resources' / 'icons'
resources_dir = project_root / 'fidra' / 'resources'
theme_icons_dir = project_root / 'fidra' / 'ui' / 'theme' / 'icons'

# Icon files (created by scripts/generate_icons.py)
macos_icon = icon_dir / 'fidra.icns'
windows_icon = icon_dir / 'fidra.ico'

# Select icon based on platform
if is_macos:
    icon_file = str(macos_icon) if macos_icon.exists() else None
elif is_windows:
    icon_file = str(windows_icon) if windows_icon.exists() else None
else:
    icon_file = None

# Theme directory (for QSS files)
theme_dir = project_root / 'fidra' / 'ui' / 'theme'

# Collect all data files
datas = [
    # Include resources
    (str(resources_dir), 'fidra/resources'),
    # Include entire theme directory (QSS files + icons)
    (str(theme_dir), 'fidra/ui/theme'),
]

# Hidden imports that PyInstaller might miss
hiddenimports = [
    'PySide6.QtSvg',
    'PySide6.QtSvgWidgets',
    'qasync',
    'aiosqlite',
    'pydantic',
    'openpyxl',
    'pyqtgraph',
    'dateutil',
    'reportlab',
    'reportlab.graphics',
    'svglib',
    'svglib.svglib',
    'markdown',
    'watchdog',
    'watchdog.observers',
    'watchdog.events',
]

# Analysis
a = Analysis(
    [str(main_script)],
    pathex=[str(project_root)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'matplotlib',
        'scipy',
        'pandas',
    ],
    noarchive=False,
    optimize=0,
)

# Remove unnecessary files to reduce bundle size
a.binaries = [x for x in a.binaries if not x[0].startswith('libQt6Designer')]
a.binaries = [x for x in a.binaries if not x[0].startswith('libQt6Quick')]

pyz = PYZ(a.pure)

if is_macos:
    # macOS: Create .app bundle
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name='Fidra',
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        console=False,
        disable_windowed_traceback=False,
        argv_emulation=True,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
        icon=icon_file,
    )

    coll = COLLECT(
        exe,
        a.binaries,
        a.datas,
        strip=False,
        upx=False,
        upx_exclude=[],
        name='Fidra',
    )

    app = BUNDLE(
        coll,
        name='Fidra.app',
        icon=icon_file,
        bundle_identifier='com.fidra.app',
        info_plist={
            'CFBundleName': 'Fidra',
            'CFBundleDisplayName': 'Fidra',
            'CFBundleVersion': '2.0.0',
            'CFBundleShortVersionString': '2.0.0',
            'NSHighResolutionCapable': True,
            'LSMinimumSystemVersion': '10.15',
            'NSRequiresAquaSystemAppearance': False,
            'CFBundleDocumentTypes': [
                {
                    'CFBundleTypeName': 'Fidra Database',
                    'CFBundleTypeExtensions': ['db'],
                    'CFBundleTypeRole': 'Editor',
                }
            ],
        },
    )

else:
    # Windows: Create single executable
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.datas,
        [],
        name='Fidra',
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=True,
        upx_exclude=[],
        runtime_tmpdir=None,
        console=False,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
        icon=icon_file,
    )
