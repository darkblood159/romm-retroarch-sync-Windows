"""Per-application filesystem locations.

The engine is shared by more than one frontend, and each one owns its own
state directory: the GTK app keeps ``~/.config/romm-retroarch-sync`` (Linux)
or ``%APPDATA%\\romm-retroarch-sync`` (Windows) while Ludo uses the
``ludo``-named equivalent. Nothing is shared between them.

Frontends call :func:`set_app_id` once, before touching anything else in the
engine. The default keeps the GTK app working without any changes on its side.
"""

import platform
from pathlib import Path

DEFAULT_APP_ID = "romm-retroarch-sync"
DEFAULT_CLIENT_NAME = "RomM-RetroArch-Sync"

_app_id = DEFAULT_APP_ID
_client_name = DEFAULT_CLIENT_NAME
_locked = False

IS_WINDOWS = platform.system() == "Windows"


def set_app_id(app_id: str) -> None:
    """Point the engine at its per-OS state directory for ``<app_id>``.

    Must be called before the first :func:`config_dir` call. Calling it after
    the fact means some state has already been read from or written to the
    wrong directory, so that raises rather than silently splitting an app's
    files across two locations.
    """
    global _app_id
    if not app_id or "/" in app_id or "\\" in app_id:
        raise ValueError(f"invalid app id: {app_id!r}")
    if _locked and app_id != _app_id:
        raise RuntimeError(
            f"set_app_id({app_id!r}) called after paths were already resolved "
            f"as {_app_id!r}; move the call earlier in startup"
        )
    _app_id = app_id


def app_id() -> str:
    return _app_id


def set_client_name(name: str) -> None:
    """Set how this app identifies itself to the RomM server.

    Sent as the ``client`` field when registering a device and as the
    User-Agent, so RomM shows each frontend as a distinct client.
    """
    global _client_name
    _client_name = name


def client_name() -> str:
    return _client_name


def config_dir() -> Path:
    """The app's state directory. Created on first use.

    Linux/macOS: ``~/.config/<app_id>`` (unchanged).
    Windows: ``%APPDATA%\\<app_id>`` — the standard per-user roaming location,
    instead of a literal ``.config`` folder under the home directory. Falls
    back to ``~/.config/<app_id>`` if ``APPDATA`` isn't set for some reason,
    so this never raises on a misconfigured environment.
    """
    global _locked
    _locked = True
    if IS_WINDOWS:
        import os
        appdata = os.environ.get("APPDATA")
        base = Path(appdata) if appdata else (Path.home() / ".config")
        d = base / _app_id
    else:
        d = Path.home() / ".config" / _app_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def cache_dir() -> Path:
    return config_dir() / "cache"
