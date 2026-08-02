#Requires -Version 5.1
<#
.SYNOPSIS
    Builds the Windows distributable for RomM-RetroArch Sync.

.DESCRIPTION
    Wraps the steps in WINDOWS_PORT_NOTES.md: create/reuse a venv, install
    dependencies (including PyGObject from gvsbuild's generated wheels), run
    PyInstaller, and report where the built app landed.

    This does NOT build the GTK runtime itself -- that's a separate,
    one-time step (gvsbuild), because it takes a long time and rarely
    changes. Run this script after that runtime already exists.

.PARAMETER GtkRuntimeDir
    Path to your gvsbuild output root, e.g. C:\gtk or C:\gtk-build\gtk\x64\release.
    Defaults to the GTK_RUNTIME_DIR environment variable if already set.

.EXAMPLE
    .\packaging\build_windows.ps1 -GtkRuntimeDir C:\gtk
#>

param(
    [string]$GtkRuntimeDir = $env:GTK_RUNTIME_DIR
)

$ErrorActionPreference = "Continue"
# Deliberately not "Stop": with Stop, PowerShell treats *any* stderr output
# from a native program (python.exe, pip, pyinstaller) as a fatal error, even
# routine/non-fatal notices with no bearing on whether the command actually
# succeeded. This script checks $LASTEXITCODE explicitly after every native
# command instead, which is the actual reliable signal.
$ProjectRoot = Split-Path -Parent $PSScriptRoot

function Fail($msg) {
    Write-Host "ERROR: $msg" -ForegroundColor Red
    Pop-Location -ErrorAction SilentlyContinue
    exit 1
}

# Everything below assumes CWD == project root (the folder containing
# engine/, src/, requirements-windows.txt). Fixed at the top rather than
# right before the PyInstaller step, because pip also needs it: the
# `-e ./engine` line in requirements-windows.txt is resolved relative to
# pip's *working directory*, not relative to the requirements file itself --
# running this script from inside packaging\ (e.g. via right-click > Run
# with PowerShell) previously made pip look for .\packaging\engine and fail
# with "./engine is not a valid editable requirement".
Push-Location $ProjectRoot

Write-Host "== RomM-RetroArch Sync -- Windows build ==" -ForegroundColor Cyan
Write-Host "Project root: $ProjectRoot"

# ---------------------------------------------------------------------
# 1. Sanity-check the GTK runtime
# ---------------------------------------------------------------------
if (-not $GtkRuntimeDir) {
    Fail "No GTK runtime directory given. Pass -GtkRuntimeDir or set GTK_RUNTIME_DIR.`nSee WINDOWS_PORT_NOTES.md if you haven't built/obtained the gvsbuild runtime yet."
}
if (-not (Test-Path $GtkRuntimeDir)) {
    Fail "GTK runtime directory does not exist: $GtkRuntimeDir"
}
$env:GTK_RUNTIME_DIR = $GtkRuntimeDir
Write-Host "Using GTK runtime: $GtkRuntimeDir"

# ---------------------------------------------------------------------
# 2. Put the GTK bin dir on PATH for this session (DLL resolution --
#    needed both for the import check below and implicitly by anything
#    that shells out to gvsbuild-provided tools).
# ---------------------------------------------------------------------
$env:Path = "$GtkRuntimeDir\bin;$env:Path"

# ---------------------------------------------------------------------
# 3. Create/reuse a venv
# ---------------------------------------------------------------------
$VenvDir = Join-Path $ProjectRoot ".venv-windows"
if (-not (Test-Path $VenvDir)) {
    Write-Host "Creating venv at $VenvDir ..."
    python -m venv $VenvDir
}
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
    Fail "venv creation seems to have failed -- $VenvPython not found."
}

# ---------------------------------------------------------------------
# 4. Find and install the gvsbuild-generated PyGObject/pycairo wheels.
#
#    gvsbuild does NOT install PyGObject into a bundled Python -- when
#    built with `gvsbuild build --enable-gi --py-wheel gtk4 libadwaita
#    pygobject`, it produces real .whl files, in one of a couple of
#    locations depending on gvsbuild version:
#      - C:\gtk\wheels\PyGObject*.whl                          (newer)
#      - C:\gtk-build\build\x64\release\pygobject\dist\*.whl    (older)
#    This searches both the given GTK_RUNTIME_DIR and its likely siblings
#    for any PyGObject*.whl / pycairo*.whl it can find.
# ---------------------------------------------------------------------
Write-Host "Looking for gvsbuild PyGObject/pycairo wheels..."
$wheelSearchRoots = @(
    $GtkRuntimeDir,
    (Join-Path $GtkRuntimeDir "wheels"),
    "C:\gtk\wheels",
    "C:\gtk-build\build\x64\release\pygobject\dist",
    "C:\gtk-build\build\x64\release\pycairo\dist"
) | Select-Object -Unique

$foundWheels = @()
foreach ($root in $wheelSearchRoots) {
    if (Test-Path $root) {
        $foundWheels += Get-ChildItem -Path $root -Recurse -Filter "PyGObject*.whl" -ErrorAction SilentlyContinue
        $foundWheels += Get-ChildItem -Path $root -Recurse -Filter "pycairo*.whl" -ErrorAction SilentlyContinue
    }
}
$foundWheels = $foundWheels | Select-Object -Unique -ExpandProperty FullName

if ($foundWheels.Count -eq 0) {
    Write-Host "No PyGObject/pycairo wheels found under:" -ForegroundColor Yellow
    $wheelSearchRoots | ForEach-Object { Write-Host "  $_" -ForegroundColor Yellow }
    Write-Host ""
    Write-Host "gvsbuild only produces these wheels when built with --enable-gi --py-wheel." -ForegroundColor Yellow
    Write-Host "If you haven't already, (re)run:" -ForegroundColor Yellow
    Write-Host "  gvsbuild build --enable-gi --py-wheel gtk4 libadwaita pygobject" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Continuing anyway in case PyGObject is already installed some other way..." -ForegroundColor Yellow
} else {
    Write-Host "Found:"
    $foundWheels | ForEach-Object { Write-Host "  $_" }
    foreach ($whl in $foundWheels) {
        & $VenvPython -m pip install --force-reinstall $whl
        if ($LASTEXITCODE -ne 0) {
            Fail "pip install failed for $whl (see output above)."
        }
    }
}

# ---------------------------------------------------------------------
# 5. Install the rest of the dependencies + PyInstaller
# ---------------------------------------------------------------------
Write-Host "Installing dependencies..."
& $VenvPython -m pip install --upgrade pip
# Not checking exit code here on purpose -- a pip self-upgrade failure isn't
# worth aborting the whole build over, unlike everything else below.
& $VenvPython -m pip install -r "requirements-windows.txt"
if ($LASTEXITCODE -ne 0) {
    Fail "pip install -r requirements-windows.txt failed (see above)."
}

# ---------------------------------------------------------------------
# 6. Sanity check: can this venv actually import Gtk4 + Adw before we
#    spend time on a PyInstaller build that would just fail the same way?
# ---------------------------------------------------------------------
Write-Host "Verifying GTK4 + libadwaita import..."
$checkScript = @"
import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw
print(f'OK: GTK {Gtk.get_major_version()}.{Gtk.get_minor_version()}, Adw {Adw.MAJOR_VERSION}.{Adw.MINOR_VERSION}')
"@
$checkScript | & $VenvPython -
if ($LASTEXITCODE -ne 0) {
    Fail "GTK4/libadwaita import failed inside the venv.`nIf no wheels were found above, that's almost certainly why -- see the gvsbuild command printed there.`nIf wheels WERE found and installed but this still fails, it's most likely a DLL resolution issue: confirm $GtkRuntimeDir\bin actually contains gtk-4-1.dll / libadwaita-1-0.dll, and that PATH (printed above as 'Using GTK runtime') points at the same GTK build the wheels came from."
}

# ---------------------------------------------------------------------
# 7. Build
#
#    --clean wipes PyInstaller's own build\ cache (Analysis/COLLECT
#    intermediates) before building. Worth forcing unconditionally: a
#    build that failed partway through a spec change can leave stale
#    cache behind that makes the *next* run skip work it should redo.
#    The dist output folder is also removed outright first, in case
#    anything was manually dropped into it while troubleshooting.
# ---------------------------------------------------------------------
$DistAppDir = Join-Path $ProjectRoot "dist\RomM-RetroArch-Sync"
if (Test-Path $DistAppDir) {
    Write-Host "Removing existing $DistAppDir before rebuilding..."
    Remove-Item -Recurse -Force $DistAppDir -ErrorAction SilentlyContinue
    if (Test-Path $DistAppDir) {
        Fail "Couldn't fully remove $DistAppDir (a file in there is probably still open/locked -- close any Explorer windows or running instances of the app in it, or delete it manually, then re-run)."
    }
}

Write-Host "Running PyInstaller (clean build)..." -ForegroundColor Cyan
& $VenvPython -m PyInstaller "packaging\build_windows.spec" `
    --distpath "dist" `
    --workpath "build" `
    --clean `
    --noconfirm
if ($LASTEXITCODE -ne 0) {
    Fail "PyInstaller build failed (see output above)."
}

# ---------------------------------------------------------------------
# 8. Verify what actually landed in dist -- don't just check the exe
#    exists, since a broken/partial COLLECT can still leave an exe
#    behind without its required _internal folder next to it.
# ---------------------------------------------------------------------
$OutputExe = Join-Path $DistAppDir "RomM-RetroArch-Sync.exe"
$InternalDir = Join-Path $DistAppDir "_internal"

Write-Host ""
Write-Host "== Build output check ==" -ForegroundColor Cyan
Write-Host "exe exists:        $(Test-Path $OutputExe)"
Write-Host "_internal exists:  $(Test-Path $InternalDir)"
if (Test-Path $DistAppDir) {
    $fileCount = (Get-ChildItem -Path $DistAppDir -Recurse -File -ErrorAction SilentlyContinue | Measure-Object).Count
    Write-Host "total files under dist\RomM-RetroArch-Sync: $fileCount"
}
if (Test-Path $InternalDir) {
    $pydll = Get-ChildItem -Path $InternalDir -Filter "python3*.dll" -ErrorAction SilentlyContinue
    Write-Host "python3*.dll in _internal: $($pydll.Name -join ', ')"
}

if ((Test-Path $OutputExe) -and (Test-Path $InternalDir)) {
    Write-Host ""
    Write-Host "Build complete: $OutputExe" -ForegroundColor Green
    Write-Host "Run it directly, or build the installer with:" -ForegroundColor Green
    Write-Host "  iscc packaging\installer.iss" -ForegroundColor Green
} else {
    Fail "Build finished but dist\RomM-RetroArch-Sync is incomplete (see the check above). This means PyInstaller's COLLECT step didn't fully write its output -- paste the full build log (not just the tail) so this can be diagnosed properly, along with the 'Build output check' block above."
}

Pop-Location
