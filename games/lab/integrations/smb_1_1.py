"""Super Mario Bros., read from NES RAM.

Addresses follow the World ROM map used by gym-super-mario-bros (MIT): page and
x at 0x6D/0x86, the three time digits at 0x07F8, player state at 0x000E, the
flagpole enemy id 0x31 with float-state 3. Power-on is World 1-1, so the
integration only has to get past the title. The life keeps going into later levels.
"""
from __future__ import annotations

# Down enters a pipe. Up climbs a vine. Left chords set up a jump.
# The older seven-button list could not do either, and its weights do not load.
SMB_ACTIONS: list[tuple[str, ...]] = [
    (),
    ("RIGHT",),
    ("RIGHT", "A"),
    ("RIGHT", "B"),
    ("RIGHT", "A", "B"),
    ("A",),
    ("LEFT",),
    ("LEFT", "A"),
    ("LEFT", "B"),
    ("LEFT", "A", "B"),
    ("DOWN",),
    ("UP",),
]

# One stage index is worth more than any x position inside the previous stage.
STAGE_SPAN = 4096
# x on the 1-1 castle walk. The level number becomes the next stage first.
CLEAR_X = 3266
# Large enough that walking into an enemy is a loss, not a small step right.
DEATH_PENALTY = 256
# One agent step that gains no ground. A few seconds of standing costs less than a death.
STALL_PENALTY = 1.0
# World 1 starts the clock at 400. A gain at 400 is worth double. At 200 it is worth 1.5x.
FULL_CLOCK = 400

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


def progress(facts: dict, place=None) -> int:
    """Monotonic position in the game. World 1-2 starts above the 1-1 flag.

    place is the stage being cleared. The level number in RAM moves on while
    Mario is still walking into that stage's castle.
    """
    if place is None:
        world = max(int(facts.get("world") or 1), 1)
        stage = max(int(facts.get("stage") or 1), 1)
    else:
        world = max(int(place[0]), 1)
        stage = max(int(place[1]), 1)
    x_pos = min(max(int(facts.get("x_pos") or 0), 0), STAGE_SPAN - 1)
    stage_index = (world - 1) * 4 + (stage - 1)
    return stage_index * STAGE_SPAN + x_pos


def note_clear(state: dict | None, facts: dict) -> dict:
    """Remember a flag touch until the next stage has actually started.

    The flag object disappears while the timer is still counting down, and the
    walk into the castle can look like a fall. The level number increments
    before Mario's position resets. That stretch is still the stage he cleared.
    """
    state = state or {}
    cleared = bool(state.get("cleared"))
    where = state.get("at")
    here = (int(facts.get("world") or 1), int(facts.get("stage") or 1))
    x = int(facts.get("x_pos") or 0)
    if facts.get("flag_get") and not cleared:
        return {"cleared": True, "at": here, "x": x}
    if not cleared:
        return {"cleared": False, "at": None}
    seen = max(int(state.get("x") or 0), x)
    stage_changed = where is not None and tuple(where) != here
    if int(facts.get("time") or 0) > 0 and stage_changed and x < seen:
        return {"cleared": False, "at": None}
    return {"cleared": True, "at": where, "x": seen}


def is_dead(facts: dict, seen_time: bool, cleared: bool = False) -> bool:
    """The clear sequence counts the timer down on purpose. That is not a death."""
    if cleared:
        # Only the death sprite ends the life. The timer and a low y are the animation.
        return bool(facts.get("dead") or facts.get("game_over") or facts.get("player_state") == 0x0B)
    timed_out = bool(seen_time and facts.get("time") == 0 and not facts.get("flag_get"))
    return bool(facts.get("dead") or facts.get("dying") or facts.get("game_over") or timed_out)


def step_reward(
    previous: int,
    facts: dict,
    seen_time: bool,
    cleared: bool = False,
    place=None,
) -> tuple[float, int, bool]:
    """New progress, worth more while the clock is high.

    The number stored as the score is still the position. Time only shapes the
    reward. A step that gains nothing while Mario is alive pays a small demerit,
    so standing in front of an obstacle is a loss. The clear, the flag, and the
    death step do not add that demerit. Dying pays its own penalty.
    """
    dead = is_dead(facts, seen_time, cleared)
    if cleared and place is not None:
        here = progress(facts, place)
    else:
        here = progress(facts)
    high = max(int(previous), here)
    gained = high - int(previous)
    try:
        time_left = max(int(facts.get("time") or 0), 0)
    except (TypeError, ValueError):
        time_left = 0
    reward = float(gained) * (1.0 + time_left / float(FULL_CLOCK))
    if gained == 0 and not dead and not cleared and not facts.get("flag_get"):
        reward -= STALL_PENALTY
    if dead:
        reward -= DEATH_PENALTY
    return reward, high, dead


def ram_vector(ram: bytes) -> list[float]:
    facts = describe(ram)
    return [
        facts["x_pos"] / float(STAGE_SPAN),
        facts["y_pos"] / 255.0,
        facts["time"] / 400.0,
        facts["player_state"] / 16.0,
        1.0 if facts["dying"] or facts["dead"] else 0.0,
        1.0 if facts["flag_get"] else 0.0,
        facts["coins"] / 99.0,
        facts["world"] / 8.0,
        facts["stage"] / 4.0,
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
    objective = "progress"
    actions = SMB_ACTIONS
    death_penalty = DEATH_PENALTY
    skip_title = staticmethod(skip_title)
    measure = staticmethod(progress)
    step_reward = staticmethod(step_reward)
    note_clear = staticmethod(note_clear)

    def matches(self, system: str, stem: str) -> bool:
        return system == "nes" and stem.casefold() == "super mario bros. (japan, usa)"

    def describe(self, ram: bytes) -> dict:
        return describe(ram)

    def ram_vector(self, ram: bytes) -> list[float]:
        return ram_vector(ram)

    def stamp(self) -> dict:
        return {
            "actions": [list(chord) for chord in self.actions],
            "objective": self.objective,
            "ram": len(self.ram_vector(bytes(2048))),
        }


INTEGRATION = _SMB()
