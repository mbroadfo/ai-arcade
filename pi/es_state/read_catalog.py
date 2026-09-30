#!/usr/bin/env python3
"""Read ES's loaded catalog, optionally requesting a new main-thread snapshot."""
import argparse
import json
from pathlib import Path
import sys
import time

from read_state import read_state

CATALOG = Path('/run/ai-arcade/es-catalog.json')
REQUEST = Path('/run/ai-arcade/es-catalog.request')


def identity(catalog):
    return {key: catalog[key] for key in ('schema_version', 'boot_id', 'pid', 'generation')}


def validate(catalog, state, now_ms):
    if (catalog.get('schema_version') != 1 or catalog.get('kind') != 'catalog'
            or catalog.get('source') != 'emulationstation'):
        raise ValueError('Unsupported ES catalog schema')
    if any(catalog.get(key) != state[key] for key in ('pid', 'boot_id')):
        raise ValueError('Catalog belongs to a different ES process or boot')
    if not 0 <= now_ms - catalog['monotonic_ms'] <= 90000:
        raise ValueError('ES catalog is stale; request a refresh')
    if not isinstance(catalog.get('systems'), list):
        raise ValueError('Invalid ES catalog systems')
    return catalog


def read_catalog(refresh=False, timeout=30):
    requested_ms = int(time.monotonic() * 1000) if refresh else None
    if refresh:
        REQUEST.touch()
    deadline = time.monotonic() + timeout
    while True:
        try:
            catalog = json.loads(CATALOG.read_text(encoding='utf-8'))
            validate(catalog, read_state(), time.monotonic() * 1000)
            if requested_ms is None or catalog['monotonic_ms'] >= requested_ms:
                return catalog
        except (OSError, ValueError, KeyError, TypeError):
            if not refresh or time.monotonic() >= deadline:
                raise
        if time.monotonic() >= deadline:
            raise RuntimeError('ES did not complete the requested catalog refresh')
        time.sleep(0.25)


def find_game(catalog, game_id):
    memberships = [dict(system=system['name'], system_is_game=system['is_game_system'], **entry)
                   for system in catalog['systems'] for entry in system['entries']
                   if entry.get('game_id') == game_id and entry['type'] == 'game']
    return {'game_id': game_id, 'recognized': bool(memberships),
            'visible': any(entry['visible'] for entry in memberships),
            'playability': 'unknown', 'catalog_identity': identity(catalog),
            'memberships': memberships}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--refresh', action='store_true')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--identity', action='store_true')
    mode.add_argument('--check', action='store_true')
    mode.add_argument('--game-id', help='Refresh and check an underlying game identifier')
    args = parser.parse_args()
    try:
        catalog = read_catalog(refresh=args.refresh or args.game_id is not None)
        if args.game_id is not None:
            result = find_game(catalog, args.game_id)
        else:
            result = identity(catalog) if args.identity else catalog
        if not args.check:
            print(json.dumps(result, ensure_ascii=True))
        return 0
    except (OSError, ValueError, KeyError, TypeError, RuntimeError) as exc:
        print(json.dumps({'ok': False, 'error': str(exc)}), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
