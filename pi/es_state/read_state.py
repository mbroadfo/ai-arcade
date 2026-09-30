#!/usr/bin/env python3
"""Read ES state and reject snapshots from an old boot, dead process, or stalled UI."""
import json
from pathlib import Path
import sys
import time

STATE = Path('/run/ai-arcade/es-state.json')


def validate(state, boot_id, now_ms, process_name):
    if state.get('schema_version') != 1 or state.get('source') != 'emulationstation':
        raise ValueError('Unsupported ES state schema')
    if state.get('boot_id') != boot_id:
        raise ValueError('ES state belongs to a different boot')
    if process_name != 'emulationstation':
        raise ValueError('ES state producer is not running')
    age = now_ms - state['monotonic_ms']
    if not 0 <= age <= 10000:
        raise ValueError('ES state is stale (UI stopped, blocked, or running a game)')
    return dict(state, age_ms=round(age))


def read_state():
    state = json.loads(STATE.read_text())
    pid = int(state['pid'])
    process_name = Path('/proc/{}/comm'.format(pid)).read_text().strip()
    # Linux comm truncates names to 15 characters.
    if process_name == 'emulationstatio':
        process_name = 'emulationstation'
    boot_id = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    return validate(state, boot_id, time.monotonic() * 1000, process_name)


def main():
    try:
        print(json.dumps(read_state(), indent=2, ensure_ascii=False))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({'ok': False, 'error': str(exc)}))
        return 1


if __name__ == '__main__':
    sys.exit(main())
