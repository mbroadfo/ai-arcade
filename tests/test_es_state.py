import importlib.util
import os
from pathlib import Path

import pytest
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'pi/es_state' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_fresh_state_preserves_selection():
    state = {'schema_version': 1, 'source': 'emulationstation', 'boot_id': 'boot',
             'monotonic_ms': 1000, 'system': {'name': 'nes'}}
    result = load('read_state').validate(state, 'boot', 1200, 'emulationstation')
    assert result['age_ms'] == 200
    assert result['system']['name'] == 'nes'


@pytest.mark.parametrize('boot, now, process', [
    ('old', 1200, 'emulationstation'),
    ('boot', 11001, 'emulationstation'),
    ('boot', 999, 'emulationstation'),
    ('boot', 1200, 'other'),
])
def test_invalid_producer_or_age_is_rejected(boot, now, process):
    state = {'schema_version': 1, 'source': 'emulationstation',
             'boot_id': 'boot', 'monotonic_ms': 1000}
    with pytest.raises(ValueError):
        load('read_state').validate(state, boot, now, process)


def test_patch_is_idempotent_and_rejects_unknown_source(tmp_path):
    main = tmp_path / 'es-app/src/main.cpp'
    window = tmp_path / 'es-core/src/Window.h'
    main.parent.mkdir(parents=True)
    window.parent.mkdir(parents=True)
    main.write_text('#include "EmulationStation.h"\n\t\tif(window.isSleeping())\n'
                    'SDL_WaitEventTimeout(&event, PowerSaver::getTimeout())')
    window.write_text('\tbool getAllowSleep();')
    patcher = load('patch_source')
    header = ROOT / 'pi/es_state/ArcadeState.h'
    patcher.patch(tmp_path, header)
    first = main.read_bytes()
    os.utime(main, (1000, 1000))
    unchanged_mtime = main.stat().st_mtime_ns
    patcher.patch(tmp_path, header)
    assert main.read_bytes() == first
    assert main.stat().st_mtime_ns == unchanged_mtime
    assert main.read_text().count('publishArcadeState(window)') == 1
    window.write_text('unsupported source')
    with pytest.raises(RuntimeError, match='Unsupported ES source'):
        patcher.patch(tmp_path, header)


def test_old_heartbeat_patch_is_upgraded(tmp_path):
    main = tmp_path / 'es-app/src/main.cpp'
    window = tmp_path / 'es-core/src/Window.h'
    main.parent.mkdir(parents=True)
    window.parent.mkdir(parents=True)
    main.write_text('#include "EmulationStation.h"\n#include "ArcadeState.h"\n'
                    '\t\tpublishArcadeState(window);\n\n\t\tif(window.isSleeping())\n'
                    'SDL_WaitEventTimeout(&event, 250 /* AI Arcade heartbeat */)')
    window.write_text('\tbool getAllowSleep();')
    load('patch_source').patch(tmp_path, ROOT / 'pi/es_state/ArcadeState.h')
    assert 'arcadeEventTimeout(PowerSaver::getTimeout())' in main.read_text()
    assert main.read_text().count('publishArcadeState(window)') == 1


def test_restart_refuses_unmanaged_or_busy_es(monkeypatch, tmp_path):
    monkeypatch.syspath_prepend(str(ROOT / 'pi/es_state'))
    installer = load('install_state')
    proc = tmp_path / 'proc'
    (proc / '10/task/10').mkdir(parents=True)
    (proc / '9').mkdir()
    (proc / '10/status').write_text('PPid:\t9\n')
    (proc / '9/status').write_text('PPid:\t1\n')
    (proc / '9/cmdline').write_bytes(b'/bin/sh\0unmanaged\0')
    monkeypatch.setattr(installer, 'Path', lambda value: tmp_path / str(value).lstrip('/'))
    with pytest.raises(RuntimeError, match='wrapper'):
        installer.check_restart(10)
    (proc / '9/cmdline').write_bytes(b'/bin/sh\0' + str(installer.ES_DIR / 'emulationstation.sh').encode() + b'\0')
    (proc / '42').mkdir()
    (proc / '42/status').write_text('PPid:\t10\n')
    with pytest.raises(RuntimeError, match='running child'):
        installer.check_restart(10)
    (proc / '42/status').write_text('PPid:\t1\n')
    installer.check_restart(10)


def test_restart_marker_can_be_removed_by_es_user(monkeypatch, tmp_path):
    monkeypatch.syspath_prepend(str(ROOT / 'pi/es_state'))
    installer = load('install_state')
    marker = tmp_path / 'es-restart'
    process = Mock()
    process.stat.return_value = Mock(st_uid=1000, st_gid=1000)
    monkeypatch.setattr(installer, 'Path', lambda value: marker if value == '/tmp/es-restart' else process)
    monkeypatch.setattr(installer, 'check_restart', Mock())
    chown = Mock()
    kill = Mock()
    monkeypatch.setattr(installer.os, 'chown', chown, raising=False)
    monkeypatch.setattr(installer.os, 'kill', kill)
    installer.restart_es(10)
    assert marker.exists()
    chown.assert_called_once_with(str(marker), 1000, 1000)
    kill.assert_called_once_with(10, installer.signal.SIGTERM)


def test_navigation_requires_new_sequence_and_same_process(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / 'tools'))
    spec = importlib.util.spec_from_file_location('navigation', ROOT / 'tools/test_es_navigation.py')
    nav = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(nav)
    before = dict(pid=10, sequence=1, view='system_select', overlay_open=False,
                  screensaver_active=False, sleeping=False, system={'name': 'nes'})
    changed = dict(before, system={'name': 'snes'})
    fresh = dict(changed, sequence=2)
    fetch = Mock(side_effect=[changed, fresh])
    monkeypatch.setattr(nav, 'fetch', fetch)
    monkeypatch.setattr(nav.time, 'sleep', Mock())
    assert nav.wait_changed(None, before) == fresh
    assert fetch.call_count == 2
    monkeypatch.setattr(nav, 'fetch', Mock(return_value=dict(fresh, pid=11)))
    with pytest.raises(RuntimeError, match='restarted'):
        nav.wait_changed(None, before)


@pytest.mark.parametrize('field,value', [('overlay_open', True), ('sleeping', True),
                                        ('screensaver_active', True), ('view', 'unknown')])
def test_navigation_refuses_noncarousel_state(monkeypatch, field, value):
    monkeypatch.syspath_prepend(str(ROOT / 'tools'))
    from test_es_navigation import navigable_system
    state = dict(view='system_select', overlay_open=False, sleeping=False,
                 screensaver_active=False, system={'name': 'nes'})
    state[field] = value
    with pytest.raises(RuntimeError, match='carousel'):
        navigable_system(state)
