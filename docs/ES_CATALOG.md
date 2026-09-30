# EmulationStation catalog for dashboards and AI selection

The catalog comes from the running ES process's loaded `SystemData` and
`FileData` objects. No controller navigation, screenshot capture, or game launch
is required to enumerate it. It includes loaded systems, collections, games,
folders, and metadata, including entries excluded by current display filters.
Systems ES never loaded (for example, empty systems omitted at startup) are not
inventoried. Files added to disk are not recognized until ES loads them.

## Deploy, fetch, and refresh

From the repository root and activated virtual environment:

```powershell
python .\tools\install_pi.py --host 192.168.10.155 --timeout 60 --with-es-state
python .\tools\es_catalog.py --host 192.168.10.155
python .\tools\es_catalog.py --host 192.168.10.155 --refresh
```

The first catalog command prints counts and the location of a dashboard-ready JSON
cache under `.manifests/es-catalog/`. Later online calls check the Pi's catalog
identity and reuse the cache when unchanged. `--refresh` asks ES's main thread to
produce a new snapshot; it does not rescan the filesystem or restart ES.

The cache is keyed by SSH host, port, and user. `--cache PATH` selects a different
file. Cache replacement is atomic, and failed fetches preserve the previous copy.
Cached library paths and metadata are excluded from Git through `.manifests/`.

```powershell
# Complete cache envelope for a dashboard or another program:
python .\tools\es_catalog.py --host 192.168.10.155 --json
# Explicitly read the saved catalog without contacting the Pi:
python .\tools\es_catalog.py --host 192.168.10.155 --offline --json
```

Offline results are marked `live_verified: false`; online errors never silently
fall back to cached data. The saved file contains `cache_schema_version`,
`endpoint`, `fetched_at`, and `catalog`. It is a historical snapshot: the dashboard
must retain that timestamp and show offline/stale status when it cannot validate
the source. The CLI adds live-validation/cache-reuse flags to its output, rather
than persisting a claim that the cache remains live indefinitely.

## Catalog schema version 1

The Pi publishes `/run/ai-arcade/es-catalog.json` atomically. Its envelope has
`source: emulationstation`, `kind: catalog`, `schema_version`, `boot_id`, `pid`,
`generation`, `monotonic_ms`, and `systems`.

Each system has its internal `name`, `full_name`, `root_path`, `is_collection`,
`is_game_system`, `visible`, and a flat `entries` array. Entries have:

- `id`: stable membership identity for this system and path.
- `game_id`: stable underlying game identity, shared across collection appearances;
  null for folders.
- `name`, `path`, `parent_path`, `type`, `source_system`, `source_path`, and metadata.
- `visible`: ES includes the entry through its current system and ancestor-folder
  visibility/filter rules. This means reachable in the current filtered library,
  not necessarily on screen at this moment.
- `playability: unknown`: recognition alone does not validate launching, controls,
  observation support, or gameplay.

IDs are opaque strings derived from the internal system name and full path, using
a length prefix to avoid delimiter collisions. They survive refreshes/restarts,
but change when the source system or path changes. Collection membership `id`s
remain distinct while `game_id` lets the dashboard deduplicate games.

ES's maintenance panel can contain launchable entries too. A game chooser should
require `is_game_system: true` and `type: game`, deduplicate by `game_id`, and
apply its separately maintained control/observation capability requirements.
There is no claim of validated playability or AI capability in this catalog.

## Refresh lifecycle and live checks

ES exports at startup, after its `reloadAll` hook invalidates the catalog, on an
explicit refresh request, and once per minute to capture other metadata/filter
changes. Export streams JSON to a temporary file from the main thread and renames
it after completion. Very large libraries can briefly pause UI processing during
export; the full catalog is not part of the four-times-per-second selection state.

The reader checks live state, matching boot/process identity, and catalog age
(at most 90 seconds). A refresh waits up to 30 seconds for a snapshot created after
the request. Requests can coalesce when multiple clients refresh concurrently.
`generation` identifies an export, not a content hash; a periodic export can
invalidate the local cache even if the contents are unchanged.

Before an AI acts on a chosen `game_id`, check it live:

```powershell
python .\tools\es_catalog.py --host 192.168.10.155 --game-id '<game_id from the catalog>'
python .\tools\es_state.py --host 192.168.10.155
```

The game-ID check forces a fresh snapshot and returns `recognized`, `visible`,
and its memberships. An absent ID returns a nonzero exit code. A recognized but
hidden entry has `visible: false`; callers must check both fields. This is only
a read-only preflight and never launches a game. Selection can change afterward,
so navigation still needs live state checks immediately before launch.

## Verification

`tools/verify_pi.py` checks catalog availability after catalog support is installed.
Deployment installs the reader and activation waits for both live state and the
catalog. The existing `--restore-es` automation disables both extra checks when
restoring the original frontend. Unit tests cover caching, endpoint isolation,
collection deduplication, freshness, refresh ordering, and target lookup.

Validated on the cabinet on 2026-09-30: 8 loaded panels, 283 recognized game
entries, and 13 additional RetroPie maintenance entries. Online fetch, unchanged
cache reuse, explicit refresh, offline labeling, known/missing game-ID lookup,
repeat deployment without recompilation, and the installed Pi verifier passed.
All 45 local tests passed. No games were launched. These counts describe that
snapshot and will change as ES's loaded library changes.
