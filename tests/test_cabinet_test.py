from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import cabinet_test as cabinet


def state(path, **changes):
    value = dict(boot_id='boot', pid=12, sequence=1, overlay_open=False,
                 sleeping=False, screensaver_active=False, view='game_list',
                 system={'name': 'arcade'},
                 selection={'path': path, 'type': 'game', 'name': path})
    value.update(changes)
    return value


def test_coin_start_mapping():
    assert cabinet.coin_start_actions('') == ('COIN', 'START')
    assert cabinet.coin_start_actions('input_player1_btn_select = "3"\ninput_player1_btn_start = "2"') == ('START', 'COIN')
    with pytest.raises(RuntimeError):
        cabinet.coin_start_actions('input_player1_btn_start = "8"')


def test_exact_rom_is_required_before_select():
    current = state('/other.zip')
    actions = []

    def tap(action):
        actions.append(action)
        current.update(state(cabinet.TARGET, sequence=2))

    cabinet.launch(lambda: dict(current), tap, lambda _: None)
    assert actions == ['DOWN', 'BUTTON_1']


def test_overlay_blocks_launch():
    with pytest.raises(RuntimeError, match='menu/dialog'):
        cabinet.launch(lambda: state(cabinet.TARGET, overlay_open=True),
                       lambda _: pytest.fail('Unexpected input'))


def test_stalled_navigation_does_not_select():
    actions = []
    with pytest.raises(RuntimeError, match='did not change'):
        cabinet.launch(lambda: state('/other.zip'), actions.append, lambda _: None)
    assert actions == ['DOWN']
