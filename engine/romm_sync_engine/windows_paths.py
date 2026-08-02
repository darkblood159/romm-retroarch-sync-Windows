"""Windows-only filesystem discovery helpers for RetroArch and Steam.

sync_core.py and bios_manager.py each have several "search a list of likely
directories" methods that were written for Linux (Flatpak, Snap, RetroDECK,
native paths under ``~/.config``). Rather than hand-writing a Windows
candidate list at every one of those call sites, this module centralizes the
Windows-specific discovery logic — Steam library parsing, registry lookups —
and each call site just extends its existing ``possible_dirs`` list with
whatever this module finds.

Every function here is safe to import and call on any OS: the ``winreg``
import (Windows-only in the standard library) is deferred inside each
function rather than done at module scope, so nothing breaks on Linux/macOS
if this module ever gets imported there. In practice callers only invoke it
behind a ``platform.system() == 'Windows'`` check, but the defensive import
keeps that a convention rather than a hard requirement.
"""

from pathlib import Path


def _winreg():
    try:
        import winreg
        return winreg
    except ImportError:
        return None


def steam_install_dirs():
    """Every Steam install directory findable via the registry.

    Usually just one, but checks both the per-user and machine-wide keys
    since Steam itself only reliably keeps the per-user one current.
    """
    winreg = _winreg()
    if not winreg:
        return []
    found = []
    lookups = (
        (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam", "SteamPath"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam", "InstallPath"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam", "InstallPath"),
    )
    for hive, key, value_name in lookups:
        try:
            with winreg.OpenKey(hive, key) as k:
                value, _ = winreg.QueryValueEx(k, value_name)
                p = Path(value)
                if p.exists() and p not in found:
                    found.append(p)
        except OSError:
            continue
    return found


def _parse_library_folders_vdf(vdf_path):
    """Pull every ``"path"  "..."`` entry out of libraryfolders.vdf.

    This is Valve's own tiny key/value text format, not real VDF/KV1 (which
    would need a real parser for nested blocks) — a regex is enough since
    all we need is the flat top-level "path" entries.
    """
    import re
    try:
        text = Path(vdf_path).read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []
    return [Path(m.group(1).replace("\\\\", "\\")) for m in re.finditer(r'"path"\s*"([^"]+)"', text)]


def steam_library_dirs():
    """Every Steam library root (main install + any additional drives)."""
    libraries = []
    for steam_dir in steam_install_dirs():
        if steam_dir not in libraries:
            libraries.append(steam_dir)
        vdf = steam_dir / "steamapps" / "libraryfolders.vdf"
        for lib in _parse_library_folders_vdf(vdf):
            if lib.exists() and lib not in libraries:
                libraries.append(lib)
    return libraries


def steam_common_dirs(subpath="RetroArch"):
    """``steamapps/common/<subpath>`` under every known Steam library."""
    return [lib / "steamapps" / "common" / subpath for lib in steam_library_dirs()]


def steam_userdata_dirs():
    """Candidate ``userdata`` directories (holds each account's shortcuts.vdf)."""
    return [lib / "userdata" for lib in steam_library_dirs()]


def registry_install_location(display_name_substrings):
    """Search both Uninstall registry trees for an app whose DisplayName
    contains any of the given substrings (case-insensitive), returning its
    InstallLocation. Covers RetroArch installs done via an installer/winget
    rather than a manual portable extract.
    """
    winreg = _winreg()
    if not winreg:
        return None
    needles = [s.lower() for s in display_name_substrings]
    roots = (
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
    )
    for hive, root in roots:
        try:
            with winreg.OpenKey(hive, root) as parent:
                for i in range(winreg.QueryInfoKey(parent)[0]):
                    try:
                        subkey_name = winreg.EnumKey(parent, i)
                        with winreg.OpenKey(parent, subkey_name) as sub:
                            name, _ = winreg.QueryValueEx(sub, "DisplayName")
                            if any(n in name.lower() for n in needles):
                                loc, _ = winreg.QueryValueEx(sub, "InstallLocation")
                                if loc and Path(loc).exists():
                                    return Path(loc)
                    except OSError:
                        continue
        except OSError:
            continue
    return None


def common_install_roots():
    """Plain Program-Files-style locations people extract/install RetroArch to,
    independent of Steam or the registry."""
    import os
    roots = []
    for env_var, sub in (
        ("ProgramFiles", "RetroArch-Win64"),
        ("ProgramFiles", "RetroArch"),
        ("ProgramFiles(x86)", "RetroArch-Win32"),
        ("ProgramFiles(x86)", "RetroArch"),
        ("LOCALAPPDATA", "RetroArch-Win64"),
        ("LOCALAPPDATA", "RetroArch"),
        ("LOCALAPPDATA", "Programs\\RetroArch"),
    ):
        base = os.environ.get(env_var)
        if base:
            roots.append(Path(base) / sub)
    # The classic "just extracted the zip to C:\" habit.
    for drive_root in (r"C:\RetroArch-Win64", r"C:\RetroArch", r"C:\Emulation\RetroArch",
                       r"C:\Emulation\RetroArch-Win64"):
        roots.append(Path(drive_root))
    return roots


def retroarch_root_candidates():
    """Ordered, de-duplicated list of directories that might directly contain
    retroarch.exe / retroarch.cfg (Windows RetroArch is portable by default,
    so the exe and its config normally live in the same folder)."""
    candidates = []
    reg_loc = registry_install_location(("retroarch",))
    if reg_loc:
        candidates.append(reg_loc)
    candidates.extend(steam_common_dirs("RetroArch"))
    candidates.extend(common_install_roots())
    seen, ordered = set(), []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            ordered.append(c)
    return ordered
