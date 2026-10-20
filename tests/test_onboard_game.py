"""tools/onboard_game.py: the parts that need no Pi."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "tools")]

import onboard_game as og  # noqa: E402
import panel_profiles as pp  # noqa: E402

XML = """<mame build="0.251"><machine name="newgame"><description>New Game</description><year>1982</year>
<input players="2" coins="2"><control type="joy" player="1" ways="4"/><control type="trackball" player="1"/>
<control type="joy" player="2" ways="4"/></input></machine></mame>"""

PROBE = """noise
COIN tag=:DSW1 name=Coinage mask=3 defvalue=3
COINSETTING name=Coinage value=3 label=2 Coins/1 Credit
COINSETTING name=Coinage value=1 label=1 Coin/1 Credit
COINSETTING name=Coinage value=0 label=Free Play
COIN tag=:DSW2 name=Coin B mask=12 defvalue=4
COINSETTING name=Coin B value=4 label=1 Coin/3 Credits
TURNS p2=5 cocktail=5 real=0 cabinet_dip=yes p3=0
"""


def test_the_games_own_description_is_read_from_mames_xml():
    info = og.parse_listxml(XML, "newgame")
    assert info["title"] == "New Game" and info["players"] == 2
    assert {c["type"] for c in info["controls"]} == {"joy", "trackball"}
    assert og.parse_listxml(XML, "other") is None


def test_the_probe_output_gives_turns_and_the_coin_switches():
    probe = og.parse_probe(PROBE)
    assert probe["turns"] == {"p2": 5, "cocktail": 5, "real": 0, "cabinet_dip": True, "p3": 0}
    assert [f["name"] for f in probe["coin"]] == ["Coinage", "Coin B"]
    assert probe["coin"][0]["settings"] == {3: "2 Coins/1 Credit", 1: "1 Coin/1 Credit", 0: "Free Play"}
    assert og.parse_probe("nothing useful")["turns"] is None


def test_play_mode_matches_the_classification_tool():
    turns = {"p2": 5, "cocktail": 5, "real": 0, "cabinet_dip": True, "p3": 0}
    assert og.play_mode(turns, 2) == "turns" and og.play_mode(turns, 1) == "single"
    assert og.play_mode({**turns, "real": 2}, 2) == "simultaneous" and og.play_mode(turns, 4) == "simultaneous"
    assert og.play_mode(None, 2) is None


def test_one_coin_is_set_only_where_the_factory_differs_and_a_setting_exists():
    dips, notes = og.one_coin_dips(og.parse_probe(PROBE)["coin"])
    assert dips == [{"tag": ":DSW1", "mask": 3, "defvalue": 3, "value": 1, "name": "Coinage"}]
    assert len(notes) == 1 and notes[0].startswith("Coin B: no one-coin-one-credit setting")
    already = [{"tag": ":D", "name": "Coinage", "mask": 3, "defvalue": 1, "settings": {1: "1 Coin/1 Credit"}}]
    assert og.one_coin_dips(already) == ([], [])


def test_merge_keeps_what_a_person_wrote_and_adds_what_was_found():
    info = og.parse_listxml(XML, "newgame")
    new = og.merge_controls(None, "newgame", "newgame", info, "trackball", "turns", [])
    assert new["roms"] == ["newgame"] and new["pointer"] == "trackball" and new["play"] == "turns" and "mame" not in new
    mine = {"roms": ["newgame"], "emulator": "mame-0.251", "panel": {"P1_BUTTON1": ["P2", "FLIGHT1"]}, "dip": {"tag": ":A"}}
    merged = og.merge_controls(mine, "newgame", "newgame2", info, None, "single", [{"tag": ":DSW1"}])
    assert merged["emulator"] == "mame-0.251" and merged["panel"] == mine["panel"]  # kept
    assert merged["mame"] == ["newgame2"] and merged["play"] == "single" and merged["dips"] == [{"tag": ":DSW1"}] and "dip" not in merged


def test_the_catalog_entry_is_added_or_replaced():
    cat = {"generated": "x", "games": [{"zip": "b"}, {"zip": "a", "title": "old"}]}
    out = og.update_catalog(cat, "a", "a", "mame-0.251", {"title": "new"})
    assert [g["zip"] for g in out["games"]] == ["a", "b"] and out["games"][0]["title"] == "new"


def test_es_extensions_come_from_es_systems_cfg():
    cfg = "<systemList><system><name>nes</name><extension>.nes .zip .NES</extension></system></systemList>"
    assert og.es_extensions(cfg, "nes") == {".nes", ".zip"} and og.es_extensions(cfg, "snes") is None


def test_a_game_with_two_coin_switches_gets_both_in_its_installed_cfg(tmp_path):
    cfg = pp.set_game_dip(None, "newgame", ":DSW1", 3, 3, 1)
    cfg = pp.set_game_dip(cfg, "newgame", ":DSW2", 12, 4, 8)
    assert cfg.count("DIPSWITCH") == 2 and ':DSW1' in cfg and ':DSW2' in cfg
