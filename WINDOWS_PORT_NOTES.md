# Windows Port Notes

This is a 1:1 port of `romm-retroarch-sync` (the GTK4/libadwaita desktop app)
to Windows — same GUI, same widgets, same features, running against the same
`romm_sync_engine` the Linux build uses. Nothing was rewritten; existing
Linux code paths are untouched, and Windows support was added alongside them
behind `platform.system()` checks. This document is a map of every change,
why it was needed, and what still needs verification on a real Windows
machine, since this was built and tested on Linux (see "How this was
tested" below).

## Source

- GUI: `Covin90/romm-retroarch-sync`, commit `249ef1e` (the `main` branch zip
  you uploaded).
- Engine: `Covin90/ludo`, commit as of 2026-07-27 (`engine/romm_sync_engine`),
  found to be publicly cloneable despite `requirements.txt` calling it
  private — flagged to you and confirmed before use.

## Layout

```
windows_port/
├── engine/romm_sync_engine/   # the engine, patched for Windows
│   ├── sync_core.py            # RomMClient, RetroArchInterface, AutoSyncManager, etc.
│   ├── bios_manager.py
│   ├── paths.py
│   ├── activity_log.py
│   └── windows_paths.py        # NEW — Windows-only discovery helpers
├── src/romm_sync_app.py       # the GTK4/libadwaita GUI, patched for Windows
├── romm_platform_slugs.py/.json
├── assets/icons/               # + romm_icon.ico, generated for the Windows build
└── packaging/
    ├── build_windows.spec      # PyInstaller spec
    ├── build_windows.ps1       # build automation
    └── installer.iss           # Inno Setup installer script
```

## Engine changes (`engine/romm_sync_engine/`)

**`windows_paths.py` (new).** Centralizes every bit of Windows-only
filesystem discovery so it isn't duplicated across six call sites:
Steam's install location + every Steam library (registry + parsing
`libraryfolders.vdf`), a search of the Windows uninstall registry for an
installer-based RetroArch install, and the common manual-extract locations
(`C:\RetroArch-Win64`, `%LOCALAPPDATA%\RetroArch`, etc.). Every `winreg`
import is deferred inside a function rather than done at module scope, so
this file is harmless to import on Linux/macOS too.

**`paths.py`.** `config_dir()` now resolves to `%APPDATA%\<app_id>` on
Windows (falling back to `~/.config/<app_id>` if `APPDATA` is somehow unset)
instead of literally creating a `.config` folder under the home directory.
Linux/macOS behavior is unchanged.

**`sync_core.py`** — the big one:

- **SSL certificates (bug fix).** Unconditionally set
  `REQUESTS_CA_BUNDLE`/`SSL_CERT_FILE` to `/etc/ssl/certs/ca-certificates.crt`
  (an AppImage workaround). That path doesn't exist on Windows; left as-is,
  every HTTPS call this app makes — including talking to your RomM server —
  would have failed with no CA bundle found. Now gated to
  `platform.system() == 'Linux'` and only if that path actually exists.
- **Core discovery (bug fix).** `get_available_cores()` and
  `find_cores_directory()` only ever globbed for `*.so` files. RetroArch
  cores on Windows are `.dll`. Unfixed, core discovery would silently return
  zero cores on Windows and every game would report "no core available."
  Now picks the extension based on `platform.system()`.
- **`find_retroarch_executable`, `find_retroarch_config_dir`,
  `find_retroarch_dirs`, `find_cores_directory`, `find_thumbnails_directory`**
  — each of these was a hand-written list of Linux paths (Flatpak, Snap,
  RetroDECK, native `~/.config`) with no Windows branch at all. Each now
  checks `windows_paths.retroarch_root_candidates()` (plus,
  where relevant, `%APPDATA%\RetroArch`) first on Windows, using the same
  "does this actually exist" verification the Linux paths use — no new
  trust placed in guessed paths.
- **`find_steam_userdata_path`** (in `SteamShortcutManager`, used by the
  Steam shortcuts/grid-art feature) — same treatment, via
  `windows_paths.steam_userdata_dirs()`.
- **Everything else** — `RomMClient` (the RomM API client), `AutoSyncManager`,
  `SaveFileHandler` (watchdog-based file watching), `CollectionSyncManager`,
  `BiosTrackingManager`, `SteamVDFHandler`, the actual `launch_game`/
  `build_launch_command` game-launch path — needed **no changes**. They're
  either pure HTTP/JSON/threading code with no OS assumptions, or already
  defensively wrapped (e.g. every `os.getuid()` call — meaningless on
  Windows — is already inside a `try/except`, so it degrades to `None`
  instead of crashing). `watchdog` itself already has a native Windows
  backend (`ReadDirectoryChangesW`), so save-file watching needed nothing
  extra either.

**`bios_manager.py`.** `find_system_directory()` got the same Windows
candidate-list treatment as the RetroArch directory finders above.

## GUI changes (`src/romm_sync_app.py`)

- **SSL certificates** — same bug, same fix, independently duplicated at the
  top of this file too.
- **`TrayIcon`.** Linux keeps its exact existing implementation (a
  subprocess running GTK3 + AppIndicator3, signaled via `SIGUSR1`/`SIGTERM`)
  untouched. AppIndicator3 doesn't exist on Windows, and Windows has no
  `SIGUSR1`, so a new `setup_tray_windows()` uses
  [`pystray`](https://github.com/moses-palmer/pystray) instead — it talks to
  the native Win32 tray (`Shell_NotifyIcon`) from a background thread in the
  *same* process (no subprocess needed on Windows), and its menu callbacks
  hand off to the GTK main loop via `GLib.idle_add` instead of OS signals.
  Same public interface (`TrayIcon(app, window)`, `.cleanup()`), so every
  other call site in the file is unchanged.
- **Autostart.** The four systemd-based methods
  (`create_systemd_service`/`remove_systemd_service`/
  `update_systemd_service_if_needed`/`check_autostart_status` — names kept
  as-is so no other call site needed touching) now dispatch on
  `platform.system()`. Windows creates a **Task Scheduler** task (via
  `schtasks`, using the XML task format since that's the only way to express
  a start delay + restart-on-failure) that mirrors the systemd unit as
  closely as Task Scheduler allows: trigger at logon, ~15s start delay,
  restart on failure. One real difference: Task Scheduler's minimum restart
  interval is 1 minute, vs. the systemd unit's 10 seconds — a Task Scheduler
  limitation, not a choice made here.
- **Notifications.** `send_desktop_notification` tries
  [`winotify`](https://github.com/versa-syahptr/winotify) (native Windows
  10/11 toast) first on Windows, falling back to `Gio.Notification` if
  `winotify` isn't installed — GLib does have its own win32 notification
  backend, kept as a safety net rather than the primary path since it's
  less proven than the Linux gdbus/notify-send combo this app normally
  relies on. Linux behavior unchanged.
- **Single instance.** Added `_windows_single_instance_guard()` — a named
  kernel mutex checked before the app starts. `Adw.Application`'s own
  `application_id` already gives GLib-level single-instance activation on
  Windows too (GIO has a win32 IPC backend, not just D-Bus), but that's hard
  to verify without a real Windows machine, and two instances of a tool that
  moves save files and ROM libraries around is worth a second, independent
  guard against. Linux continues to rely on GApplication/D-Bus alone, as
  before.
- **Folder-opening.** The `xdg-open` fallback (used only if `Gtk.FileLauncher`
  itself fails) is now `os.startfile()` on Windows.
- **Cosmetic:** the RetroArch "install type" label now says "Portable"
  instead of falling through to "Native" when none of the
  Flatpak/Snap/RetroDECK/Steam/AppImage markers match and the OS is Windows.

## Packaging

RetroArch itself isn't bundled — same as the Linux build, the app expects
RetroArch to already be installed and finds it (or you point it at a custom
path in Settings, which always works regardless of auto-detection).

**What GTK4/libadwaita needs on Windows.** Unlike Linux, there's no system
package manager to `apt install` these from. The standard way to get a real
GTK4 + PyGObject + libadwaita stack on Windows is
[**gvsbuild**](https://github.com/wingtk/gvsbuild) — it builds (or, via its
CI artifacts, provides pre-built) the actual upstream libraries, not a
reimplementation, so this stays a genuine 1:1 GUI rather than a recreation
in a different toolkit. This is a real build dependency, not a pip package —
budget time for it the first time; it's a one-off per machine, not a
per-build step.

1. Install [gvsbuild](https://github.com/wingtk/gvsbuild) itself (`pipx
   install gvsbuild` is the tool's own recommended method) and build with the
   `--enable-gi --py-wheel` flags, which matter — without them, gvsbuild
   builds the C libraries only and never produces the Python bindings:
   ```
   gvsbuild build --enable-gi --py-wheel gtk4 libadwaita pygobject
   ```
   This lands the runtime at `C:\gtk` by default (`bin\`, `lib\`, `share\`),
   and — importantly, and *not* inside that runtime tree — generates real
   `.whl` files (`PyGObject*.whl`, `pycairo*.whl`) under `C:\gtk\wheels\` on
   current gvsbuild, or `C:\gtk-build\build\x64\release\pygobject\dist\` on
   older versions. (Earlier revisions of this doc assumed gvsbuild bundles
   its own Python install and PyGObject lives in a `Python3XX\site-packages`
   folder inside the runtime — that's wrong, corrected here.)
2. Set `GTK_RUNTIME_DIR` to the runtime root (`C:\gtk` above).
3. Run `packaging\build_windows.ps1` — it creates a venv, searches both of
   the wheel locations above and `pip install`s whatever it finds there,
   installs `requirements-windows.txt`, verifies `import gi; Gtk; Adw`
   actually works *before* attempting a full PyInstaller build, then runs
   PyInstaller. If it can't find any wheels, it prints the exact `gvsbuild`
   command from step 1 rather than failing silently later.
4. Optionally, `iscc packaging\installer.iss` (needs
   [Inno Setup](https://jrsoftware.org/isinfo.php)) to produce a real
   installer — Start Menu entry, optional desktop icon, optional autostart
   registry entry, uninstaller registered in Add/Remove Programs.

`packaging/build_windows.spec` bundles the *entire* gvsbuild `bin\` (all
DLLs), the GObject-Introspection typelibs, the Adwaita/hicolor icon themes,
and the GDK-Pixbuf loaders, rather than hand-picking a subset — trying to
enumerate "exactly which DLLs this app needs" out of a gvsbuild tree is
exactly the kind of thing that works on the machine that built it and
breaks on the next `gvsbuild` version bump.

`assets/icons/romm_icon.ico` was generated from the existing
`romm_icon.png` (multi-resolution: 16/24/32/48/64/128/256px) since Windows
needs a real `.ico` for the exe/taskbar icon and only a PNG existed before.

## How this was tested

This was built in a Linux sandbox with no Windows machine available, so
testing tops out at:

- Real GTK4 4.14.5 + libadwaita 1.5 installed (not just the Python
  bindings) — every file compiles, imports cleanly, and `SyncApp`
  instantiates and registers correctly against the real GLib/GTK4 stack.
- The engine (`RetroArchInterface`, `BiosManager`, `SteamShortcutManager`)
  instantiated with `platform.system` monkeypatched to `'Windows'` and
  fake `APPDATA`/`ProgramFiles`/etc. env vars — confirms every new code
  path runs without crashing and degrades gracefully (returns `None`/empty
  rather than raising) when a candidate path predictably doesn't exist on
  a Linux test machine.
- `windows_paths.py`'s registry-dependent functions (`steam_install_dirs`,
  `registry_install_location`) can't be exercised at all without Windows —
  `winreg` doesn't exist here — so they're verified by code review only.

**What genuinely needs a real Windows machine to confirm:**

1. The gvsbuild runtime bundling in `build_windows.spec` — first build will
   likely need one or two rounds of "run the exe, see which DLL/typelib is
   missing, check it got collected" iteration. This is normal for a first
   GTK-on-Windows packaging pass.
2. Task Scheduler autostart actually restarts the app on crash / starts it
   at logon as configured.
3. `pystray`'s Win32 backend — menu positioning, icon rendering, click
   behavior.
4. `winotify` toast delivery, and whether the `Gio.Notification` fallback
   also happens to work via GLib's win32 backend.
5. The Steam-library and uninstall-registry parsing in `windows_paths.py`
   against a real Steam install / real RetroArch install.
6. `Adw.Application`'s single-instance activation on Windows (the named
   mutex guard means a second launch is *prevented*, but "prevented" is a
   different question from "cleanly focuses the existing window instead" —
   worth a look once testable).

None of these are "might not work" architecturally — they're all standard,
well-trodden libraries/mechanisms for exactly this purpose — but I can't
personally exercise a Win32 tray icon or Task Scheduler from this sandbox,
so treat item 1-6 as the actual first-Windows-run checklist rather than
assuming zero surprises.
