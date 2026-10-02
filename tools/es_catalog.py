#!/usr/bin/env python3
"""Cache ES's recognized catalog for dashboards; check selected targets live."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shlex
import sys
import tempfile

import paramiko
from gamelib import DEFAULT_PI_HOST

READER = '/usr/bin/python3 /opt/ai-arcade/es-state/read_catalog.py'


def remote(ssh, arguments=''):
    _, stdout, stderr = ssh.exec_command(READER + ' ' + arguments, timeout=45)
    output = stdout.read().decode('utf-8')
    error = stderr.read().decode('utf-8')
    if stdout.channel.recv_exit_status():
        raise RuntimeError(error.strip() or output.strip())
    return json.loads(output)


def identity(catalog):
    return {key: catalog[key] for key in ('schema_version', 'boot_id', 'pid', 'generation')}


def load_cache(path, endpoint):
    try:
        cache = json.loads(path.read_text(encoding='utf-8'))
        if (cache['cache_schema_version'] != 1 or cache['endpoint'] != endpoint
                or cache['catalog']['kind'] != 'catalog'
                or cache['catalog']['schema_version'] != 1):
            return None
        identity(cache['catalog'])
        return cache
    except (OSError, ValueError, KeyError, TypeError):
        return None


def save_cache(path, endpoint, catalog):
    cache = {'cache_schema_version': 1, 'endpoint': endpoint,
             'fetched_at': datetime.now(timezone.utc).isoformat(), 'catalog': catalog}
    path.parent.mkdir(parents=True, exist_ok=True)
    name = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=str(path.parent),
                                         prefix='.catalog-', suffix='.tmp', delete=False) as output:
            name = output.name
            json.dump(cache, output, ensure_ascii=False)
            output.write('\n')
        os.replace(name, str(path))
    finally:
        if name and os.path.exists(name):
            os.unlink(name)
    return cache


def summary(catalog):
    systems = catalog['systems']
    games = [entry for system in systems if system['is_game_system']
             for entry in system['entries'] if entry['type'] == 'game']
    return {'loaded_systems': len(systems),
            'visible_systems': sum(bool(system['visible']) for system in systems),
            'game_memberships': len(games),
            'unique_games': len({entry['game_id'] for entry in games}),
            'visible_unique_games': len({entry['game_id'] for entry in games if entry['visible']}),
            'playability': 'unknown'}


def synchronize(ssh, path, endpoint, refresh=False):
    cache = load_cache(path, endpoint)
    current = remote(ssh, '--identity' + (' --refresh' if refresh else ''))
    if cache is not None and identity(cache['catalog']) == current:
        return cache, True
    catalog = remote(ssh)
    return save_cache(path, endpoint, catalog), False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', default=DEFAULT_PI_HOST)
    parser.add_argument('--user', default='pi')
    parser.add_argument('--key', default=str(Path.home() / '.ssh/id_rsa'))
    parser.add_argument('--port', type=int, default=22)
    parser.add_argument('--cache', type=Path, help='Override the local dashboard cache path')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--refresh', action='store_true', help='Request a new snapshot from ES memory')
    mode.add_argument('--offline', action='store_true', help='Read cached data without live validation')
    mode.add_argument('--game-id', help='Refresh and check one canonical game ID; does not launch it')
    parser.add_argument('--json', action='store_true', help='Print complete cache envelope instead of counts')
    args = parser.parse_args()
    endpoint = {'host': args.host, 'port': args.port, 'user': args.user}
    key = hashlib.sha256(json.dumps(endpoint, sort_keys=True).encode()).hexdigest()[:16]
    path = args.cache or Path(__file__).resolve().parents[1] / '.manifests/es-catalog' / (key + '.json')
    ssh = None
    try:
        if args.offline:
            cache = load_cache(path, endpoint)
            if cache is None:
                raise RuntimeError('No valid cache for this Pi; fetch it online first')
            reused = True
        else:
            ssh = paramiko.SSHClient()
            ssh.load_system_host_keys()
            ssh.set_missing_host_key_policy(paramiko.RejectPolicy())
            ssh.connect(args.host, port=args.port, username=args.user,
                        key_filename=str(Path(args.key).expanduser()), timeout=10)
            if args.game_id is not None:
                result = remote(ssh, '--game-id ' + shlex.quote(args.game_id))
                print(json.dumps(result, indent=2))
                return 0 if result['recognized'] else 1
            cache, reused = synchronize(ssh, path, endpoint, args.refresh)
        output = dict(cache) if args.json else summary(cache['catalog'])
        output.update(cache_path=str(path.resolve()), cache_reused=reused,
                      live_verified=not args.offline, fetched_at=cache['fetched_at'])
        print(json.dumps(output, indent=2))
        return 0
    except (OSError, ValueError, KeyError, TypeError, RuntimeError, paramiko.SSHException) as exc:
        print('ERROR:', exc, file=sys.stderr)
        return 1
    finally:
        if ssh is not None:
            ssh.close()


if __name__ == '__main__':
    sys.exit(main())
