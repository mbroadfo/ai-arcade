import importlib.util
from pathlib import Path
from unittest.mock import Mock

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load(relative):
    spec = importlib.util.spec_from_file_location(Path(relative).stem, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def catalog():
    def game(entry_id, visible=True):
        return dict(id=entry_id, game_id='3:nes/roms/a.zip', type='game', visible=visible,
                    name='A "quoted" game', path='/roms/a.zip', playability='unknown')
    return dict(schema_version=1, kind='catalog', source='emulationstation', pid=100,
                boot_id='boot', generation=1, monotonic_ms=1000,
                systems=[dict(name='nes', full_name='NES', is_game_system=True,
                              is_collection=False, visible=True, entries=[game('original')]),
                         dict(name='favorites', full_name='Favorites', is_game_system=True,
                              is_collection=True, visible=True, entries=[game('collection')]),
                         dict(name='retropie', is_game_system=False, visible=True,
                              entries=[dict(game('config'), game_id='config')])])


def test_counts_deduplicate_collections_and_exclude_maintenance(catalog):
    result = load('tools/es_catalog.py').summary(catalog)
    assert result['unique_games'] == 1
    assert result['game_memberships'] == 2
    assert result['playability'] == 'unknown'


def test_cache_roundtrip_and_endpoint_isolation(catalog, tmp_path):
    tool = load('tools/es_catalog.py')
    path = tmp_path / 'catalog.json'
    endpoint = dict(host='pi', port=22, user='pi')
    tool.save_cache(path, endpoint, catalog)
    assert tool.load_cache(path, endpoint)['catalog'] == catalog
    assert tool.load_cache(path, dict(endpoint, host='other')) is None
    path.write_text('broken JSON')
    assert tool.load_cache(path, endpoint) is None


def test_unchanged_catalog_avoids_full_download(catalog, tmp_path, monkeypatch):
    tool = load('tools/es_catalog.py')
    path = tmp_path / 'catalog.json'
    endpoint = dict(host='pi', port=22, user='pi')
    tool.save_cache(path, endpoint, catalog)
    remote = Mock(return_value=tool.identity(catalog))
    monkeypatch.setattr(tool, 'remote', remote)
    cache, reused = tool.synchronize(None, path, endpoint)
    assert reused and cache['catalog'] == catalog
    remote.assert_called_once_with(None, '--identity')


def test_restart_invalidates_cache(catalog, tmp_path, monkeypatch):
    tool = load('tools/es_catalog.py')
    path = tmp_path / 'catalog.json'
    endpoint = dict(host='pi', port=22, user='pi')
    tool.save_cache(path, endpoint, catalog)
    current = dict(catalog, pid=200)
    monkeypatch.setattr(tool, 'remote', Mock(side_effect=[tool.identity(current), current]))
    cache, reused = tool.synchronize(None, path, endpoint)
    assert not reused and cache['catalog']['pid'] == 200


@pytest.mark.parametrize('changes', [{'pid': 1}, {'boot_id': 'old'}, {'schema_version': 2},
                                   {'monotonic_ms': -90000}, {'kind': 'state'}])
def test_invalid_catalog_is_rejected(catalog, changes, monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / 'pi/es_state'))
    reader = load('pi/es_state/read_catalog.py')
    with pytest.raises(ValueError):
        reader.validate(dict(catalog, **changes), {'pid': 100, 'boot_id': 'boot'}, 2000)


def test_target_check_recognized_is_not_playable(catalog, monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / 'pi/es_state'))
    reader = load('pi/es_state/read_catalog.py')
    found = reader.find_game(catalog, '3:nes/roms/a.zip')
    assert found['recognized'] and found['visible']
    assert len(found['memberships']) == 2
    assert found['playability'] == 'unknown'
    assert not reader.find_game(catalog, 'absent')['recognized']


def test_refresh_waits_for_snapshot_after_request(catalog, monkeypatch, tmp_path):
    monkeypatch.syspath_prepend(str(ROOT / 'pi/es_state'))
    reader = load('pi/es_state/read_catalog.py')
    import json
    old = dict(catalog, monotonic_ms=500)
    new = dict(catalog, monotonic_ms=1200, generation=2)
    fake = Mock()
    fake.read_text.side_effect = [json.dumps(old), json.dumps(new)]
    monkeypatch.setattr(reader, 'CATALOG', fake)
    monkeypatch.setattr(reader, 'REQUEST', tmp_path / 'request')
    monkeypatch.setattr(reader, 'read_state', lambda: dict(pid=100, boot_id='boot'))
    monkeypatch.setattr(reader.time, 'monotonic', Mock(side_effect=[1, 1, 1, 1, 2]))
    monkeypatch.setattr(reader.time, 'sleep', Mock())
    new['monotonic_ms'] = 1500
    fake.read_text.side_effect = [json.dumps(old), json.dumps(new)]
    assert reader.read_catalog(refresh=True)['generation'] == 2
