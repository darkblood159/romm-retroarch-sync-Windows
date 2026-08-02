# RomM - RetroArch Sync (Windows port)

A Windows port of [Covin90/romm-retroarch-sync](https://github.com/Covin90/romm-retroarch-sync)
— same GTK4/libadwaita GUI, same features, running against the same
`romm_sync_engine` the Linux build uses. Existing Linux behavior is
untouched; Windows support was added alongside it.

**Read [`WINDOWS_PORT_NOTES.md`](WINDOWS_PORT_NOTES.md) first.** It documents
every change made, why, and — importantly — a checklist of the handful of
things (Task Scheduler behavior, tray icon rendering, toast notifications)

## Quick start

1. **Get a GTK4 + libadwaita runtime for Windows** via
   [gvsbuild](https://github.com/wingtk/gvsbuild) — this is the one genuinely
   heavy prerequisite; see `WINDOWS_PORT_NOTES.md` → "Packaging" for the
   exact command (needs the `--enable-gi --py-wheel` flags). One-time setup,
   not a per-build step.
2. From the project root (this folder): `set GTK_RUNTIME_DIR=C:\gtk`
   (or wherever yours landed)
3. `.\packaging\build_windows.ps1` — run this from the project root too, not
   from inside `packaging\`.
4. Run `dist\RomM-RetroArch-Sync\RomM-RetroArch-Sync.exe`, or build a proper
   installer with `iscc packaging\installer.iss` (needs
   [Inno Setup](https://jrsoftware.org/isinfo.php)).

## Running from source instead (no build)

```
pip install -r requirements-windows.txt
python src\romm_sync_app.py
```
(Still needs the GTK4 runtime above on `PATH` first — GTK4/PyGObject/
libadwaita aren't plain `pip install`able on Windows.)

## License

GPL-3.0, same as the upstream project — see `LICENSE`.
