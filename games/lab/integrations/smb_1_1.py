"""Super Mario Bros., read from NES RAM.

Addresses follow the World ROM map used by gym-super-mario-bros (MIT): page and
x at 0x6D/0x86, the three time digits at 0x07F8, player state at 0x000E, the
flagpole enemy id 0x31 with float-state 3. Power-on is World 1-1, so the
integration only has to get past the title. The life keeps going into later levels.
"""
from __future__ import annotations

import json
from pathlib import Path

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


def progress_components(
    previous: int,
    facts: dict,
    seen_time: bool,
    cleared: bool = False,
    place=None,
) -> dict:
    """The progress objective, split into parts. The total is step_reward."""
    reward, high, dead = step_reward(previous, facts, seen_time, cleared, place)
    gained = high - int(previous)
    try:
        time_left = max(int(facts.get("time") or 0), 0)
    except (TypeError, ValueError):
        time_left = 0
    progress_reward = float(gained) * (1.0 + time_left / float(FULL_CLOCK))
    stall = 0.0
    if gained == 0 and not dead and not cleared and not facts.get("flag_get"):
        stall = float(STALL_PENALTY)
    death = float(DEATH_PENALTY) if dead else 0.0
    return {
        "total": float(reward),
        "high": high,
        "dead": dead,
        "gained": gained,
        "stop": False,
        "paid": False,
        "progress": progress_reward,
        "completion": 0.0,
        "stall": stall,
        "death": death,
        "time": 0.0,
    }


# World 1-1 speed. These magnitudes are the calibrated profile, not the progress
# objective. One decision's distance term is capped. Completion is paid once.
SPEED_ID = "smb-1-1-speed"
SPEED_PIXEL_UNIT = 256.0
SPEED_STEP_CAP = 1.0
SPEED_COMPLETION = 5.0
SPEED_DEATH = 1.0
SPEED_STALL = 0.05
SPEED_TIME_PER_FRAME = 0.001
SPEED_STALL_LIMIT = 24
_ACCEPTED_OBJECTIVES = ("progress", SPEED_ID)


def _stage_pair(place):
    if isinstance(place, (tuple, list)) and len(place) == 2:
        try:
            return int(place[0]), int(place[1])
        except (TypeError, ValueError):
            return None
    return None


def speed_components(
    previous: int,
    facts: dict,
    seen_time: bool,
    cleared: bool = False,
    place=None,
    frame_skip: int = 4,
    paid: bool = False,
) -> dict:
    """Bounded return for finishing World 1-1 quickly.

    Distance is pixels over one screen, and one decision cannot pay more than
    the step cap. A per-frame time cost prefers a faster clear. Standing still
    pays its own demerit. Dying pays one screen's worth, not the progress
    objective's death number. The completion bonus is paid once, on the World
    1-1 flag, and that step ends the episode.
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
    clock = 1.0 + time_left / float(FULL_CLOCK)
    progress_reward = min(SPEED_STEP_CAP, (gained / SPEED_PIXEL_UNIT) * clock)
    completed_now = (not paid) and bool(cleared) and _stage_pair(place) == (1, 1) and not dead
    stall = SPEED_STALL if gained == 0 and not dead and not completed_now else 0.0
    death = SPEED_DEATH if dead else 0.0
    bonus = SPEED_COMPLETION if completed_now else 0.0
    try:
        skip = max(int(frame_skip), 0)
    except (TypeError, ValueError):
        skip = 0
    time_cost = skip * SPEED_TIME_PER_FRAME
    return {
        "total": progress_reward + bonus - stall - death - time_cost,
        "high": high,
        "dead": dead,
        "gained": gained,
        "stop": completed_now,
        "paid": bool(paid or completed_now),
        "progress": progress_reward,
        "completion": bonus,
        "stall": stall,
        "death": death,
        "time": time_cost,
    }


def reward_bundle(
    objective,
    previous: int,
    facts: dict,
    seen_time: bool,
    cleared: bool = False,
    place=None,
    frame_skip: int = 4,
    paid: bool = False,
    scenario=None,
) -> dict | None:
    """Parts for the selected objective. An unknown name leaves the caller on its own."""
    del scenario
    name = objective or "progress"
    if name in ("progress", "x_pos"):
        return progress_components(previous, facts, seen_time, cleared, place)
    if name == SPEED_ID:
        return speed_components(
            previous, facts, seen_time, cleared, place, frame_skip=frame_skip, paid=paid
        )
    return None


def scenario_stall_limit(objective, scenario=None):
    """Decisions without a new maximum before the episode stops.

    The progress objective has no cutoff. The speed objective stops after 24
    decisions. A scenario file can name its own cutoff. The World 1-2 rising
    platform waits on purpose, so its file carries a longer cutoff.
    """
    if objective != SPEED_ID:
        return None
    if scenario:
        path = Path(__file__).resolve().parents[1] / "challenges" / str(scenario) / "challenge.json"
        if path.is_file():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                data = None
            if isinstance(data, dict) and data.get("stall_limit") is not None:
                return int(data["stall_limit"])
    return SPEED_STALL_LIMIT


def objective_profile(name: str | None = None) -> dict:
    """Declared objective. Names other than progress and the speed run are not implemented."""
    if name in (None, "progress"):
        return {
            "id": "progress",
            "version": 1,
            "implemented": True,
            "training_sense": "maximize",
            "stall_limit": None,
        }
    if name == SPEED_ID:
        return {
            "id": SPEED_ID,
            "version": 1,
            "implemented": True,
            "training_sense": "maximize",
            "eval_sense": "minimize",
            "eval_metric": "frames",
            "require_success": True,
            "stall_limit": SPEED_STALL_LIMIT,
            "pixel_unit": SPEED_PIXEL_UNIT,
            "step_cap": SPEED_STEP_CAP,
            "completion": SPEED_COMPLETION,
            "death": SPEED_DEATH,
            "stall": SPEED_STALL,
            "time_per_frame": SPEED_TIME_PER_FRAME,
            "frame_skip": PROTOCOL_FRAME_SKIP,
        }
    raise ValueError(f"unknown objective {name}")


def _signed(value: int) -> int:
    return value - 256 if value >= 128 else value


# Player_State in smbdis. 0 is on the ground. The jump routine sets 1.
# 2 is the usual falling value. 3 is climbing. This is not the policy observation.
_PHYSICS = {0: "ground", 1: "jumping", 2: "falling", 3: "climbing"}


def diagnose(ram: bytes) -> dict:
    """Physics the solver can read. The policy vector does not include these.

    Addresses are the doppelganger smbdis names. On this PC's FCEUmm, a jump set
    Player_State $1D to 1 and Player_Y_Speed $9F to -4. Falling used state 2 and
    a positive Y speed. The ground used state 0 and Y speed 0. Running made
    Player_X_Speed $57 positive. A goomba showed up as enemy flag 1, id 6.
    screen_x is the sprite's position on the screen, not a world x.
    """
    physics = _byte(ram, 0x001D)
    enemies = []
    for index in range(5):
        flag = _byte(ram, 0x000F + index)
        if flag == 0:
            continue
        enemies.append({
            "slot": index,
            "flag": flag,
            "id": _byte(ram, 0x0016 + index),
            "page": _byte(ram, 0x006E + index),
            "screen_x": _byte(ram, 0x0087 + index),
        })
    return {
        "physics": _PHYSICS.get(physics, "other"),
        "physics_code": physics,
        "x_speed": _signed(_byte(ram, 0x0057)),
        "y_speed": _signed(_byte(ram, 0x009F)),
        "x_fraction": _byte(ram, 0x0400),
        "y_fraction": _byte(ram, 0x0433),
        "x_move_force": _byte(ram, 0x0705),
        "power": _byte(ram, 0x0756),
        "area": _byte(ram, 0x0760),
        "enemies": enemies,
    }


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


# The unassisted experiment for this adapter. The lab engine does not define these.
PROTOCOL_NAME = "smb-unassisted-v1"
PROTOCOL_ATTEMPTS = 5
PROTOCOL_LIMIT = 2000
PROTOCOL_FRAME_SKIP = 4
PROTOCOL_SEED = 0
DEFAULT_BENCHMARK = "enter-world-4"

# A later milestone is never implied by an earlier one.
BENCHMARKS = {
    "clear-1-1-flag": (
        "Mario touches the World 1-1 flagpole while that stage is showing. "
        "This does not mean he entered a later world."
    ),
    "reach-world-1-2": (
        "The emulator is in World 1-2 or any later level, and Mario is alive. "
        "The World 1-1 castle walk does not count."
    ),
    "enter-world-4": (
        "The emulator shows World 4 and Mario is alive. "
        "A flagpole does not count, including the World 1-1 flagpole."
    ),
}


def update_milestones(reached: dict, info: dict) -> dict:
    """Latch this adapter's milestones. The flagpole does not latch a later world."""
    reached = {name: bool((reached or {}).get(name)) for name in BENCHMARKS}
    try:
        world = int(info.get("world") or 1)
        stage = int(info.get("stage") or 1)
    except (TypeError, ValueError):
        return reached
    alive = not info.get("dead") and not info.get("dying")
    if info.get("flag_get") and world == 1 and stage == 1 and alive:
        reached["clear-1-1-flag"] = True
    if alive and (world > 1 or (world == 1 and stage >= 2)):
        reached["reach-world-1-2"] = True
    if alive and world >= 4:
        reached["enter-world-4"] = True
    return reached


def position_supports(episode: dict, benchmark: str) -> bool:
    """The recorded ending still agrees with a milestone the episode claims."""
    try:
        world = int(episode.get("world") or 0)
        stage = int(episode.get("stage") or 0)
    except (TypeError, ValueError):
        return False
    if benchmark == "enter-world-4":
        return world > 4 or (world == 4 and stage >= 1)
    if benchmark == "reach-world-1-2":
        return world > 1 or (world == 1 and stage >= 2)
    if benchmark == "clear-1-1-flag":
        return True
    return False


def episode_metrics(info: dict) -> dict:
    """Facts this adapter records for one life. The engine stores them as given."""
    def num(key: str, default: int = 0) -> int:
        try:
            return int(info.get(key) if info.get(key) is not None else default)
        except (TypeError, ValueError):
            return default

    return {
        "score": num("score"),
        "world": num("world", 1),
        "stage": num("stage", 1),
        "x_pos": num("x_pos"),
        "time": num("time"),
        "dead": bool(info.get("dead")),
    }


def reached_warp(start: dict, now: dict) -> bool:
    """World 1-2 became world 4 inside the emulator. A score is not this check."""
    return (
        start.get("world") == 1
        and start.get("stage") == 2
        and now.get("world") == 4
        and now.get("stage") == 1
        and not now.get("dead")
        and not now.get("dying")
    )


def correct_progress(tape: dict, score: int) -> int:
    """A castle walk once stored World 1-1's x as the start of World 1-2.

    The buttons of that file stop on the 1-1 ending. A tape marked scored_clear
    already measured the stage after the position reset.
    """
    if tape.get("scored_clear"):
        return score
    if tape.get("objective") not in (None, "progress"):
        return score
    try:
        world = int(tape.get("world") or 1)
        stage = int(tape.get("stage") or 1)
    except (TypeError, ValueError):
        return score
    index = (world - 1) * 4 + (stage - 1)
    if index > 0 and score == index * STAGE_SPAN + CLEAR_X:
        return score - STAGE_SPAN
    return score


def correct_floor(floor: int):
    """The historical parent 7362 is the 1-1 castle counted as 1-2."""
    try:
        floor = int(floor)
    except (TypeError, ValueError):
        return None
    if floor == STAGE_SPAN + CLEAR_X:
        return CLEAR_X
    return None


def accept_hint_context(context: dict) -> dict:
    """A hint plays in one world and stage. Worlds are 1 to 8 and stages 1 to 4."""
    try:
        world = int(context.get("world"))
        stage = int(context.get("stage"))
    except (TypeError, ValueError):
        raise ValueError("world and stage are numbers") from None
    if not 1 <= world <= 8 or not 1 <= stage <= 4:
        raise ValueError("world is 1 to 8 and stage is 1 to 4")
    return {"world": world, "stage": stage}


def note_frame(facts: dict, diag: dict, memory: dict | None) -> dict:
    """Remember whether this life left the ground. Search uses that as a signal."""
    memory = dict(memory or {})
    if "start_y" not in memory:
        memory["start_y"] = int(facts.get("y_pos") or 0)
    saw = bool(memory.get("saw_jump"))
    try:
        speed = int((diag or {}).get("y_speed") or 0)
        height = int(facts.get("y_pos") or 0)
    except (TypeError, ValueError):
        speed, height = 0, 0
    if speed < 0 or height > int(memory["start_y"]) + 2:
        saw = True
    memory["saw_jump"] = saw
    facts["saw_jump"] = saw
    facts["diagnose"] = diag
    return memory


def clock_running(facts: dict) -> bool:
    """True once this stage's timer has started."""
    try:
        return int((facts or {}).get("time") or 0) > 0
    except (TypeError, ValueError):
        return False


def present(facts: dict, clear: dict | None = None) -> dict:
    """Facts the seat should see. A latched clear keeps the finished stage."""
    info = dict(facts or {})
    latch = clear or {}
    if latch.get("cleared") and latch.get("at"):
        info["world"], info["stage"] = latch["at"]
    return info


def evaluation_protocol() -> dict:
    """What an independent Mario measurement is. Callers pass this to the engine."""
    return {
        "name": PROTOCOL_NAME,
        "attempts": PROTOCOL_ATTEMPTS,
        "limit": PROTOCOL_LIMIT,
        "frame_skip": PROTOCOL_FRAME_SKIP,
        "n_actions": len(SMB_ACTIONS),
        "seed": PROTOCOL_SEED,
        "default_benchmark": DEFAULT_BENCHMARK,
        "clear_benchmark": "clear-1-1-flag",
        "game": "smb_1_1",
        "objective": "progress",
        "sense": "maximize",
        "metric": "score",
        "start": "game",
        "benchmarks": dict(BENCHMARKS),
        "observe": update_milestones,
        "supports": position_supports,
        "metrics": episode_metrics,
    }


def speed_protocol() -> dict:
    """Independent ranking for the speed objective.

    Sense is minimize and the metric is emulator frames. require_success means
    a failure is not a champion, even when it used very few frames. Training
    still maximizes position. This protocol does not replace evaluation_protocol.
    """
    return {
        "name": "smb-1-1-speed-v1",
        "attempts": PROTOCOL_ATTEMPTS,
        "limit": PROTOCOL_LIMIT,
        "frame_skip": PROTOCOL_FRAME_SKIP,
        "n_actions": len(SMB_ACTIONS),
        "seed": PROTOCOL_SEED,
        "default_benchmark": "clear-1-1-flag",
        "clear_benchmark": "clear-1-1-flag",
        "game": "smb_1_1",
        "objective": SPEED_ID,
        "sense": "minimize",
        "metric": "frames",
        "require_success": True,
        "start": "game",
        "benchmarks": dict(BENCHMARKS),
        "observe": update_milestones,
        "supports": position_supports,
        "metrics": episode_metrics,
    }


class _SMB:
    id = "smb_1_1"
    system = "nes"
    objective = "progress"
    sense = "maximize"
    actions = SMB_ACTIONS
    death_penalty = DEATH_PENALTY
    capabilities = {
        "contract": 1,
        "pixels": True,
        "ram": True,
        "savestate": True,
        "frame_accurate": True,
        "structured": True,
    }
    skip_title = staticmethod(skip_title)
    measure = staticmethod(progress)
    step_reward = staticmethod(step_reward)
    note_clear = staticmethod(note_clear)
    clock_running = staticmethod(clock_running)
    present = staticmethod(present)
    evaluation_protocol = staticmethod(evaluation_protocol)
    speed_protocol = staticmethod(speed_protocol)
    objective_profile = staticmethod(objective_profile)
    reward_bundle = staticmethod(reward_bundle)
    reached_warp = staticmethod(reached_warp)
    correct_progress = staticmethod(correct_progress)
    correct_floor = staticmethod(correct_floor)
    accept_hint_context = staticmethod(accept_hint_context)
    note_frame = staticmethod(note_frame)

    def open_env(self, rom=None, objective=None, scenario=None):
        """The scored environment for this ROM. The engine asks every adapter for this.

        objective selects the reward. The default stays the progress objective.
        """
        from games.lab.env import make_env
        if rom:
            path = Path(rom)
        else:
            path = self.pinned_rom()
        return make_env(self.system, path, self, objective=objective, scenario=scenario)

    def stall_limit(self, objective=None, scenario=None):
        name = self.objective if objective is None else objective
        return scenario_stall_limit(name, scenario)

    def pinned_rom(self):
        from games.lab.mario.rom import pinned_smb
        return pinned_smb()

    def rom_sha1(self) -> str:
        from games.lab.mario.rom import SMB_SHA1
        return SMB_SHA1

    def materialize(self, game=None):
        from games.lab.mario.rom import store_smb
        return store_smb()

    def owns(self, record: dict) -> bool:
        """Historical files often omit the adapter id. New files should set it."""
        if not isinstance(record, dict):
            return False
        if record.get("integration") == self.id:
            return True
        if record.get("integration"):
            return False
        game = str(record.get("game") or "")
        if game in {self.id, "Super Mario Bros."}:
            return True
        objective = record.get("objective")
        if record.get("system") == "nes" and objective == "progress":
            return True
        if objective in (None, "progress", "x_pos") and ("world" in record or "stage" in record):
            return True
        return False

    def matches(self, system: str, stem: str) -> bool:
        return system == "nes" and stem.casefold() == "super mario bros. (japan, usa)"

    def describe(self, ram: bytes) -> dict:
        return describe(ram)

    def ram_vector(self, ram: bytes) -> list[float]:
        return ram_vector(ram)

    def diagnose(self, ram: bytes) -> dict:
        return diagnose(ram)

    def stamp(self, objective=None) -> dict:
        name = self.objective if objective is None else str(objective)
        if name not in _ACCEPTED_OBJECTIVES:
            raise ValueError(f"unknown objective {name}")
        return {
            "actions": [list(chord) for chord in self.actions],
            "objective": name,
            "ram": len(self.ram_vector(bytes(2048))),
        }


INTEGRATION = _SMB()
