# Structured EmulationStation observation

AI Arcade reads the frontend's own C++ objects. The exporter reports the selected
system or game, not pixels, OCR, or inferred positions from previous button presses.

## Install and update

From the repository root and activated Windows virtual environment:

```powershell
python .\tools\install_pi.py --host 192.168.10.155 --timeout 60 --with-es-state
```

The opt-in flag builds and installs observation support as well as the controller
infrastructure. The first native build on a Pi 3 can take a while; progress is
streamed over SSH. The installer installs missing build dependencies, downloads
checksum-verified source archives, applies the repository patch, and builds with
one compiler process to limit memory use. Successful builds are cached by source
revision and patch content; repeat installation reuses the verified binary.

Supported baseline: RetroPie EmulationStation `v2.10.1rp`, source commit
`c9d905c31acf4b92d0a76b76c5cdf49e2b266d43`, with its pinned pugixml submodule
`d2deb420bc70369faa12785df2b5dd4d390e523d`. The current build settings target the
Pi 3 legacy VideoCore renderer. The installer rejects other ES package revisions.
It does not upgrade ES to the latest upstream version.

The original binary is saved once at
`/opt/ai-arcade/es-state/emulationstation.original`. Replacement uses an atomic
rename. Activation requests a restart through RetroPie's existing
`emulationstation.sh` wrapper and waits for a fresh snapshot from the new binary.
Run installation while ES is idle in its carousel or game list. The installer refuses activation
if ES has a child process or is not managed by that wrapper.

The installer creates `/etc/tmpfiles.d/ai-arcade-state.conf` so the RAM-backed
`/run/ai-arcade` directory is recreated with the ES user's ownership at every boot.
The existing RetroPie boot process starts the patched ES; no Windows process is
needed to keep observation running. Once enabled, `tools/verify_pi.py` includes a
live ES state check, with the same readiness retry window as the controller checks.

## Read and test

```powershell
python .\tools\es_state.py --host 192.168.10.155
python .\tools\test_es_navigation.py --host 192.168.10.155
```

Both commands support `--user`, `--key`, and `--port` for SSH. They use the same
trusted-host-key policy as the installer. Observation uses SSH and adds no TCP
listener. The navigation test requires an awake, unobstructed system carousel or
game list (with ES's quick system selection enabled for game lists).
It reads the current selection, taps RIGHT, checks a new selection, taps LEFT,
checks return to the original selection, and releases the controllers. It never
sends a game-launch button. It fails if ES restarts or the expected change does not
arrive within five seconds. At least two visible systems are required.

After reboot, run the verifier and state reader again to check boot persistence.

## State contract (schema version 1)

`/run/ai-arcade/es-state.json` is atomically replaced by ES's main thread about
four times per second. Power-saving event waits are capped at 250 ms to maintain
the heartbeat. These are logical UI selections; an animation can still be moving
toward the selected item when a snapshot is published.

Fields include:

- `source`, `schema_version`, `pid`, `boot_id`, `sequence`, and `monotonic_ms`.
- `view`: `system_select`, `game_list`, or `unknown`.
- `system`: internal name and display name, or null.
- `selection`: name, path, game/folder/placeholder type, and metadata, or null on the carousel.
- `overlay_open`, `screensaver_active`, and `sleeping`.
- `age_ms`: computed by the reader on the Pi, using the same monotonic clock.

The reader rejects snapshots from another boot, a dead/non-ES producer, an unknown
schema, or more than ten seconds ago. A stalled ES or an ES waiting for a running
game therefore stops providing valid observations. This is frontend observation;
it does not expose emulator/game memory. During the freshness window, the last
snapshot can still predate a blocked UI. Callers confirming an action must require
a newer sequence from the same producer, as the navigation test does.

When an overlay is open, system/selection fields describe the underlying view.
This first patch reports the presence of an overlay, not its labels or selected
menu option. Screensaver and sleep flags must be checked before interpreting the
underlying selection as the visible page. Game paths and metadata remain local
to the Pi and the requesting SSH client.

## Restore the original frontend

```powershell
python .\tools\install_pi.py --host 192.168.10.155 --restore-es
```

This automated path restores the saved original ES binary, requests a wrapper
restart, and disables the extra verification check. Controller service and
emulator mappings remain installed. Reinstall with `--with-es-state` to enable
observation again.

## Development

`pi/es_state/patch_source.py` checks exact source anchors and is safe to apply
repeatedly. `ArcadeState.h` reads the carousel from `SystemView::getSelected()`;
`ViewController`'s remembered system is not used as the carousel cursor. In game
lists it uses `IGameListView::getCursor()` and `FileData` metadata. The Window
accessor exposes screensaver presence. JSON serialization uses ES's existing
RapidJSON dependency.

Run local regression tests with `python -m pytest -q`. The native Pi build checks
C++ compatibility; the separate navigation command checks actual state changes.
An upstream RetroPie ES reinstall can replace the patched binary; reinstall this
feature only after confirming the package revision is still supported.

## Validation on the cabinet

Validated on the Pi at `192.168.10.155` on 2026-09-30:

- Native build and activation succeeded; state reported the Arcade game list and
  highlighted Amidar entry with its path and metadata.
- The live directional test observed `arcade → atari2600 → arcade`, without
  launching a game.
- Repeat installation reused the compiled binary, retained the same ES PID, and
  preserved the original binary's SHA-256 checksum.
- After reboot, readiness verification waited for ES startup and passed all
  controller, mapping, boot-enable, and live-state checks. The directional test
  passed again with the same system sequence.
- All 34 local regression tests and repository hygiene checks passed.

The original-binary rollback command is provided but was not exercised on the
live cabinet during this validation. Overlay labels and in-game state remain
outside this patch's scope.
