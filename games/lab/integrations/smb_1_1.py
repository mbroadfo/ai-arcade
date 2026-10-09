"""Super Mario Bros. World 1-1, read from NES RAM.

Addresses follow the World ROM map used by gym-super-mario-bros (MIT): page and
x at 0x6D/0x86, the three time digits at 0x07F8, player state at 0x000E, the
flagpole enemy id 0x31 with float-state 3. Power-on is World 1-1, so the
integration only has to get past the title.
"""
from __future__ import annotations

SMB_ACTIONS: list[tuple[str, ...]] = [
    (),
    ("RIGHT",),
    ("RIGHT", "A"),
    ("RIGHT", "B"),
    ("RIGHT", "A", "B"),
    ("A",),
    ("LEFT",),
]

_STAGE_OVER_ENEMIES = (0x2D, 0x31)
_ENEMY_TYPE_ADDRESSES = (0x0016, 0x0017, 0x0018, 0x0019, 0x001A)
_STATUS = {0: "small", 1: "tall"}


def _byte(ram: bytes, address: int) -> int:
    if address < 0 or address >= len(ram):
        return 0
    return ram[address]


def _digits(ram: bytes, address: int, length: int) -> int:
    chars = [str(_byte(ram, address + offset) % 10) for offset in range(length)]
    return int("".join(chars))


def _player_state(ram: bytes) -> int:
    return _byte(ram, 0x000E)


def _y_viewport(ram: bytes) -> int:
    return _byte(ram, 0x00B5)


def describe(ram: bytes) -> dict:
    """Facts the scoreboard and the RAM model are allowed to use."""
    state = _player_state(ram)
    y_pixel = _byte(ram, 0x03B8)
    viewport = _y_viewport(ram)
    if viewport < 1:
        y_pos = 255 + (255 - y_pixel)
    else:
        y_pos = 255 - y_pixel
    stage_over = any(_byte(ram, address) in _STAGE_OVER_ENEMIES for address in _ENEMY_TYPE_ADDRESSES) and _byte(ram, 0x001D) == 3
    world_over = _byte(ram, 0x0770) == 2
    status = _byte(ram, 0x0756)
    return {
        "x_pos": _byte(ram, 0x006D) * 0x100 + _byte(ram, 0x0086),
        "y_pos": y_pos,
        "time": _digits(ram, 0x07F8, 3),
        "coins": _digits(ram, 0x07ED, 2),
        "points": _digits(ram, 0x07DE, 6),
        "life": _byte(ram, 0x075A),
        "world": _byte(ram, 0x075F) + 1,
        "stage": _byte(ram, 0x075C) + 1,
        "player_state": state,
        "status": _STATUS.get(status, "fireball"),
        "dying": state == 0x0B or viewport > 1,
        "dead": state == 0x06,
        "game_over": _byte(ram, 0x075A) == 0xFF,
        "flag_get": world_over or stage_over,
    }


def ram_vector(ram: bytes) -> list[float]:
    facts = describe(ram)
    return [
        facts["x_pos"] / 3168.0,
        facts["y_pos"] / 255.0,
        facts["time"] / 400.0,
        facts["player_state"] / 16.0,
        1.0 if facts["dying"] or facts["dead"] else 0.0,
        1.0 if facts["flag_get"] else 0.0,
        facts["coins"] / 99.0,
    ]


def skip_title(runner, limit: int = 600) -> None:
    """Press START until Mario is in the level and the timer has started to count down.

    0x07A0 is the pre-level timer. Writing 0 skips the walk-in. START is not held
    once the clock is running: that would pause the game.
    """

    def facts():
        return describe(runner.ram_bytes())

    def tap_start():
        runner.frame({"START"})
        runner.frame(set())

    tap_start()
    for _ in range(limit):
        if facts()["time"] > 0 and facts()["player_state"] == 0x08:
            break
        runner.poke(0x07A0, 0)
        tap_start()
    else:
        raise RuntimeError("Super Mario Bros. did not leave the title screen")

    last = facts()["time"]
    for _ in range(limit):
        runner.frame(set())
        now = facts()["time"]
        if 0 < now < last:
            return
        last = now
    raise RuntimeError("Super Mario Bros. timer never started")


class _SMB:
    id = "smb_1_1"
    objective = "x_pos"
    actions = SMB_ACTIONS
    skip_title = staticmethod(skip_title)

    def matches(self, system: str, stem: str) -> bool:
        return system == "nes" and stem.casefold() == "super mario bros. (japan, usa)"

    def describe(self, ram: bytes) -> dict:
        return describe(ram)

    def ram_vector(self, ram: bytes) -> list[float]:
        return ram_vector(ram)


INTEGRATION = _SMB()
