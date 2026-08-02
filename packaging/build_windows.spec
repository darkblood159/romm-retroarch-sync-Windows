# -*- mode: python ; coding: utf-8 -*-
r"""
PyInstaller spec for RomM-RetroArch Sync on Windows.

Prerequisites (full walkthrough in WINDOWS_PORT_NOTES.md):
  1. A gvsbuild GTK4 + libadwaita runtime, e.g. built to C:\gtk (gvsbuild's
     own default) or C:\gtk-build\gtk\x64\release depending on your gvsbuild
     version/config.
  2. A venv with PyGObject installed from gvsbuild's generated wheel (NOT
     bundled inside the runtime tree -- see WINDOWS_PORT_NOTES.md), plus
     `pip install -r requirements-windows.txt` from the project root.
  3. Run this from the project root (the folder containing src/, engine/,
     assets/, requirements-windows.txt):

       set GTK_RUNTIME_DIR=C:\gtk
       pyinstaller packaging\build_windows.spec --distpath dist --workpath build

Output: dist/RomM-RetroArch-Sync/RomM-RetroArch-Sync.exe

This is a onedir build, not onefile. GTK's runtime pulls in a few hundred
small data files (icon theme, typelibs, pixbuf loaders) that onefile mode
would have to re-extract to a temp dir on every single launch — slower to
start, and much harder to debug when one file is missing. onedir just means
"a folder", which is what the Inno Setup installer script expects too.
"""

import os
from pathlib import Path

block_cipher = None

# ---------------------------------------------------------------------
# Locate the GTK runtime
# ---------------------------------------------------------------------
GTK_RUNTIME_DIR = os.environ.get('GTK_RUNTIME_DIR', r'C:\gtk')
gtk_root = Path(GTK_RUNTIME_DIR)
if not gtk_root.exists():
    raise SystemExit(
        f"GTK runtime not found at {GTK_RUNTIME_DIR}.\n"
        f"Set GTK_RUNTIME_DIR to your gvsbuild output directory first, e.g.:\n"
        f"  set GTK_RUNTIME_DIR=C:\\gtk-build\\gtk\\x64\\release\n"
        f"See WINDOWS_PORT_NOTES.md for how to obtain/build it."
    )

gtk_bin = gtk_root / 'bin'
gtk_lib = gtk_root / 'lib'
gtk_share = gtk_root / 'share'

try:
    PROJECT_ROOT = Path(__file__).resolve().parent.parent
except NameError:
    # PyInstaller runs spec files via exec(), and depending on the
    # PyInstaller/Python version combo, __file__ isn't always injected into
    # that exec() namespace (observed with PyInstaller 6.21 + Python 3.14).
    # Falling back to CWD is safe here specifically because
    # build_windows.ps1 always invokes PyInstaller from the project root.
    PROJECT_ROOT = Path.cwd()

# Whichever path was used above, confirm it's actually right rather than
# letting a wrong guess surface as a confusing "file not found" deep inside
# Analysis() instead.
if not (PROJECT_ROOT / 'src' / 'romm_sync_app.py').exists():
    raise SystemExit(
        f"Can't find src\\romm_sync_app.py under {PROJECT_ROOT}.\n"
        f"Run PyInstaller from the project root (the folder containing "
        f"src\\, engine\\, requirements-windows.txt), e.g.:\n"
        f"  cd <project root>\n"
        f"  pyinstaller packaging\\build_windows.spec"
    )


def collect_dir(src: Path, dest_prefix: str):
    """(SRC_FILE, DEST_DIR) pairs for every file under src -- PyInstaller's
    `datas` list wants a destination *directory* per file, not per-tree."""
    pairs = []
    if not src.exists():
        print(f"[build_windows.spec] WARNING: {src} not found, skipping")
        return pairs
    for f in src.rglob('*'):
        if f.is_file():
            rel = f.relative_to(src)
            pairs.append((str(f), str(Path(dest_prefix) / rel.parent)))
    return pairs


datas = []
binaries = []

# All GTK/GLib/Adwaita/HarfBuzz/Pango/etc DLLs, bundled wholesale. Hand-
# picking "the DLLs this app actually needs" out of a gvsbuild tree is
# fragile across gvsbuild versions -- this errs toward a larger dist folder
# instead of a build that mysteriously breaks after the next `gvsbuild update`.
for dll in gtk_bin.glob('*.dll'):
    binaries.append((str(dll), '.'))

# Typelibs: gi.repository.Gtk / .Adw / .Gio / .GLib etc all resolve through
# these at runtime -- without them `gi.require_version(...)` fails outright.
datas += collect_dir(gtk_lib / 'girepository-1.0', 'lib/girepository-1.0')

# Compiled GSettings schemas
datas += collect_dir(gtk_share / 'glib-2.0' / 'schemas', 'share/glib-2.0/schemas')

# Icon themes -- without these, every symbolic/themed icon in the UI (the
# sidebar icons, header bar buttons, etc.) renders as a blank box.
datas += collect_dir(gtk_share / 'icons' / 'Adwaita', 'share/icons/Adwaita')
datas += collect_dir(gtk_share / 'icons' / 'hicolor', 'share/icons/hicolor')

# GDK-Pixbuf loaders -- needed to decode PNG/JPEG cover art and screenshots
datas += collect_dir(gtk_lib / 'gdk-pixbuf-2.0', 'lib/gdk-pixbuf-2.0')

# ---------------------------------------------------------------------
# App data files
# ---------------------------------------------------------------------
datas += [
    (str(PROJECT_ROOT / 'assets'), 'assets'),
    (str(PROJECT_ROOT / 'romm_platform_slugs.json'), '.'),
]

a = Analysis(
    [str(PROJECT_ROOT / 'src' / 'romm_sync_app.py')],
    pathex=[str(PROJECT_ROOT / 'engine'), str(PROJECT_ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=[
        'gi',
        'gi._gi_cairo',  # PyGObject loads this dynamically (not a normal
                         # import), so PyInstaller's static analysis misses
                         # it; without it, any cairo.Context use anywhere in
                         # GTK's own drawing internals fails at runtime with
                         # "Couldn't find foreign struct converter for
                         # 'cairo.Context'" -- this is the documented fix
                         # (see pyinstaller/pyinstaller discussion #7138).
        'cairo',
        'romm_sync_engine',
        'romm_sync_engine.sync_core',
        'romm_sync_engine.bios_manager',
        'romm_sync_engine.paths',
        'romm_sync_engine.activity_log',
        'romm_sync_engine.windows_paths',
        'pystray._win32',
        'winotify',
        'PIL._tkinter_finder',
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

# Set BUILD_DEBUG_CONSOLE=1 before running PyInstaller to get a build with a
# visible console window and verbose bootloader logging -- the normal
# windowed build (console=False) has no console and no window yet if
# something fails during startup, so a crash there is completely silent by
# design. This is the standard way to un-silence that.
DEBUG_BUILD = os.environ.get('BUILD_DEBUG_CONSOLE', '0') == '1'

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='RomM-RetroArch-Sync',
    debug=DEBUG_BUILD,          # verbose bootloader-level loading diagnostics
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,   # UPX-compressing GTK's DLLs is a classic source of a build
                 # that works on the machine that built it and nowhere else.
    console=DEBUG_BUILD,        # gives tracebacks/prints somewhere to go
    icon=str(PROJECT_ROOT / 'assets' / 'icons' / 'romm_icon.ico'),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='RomM-RetroArch-Sync',
)
