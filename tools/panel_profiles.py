"""Emulator configuration for the physical panel, generated from pi/controls/panel.json (the capture of 17 October 2026).

Pure functions: they return text and touch nothing. tools/install_controls.py puts the results on the Pi, with backups.

One layout for every emulator (panel.json "layout"): each player's stick; BUTTON_1 to BUTTON_6 are A, B, X, Y,
Snowflake and Star in that order; Coin and Start; Player 2's flight-stick trigger and secondary also act as its BUTTON_1
and BUTTON_2. In MAME's menu: Tab opens it, the stick moves, Enter (on the P2 encoder) selects, Esc (P1) backs out,
Pause (P2) pauses. EmulationStation is driven by Player 1's side (the two encoders share one name, so one map serves
both: Player 2's buttons act as Player 1's in the menu until the wiring is changed to match).

Button numbers: an SDL, RetroArch and MAME button is the evdev code minus the first button code (288), counted from 0
(MAME names them from 1). AdvanceMAME names the same buttons trigger, thumb, thumb2, top, top2, pinkie, base, base2 ... base6.
"""
import json
import re
from pathlib import Path
from xml.sax.saxutils import quoteattr

PANEL_JSON = Path(__file__).resolve().parent.parent / "pi" / "controls" / "panel.json"
GAMES_DIR = Path(__file__).resolve().parent.parent / "games"


def load_game_controls(root=GAMES_DIR):
    """{"<system>/<ROM name>": that game's controls.json} for every games/<system>/<game>/controls.json. A game's own folder says
    where its controls differ from the cabinet's defaults (the "roms" it covers, an "emulator", MAME "panel" port
    changes, a "dip" setting, "retroarch_pad" button changes); a game with no file, or no entry, gets the defaults. The
    framework knows no game by name."""
    out = {}
    for path in sorted(Path(root).glob("*/*/controls.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        data["_system"] = path.parent.parent.name
        for rom in data.get("roms") or [path.parent.name]:
            out[f"{data['_system']}/{rom}"] = data  # the system is part of the key: two systems may share a ROM name
    return out


def load_panel(path=PANEL_JSON):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def index(panel, player, control):
    """The 0-based button number of a player's control."""
    return panel["players"][player]["buttons"][control] - panel["device"]["first_button_code"]


def actions(panel, player):
    """BUTTON_1..6 -> the button number(s) that press it (a list: the flight buttons double P2's first two)."""
    out = {}
    for n, control in enumerate(panel["layout"]["action_order"], 1):
        out[n] = [index(panel, player, control)]
    if player == "P2":
        buttons = panel["players"]["P2"]["buttons"]
        for n, control in ((1, "FLIGHT1"), (2, "FLIGHT2")):
            if control in buttons:
                out[n].append(index(panel, player, control))
    return out


# ---------------------------------------------------------------- EmulationStation

def es_input_entry(panel):
    """The <inputConfig> for the panel's encoders. Player 1's map: both encoders share the name and GUID."""
    d, p1 = panel["device"], panel["players"]["P1"]
    ax = {name: p1["stick"][name] for name in ("up", "down", "left", "right")}
    rows = [(name, "axis", ax[name][1], ax[name][2]) for name in ("up", "down", "left", "right")]
    ui = {"a": "A", "b": "B", "x": "X", "y": "Y", "pageup": "STAR", "pagedown": "SNOWFLAKE", "select": "TAB",
          "start": "START"}
    rows += [(name, "button", index(panel, "P1", control), 1) for name, control in ui.items()]
    lines = [f'  <inputConfig type="joystick" deviceName={quoteattr(d["sdl_name"])} deviceGUID={quoteattr(d["sdl_guid"])}>']
    lines += [f'    <input name="{n}" type="{t}" id="{i}" value="{v}"/>' for n, t, i, v in rows]
    lines.append("  </inputConfig>")
    return "\n".join(lines) + "\n"


def sdl_guid(bus, vendor, product, version, name):
    """SDL's joystick GUID for a USB device, from /proc/bus/input/devices: bus, a CRC-16 of the kernel's device name
    (poly 0xA001), then vendor, product and version, each little-endian with 0000 after. Matches the panel's GUID in
    es_input.cfg and what EmulationStation logs for a Logitech F310 (030005ff6d0400001dc2000014400000)."""
    crc = 0
    for byte in name.encode():
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    le = lambda h: int(h, 16).to_bytes(2, "little").hex()  # noqa: E731
    return f"{le(bus)}{crc.to_bytes(2, 'little').hex()}{le(vendor)}0000{le(product)}0000{le(version)}0000"


def es_gamepad_entry(name, guid):
    """The <inputConfig> for an ordinary gamepad in SDL's standard layout (a Logitech F310 in XInput mode, an Xbox pad):
    the D-pad moves, A and B accept and go back, X and Y as they are, LB and RB page, Back is select, Start is start."""
    rows = [("up", "hat", 0, 1), ("right", "hat", 0, 2), ("down", "hat", 0, 4), ("left", "hat", 0, 8),
            ("a", "button", 0, 1), ("b", "button", 1, 1), ("x", "button", 2, 1), ("y", "button", 3, 1),
            ("pageup", "button", 4, 1), ("pagedown", "button", 5, 1), ("select", "button", 6, 1), ("start", "button", 7, 1)]
    lines = [f'  <inputConfig type="joystick" deviceName={quoteattr(name)} deviceGUID={quoteattr(guid)}>']
    lines += [f'    <input name="{n}" type="{t}" id="{i}" value="{v}"/>' for n, t, i, v in rows]
    lines.append("  </inputConfig>")
    return "\n".join(lines) + "\n"


def merge_es_input(existing, entry, device_name):
    """es_input.cfg with this device's <inputConfig> replaced (or added). Other devices are left byte for byte."""
    pattern = re.compile(r'[ \t]*<inputConfig [^>]*deviceName=("|\')' + re.escape(device_name) + r'\1[^>]*>.*?</inputConfig>\n?', re.S)
    if pattern.search(existing):
        return pattern.sub(lambda m: entry, existing, count=1)
    return existing.replace("</inputList>", entry + "</inputList>", 1)


# ---------------------------------------------------------------- RetroArch

def retroarch_autoconfig(panel, player="P1", system=None):
    """The joypad autoconfig. The panel's six action buttons press the RetroPad buttons panel.json "retroarch" lists for the
    system (SNES order by default; B, Y, X, A, L, R for the arcade cores); Select is Coin and Start is Start. Esc is the hotkey and the exit (alone, as on the keyboard), Tab with Esc held opens the menu."""
    d = panel["device"]
    orders = panel.get("retroarch", {}).get("button_order", {})
    names = dict(enumerate(orders.get(system) or orders.get("default") or ["b", "a", "y", "x", "l", "r"], 1))
    first = actions(panel, player)
    lines = [f'input_device = "{d["evdev_name"]}"', 'input_driver = "udev"',
             f'input_vendor_id = "{int(d["vendor_id"], 16)}"', f'input_product_id = "{int(d["product_id"], 16)}"', ""]
    stick = panel["players"][player]["stick"]
    for direction in ("left", "right", "up", "down"):
        _, axis, sign = stick[direction]
        lines.append(f'input_{direction}_axis = "{"+" if sign > 0 else "-"}{axis}"')
    lines.append("")
    for n, retro in names.items():
        lines.append(f'input_{retro}_btn = "{first[n][0]}"')
    lines += ["", f'input_select_btn = "{index(panel, player, "COIN")}"', f'input_start_btn = "{index(panel, player, "START")}"', ""]
    if player == "P1":  # Esc and Tab are on Player 1's encoder
        lines += [f'input_enable_hotkey_btn = "{index(panel, "P1", "ESC")}"',
                  f'input_exit_emulator_btn = "{index(panel, "P1", "ESC")}"',
                  f'input_menu_toggle_btn = "{index(panel, "P1", "TAB")}"', ""]
    return "\n".join(lines)


HOTKEY_BINDS = ("input_enable_hotkey_btn", "input_exit_emulator_btn", "input_menu_toggle_btn")


def retroarch_player_binds(autoconfig, player_number):
    """An autoconfig file's button, axis and D-pad lines as one player's explicit binds (input_player2_b_btn = ...),
    for the RetroArch options file appended at launch. RetroArch gives explicit binds priority over its autoconfig,
    and autoconfig alone ties a pad's buttons to the port it was found in, not the player it is meant to be.
    Returns (that player's lines, the hotkey lines, which belong to the device that plays Player 1)."""
    lines, hotkeys = [], []
    for line in autoconfig.splitlines():
        key, _, value = line.partition(" = ")
        if key in HOTKEY_BINDS:
            hotkeys.append(line)
        elif key.startswith("input_") and key.endswith(("_btn", "_axis")):
            lines.append(f"input_player{player_number}_{key[len('input_'):]} = {value}")
    return lines, hotkeys


def retroarch_gamepad_autoconfig(name, vendor, product):
    """RetroArch's joypad autoconfig for an ordinary gamepad in the standard layout (as RetroArch's own Logitech F310
    XInput file): RetroPad B, A, Y, X are the pad's A, B, X, Y; Back is Select (the arcade coin), Start is Start. The D-pad
    and the left stick both move (each direction has a button bind, the D-pad, and an axis bind, the stick). The Guide button is the hotkey (Back and Start stay coin and start): Guide+Start exits the game, Guide+Back opens RetroArch's menu."""
    return "\n".join([
        f'input_device = "{name}"', 'input_driver = "udev"',
        f'input_vendor_id = "{int(vendor, 16)}"', f'input_product_id = "{int(product, 16)}"', "",
        'input_b_btn = "0"', 'input_a_btn = "1"', 'input_y_btn = "2"', 'input_x_btn = "3"',
        'input_l_btn = "4"', 'input_r_btn = "5"', 'input_select_btn = "6"', 'input_start_btn = "7"',
        'input_up_btn = "h0up"', 'input_down_btn = "h0down"', 'input_left_btn = "h0left"', 'input_right_btn = "h0right"',
        'input_left_axis = "-0"', 'input_right_axis = "+0"', 'input_up_axis = "-1"', 'input_down_axis = "+1"',
        'input_l_x_plus_axis = "+0"', 'input_l_x_minus_axis = "-0"', 'input_l_y_plus_axis = "+1"', 'input_l_y_minus_axis = "-1"',
        'input_enable_hotkey_btn = "8"', 'input_exit_emulator_btn = "7"', 'input_menu_toggle_btn = "6"', ""])


# ---------------------------------------------------------------- MAME 0.251

def _direction_code(joy, direction_sign):
    axis, sign = direction_sign
    name = "XAXIS" if axis == 0 else "YAXIS"
    if axis == 0:
        side = "LEFT" if sign < 0 else "RIGHT"
    else:
        side = "UP" if sign < 0 else "DOWN"
    return f"JOYCODE_{joy}_{name}_{side}_SWITCH"


def pad_terms(pad):
    """What an ordinary gamepad (a Logitech F310 in XInput mode, or anything that reports as SDL's standard layout)
    adds to a player's controls, as {MAME port suffix: sequence}. `pad` is MAME's joystick number for it. The stick
    or the D-pad moves; A, B, X, Y, LB, RB are buttons 1 to 6; Back is coin and Start is start."""
    out = {}
    for direction, axis in (("UP", "YAXIS_UP"), ("DOWN", "YAXIS_DOWN"), ("LEFT", "XAXIS_LEFT"), ("RIGHT", "XAXIS_RIGHT")):
        out[direction] = f"JOYCODE_{pad}_{axis}_SWITCH OR JOYCODE_{pad}_HAT1{direction}"
    for n in range(1, 7):
        out[f"BUTTON{n}"] = f"JOYCODE_{pad}_BUTTON{n}"
    out["COIN"] = f"JOYCODE_{pad}_BUTTON7"
    out["START"] = f"JOYCODE_{pad}_BUTTON8"
    return out


def _drop_absent(seq, absent):
    """A sequence without the terms that name a joystick number that is not plugged in."""
    terms = [t for t in seq.split(" OR ") if not any(t.startswith(f"JOYCODE_{n}_") for n in absent)]
    return " OR ".join(terms)


def mame_ports(panel, joy1=1, joy2=2, pads=None):
    """[(MAME port type, input sequence)] for the default section: both players' sticks, six buttons, coin, start, and
    MAME's menu keys. joy1 and joy2 are MAME's joystick numbers for the P1 and P2 encoders (1 and 2 when the panel's
    encoders are the first two joysticks, which the order checks must confirm); None means that encoder is not plugged
    in. pads is {"P1": joystick number, "P2": ...} for gamepads that also play as that player (pad_terms).
    tools/... pi/mame_human/pad_map.py works these numbers out at every launch from what is plugged in."""
    absent = [n for n, j in (("P1", joy1), ("P2", joy2)) if j is None]
    joy1_, joy2_ = (j if j is not None else 90 + i for i, j in enumerate((joy1, joy2)))
    ports = _mame_ports(panel, joy1_, joy2_)
    gone = [90 + i for i, n in enumerate(("P1", "P2")) if n in absent]
    pads = pads or {}
    out = []
    for port, seq in ports:
        seq = _drop_absent(seq, gone)
        for player, pad in pads.items():
            t = pad_terms(pad)
            suffix = port[3:] if port.startswith(player + "_") else None
            if suffix in t:
                seq += " OR " + t[suffix]
            elif port == "COIN" + player[1] or port == "START" + player[1]:
                seq += " OR " + t[port[:-1]]
            elif player == "P1" and port in ("UI_UP", "UI_DOWN", "UI_LEFT", "UI_RIGHT"):
                seq += " OR " + t[port[3:]]
            elif player == "P1" and port == "UI_SELECT":
                seq += " OR " + t["BUTTON1"]
            elif player == "P1" and port == "UI_CANCEL":
                seq += " OR " + t["BUTTON2"]
        out.append((port, seq))
    return out


def _mame_ports(panel, joy1, joy2):
    joy = {"P1": joy1, "P2": joy2}
    ports = []
    keys = {"P1": {"up": "KEYCODE_UP", "down": "KEYCODE_DOWN", "left": "KEYCODE_LEFT", "right": "KEYCODE_RIGHT"},
            "P2": {"up": "KEYCODE_R", "down": "KEYCODE_F", "left": "KEYCODE_D", "right": "KEYCODE_G"}}
    button_keys = {"P1": ["KEYCODE_LCONTROL", "KEYCODE_LALT", "KEYCODE_SPACE", "KEYCODE_LSHIFT", "KEYCODE_Z", "KEYCODE_X"],
                   "P2": ["KEYCODE_A", "KEYCODE_S", "KEYCODE_Q", "KEYCODE_W", "KEYCODE_E", "KEYCODE_I"]}
    for player in ("P1", "P2"):
        stick = panel["players"][player]["stick"]
        for direction in ("up", "down", "left", "right"):
            ports.append((f"{player}_JOYSTICK_{direction.upper()}",
                          f"{_direction_code(joy[player], stick[direction][1:])} OR {keys[player][direction]}"))
        for n, idx in actions(panel, player).items():
            codes = " OR ".join(f"JOYCODE_{joy[player]}_BUTTON{i + 1}" for i in idx)
            ports.append((f"{player}_BUTTON{n}", f"{codes} OR {button_keys[player][n - 1]}"))
    # twin-stick games (Robotron, Black Widow, Battlezone...): the left stick is Player 1's, the right is Player 2's
    for side, player in (("LEFT", "P1"), ("RIGHT", "P2")):
        stick = panel["players"][player]["stick"]
        for direction in ("up", "down", "left", "right"):
            ports.append((f"P1_JOYSTICK{side}_{direction.upper()}",
                          f"{_direction_code(joy[player], stick[direction][1:])}"))
    c = lambda player, control, j: f"JOYCODE_{j}_BUTTON{index(panel, player, control) + 1}"  # noqa: E731
    ports += [("COIN1", f"{c('P1', 'COIN', joy1)} OR KEYCODE_5 OR KEYCODE_RSHIFT"),
              ("START1", f"{c('P1', 'START', joy1)} OR KEYCODE_1 OR KEYCODE_ENTER"),
              ("COIN2", f"{c('P2', 'COIN', joy2)} OR KEYCODE_6"),
              ("START2", f"{c('P2', 'START', joy2)} OR KEYCODE_2")]
    ui = panel["layout"]["ui"]
    ui_keys = {"menu": ("UI_CONFIGURE", "KEYCODE_TAB"), "back": ("UI_CANCEL", "KEYCODE_ESC"),
               "select": ("UI_SELECT", "KEYCODE_ENTER"), "pause": ("UI_PAUSE", "KEYCODE_P")}
    for name, (port, key) in ui_keys.items():
        player, control = ui[name]
        ports.append((port, f"{c(player, control, joy[player])} OR {key}"))
    stick1 = panel["players"]["P1"]["stick"]
    for direction in ("up", "down", "left", "right"):
        ports.append((f"UI_{direction.upper()}", f"{_direction_code(joy1, stick1[direction][1:])} OR KEYCODE_{direction.upper()}"))
    return ports


def game_ports(panel, joy1=1, joy2=2, pads=None, games=None):
    """{MAME game: [(port type, sequence)]} for the games whose controls.json has a "panel" section: a port is pressed
    by another control than the layout says. A gamepad's button for the same port stays on it."""
    joy = {"P1": joy1, "P2": joy2}
    pads = pads or {}
    out = {}
    for key, game in (games or {}).items():
        if game.get("_system") != "arcade":  # MAME's controller file is for the arcade system
            continue
        rom = key.split("/", 1)[1]
        overrides = {k: v for k, v in game.get("panel", {}).items() if k != "comment"}
        if not overrides:
            continue
        rows = []
        for port, (player, control) in overrides.items():
            if joy[player] is None:
                seq = ""
            else:
                seq = f"JOYCODE_{joy[player]}_BUTTON{index(panel, player, control) + 1}"
            for owner, pad in pads.items():
                if port.startswith(owner + "_") and port[3:] in pad_terms(pad):
                    seq = (seq + " OR " if seq else "") + pad_terms(pad)[port[3:]]
            if seq:
                rows.append((port, seq))
        out[rom] = rows
    return out


def shared_ports(panel, joy1, joy2, pads, single):
    """[(port, sequence)] that let Player 2's encoder (its stick and its buttons, the flight stick's two buttons included)
    play Player 1's ports too, for a game where the players take turns on one set of controls or only one plays: the
    P1 sequences with Player 2's added. For a single-player game Player 2's coin and start also work as Player 1's; for a
    two-player game they stay Player 2's (START2 is the "2 players" start). Empty when the second encoder is not there."""
    if joy2 is None:
        return []
    base = dict(mame_ports(panel, joy1, joy2, pads))
    stick = panel["players"]["P2"]["stick"]
    extra = {f"P1_JOYSTICK_{d.upper()}": _direction_code(joy2, stick[d][1:]) for d in ("up", "down", "left", "right")}
    for n, idx in actions(panel, "P2").items():
        extra[f"P1_BUTTON{n}"] = " OR ".join(f"JOYCODE_{joy2}_BUTTON{i + 1}" for i in idx)
    if single:
        extra["COIN1"] = f"JOYCODE_{joy2}_BUTTON{index(panel, 'P2', 'COIN') + 1}"
        extra["START1"] = f"JOYCODE_{joy2}_BUTTON{index(panel, 'P2', 'START') + 1}"
    return [(port, f"{base[port]} OR {seq}") for port, seq in extra.items()]


def game_sections(panel, joy1, joy2, pads, games):
    """{MAME machine name: [(port, sequence)]} for every game with its own section: those whose controls.json says
    "play": "single" or "turns" get Player 2's encoder on Player 1's ports (shared_ports), and any "panel" changes of the
    game win over that. The machine name is "mame" in the file (the set the cabinet runs) or else the ROM names."""
    overrides = game_ports(panel, joy1, joy2, pads, games)
    out = {}
    for key, game in (games or {}).items():
        if game.get("_system") != "arcade":
            continue
        rom = key.split("/", 1)[1]
        rows = {}
        if game.get("play") in ("single", "turns"):
            rows.update(shared_ports(panel, joy1, joy2, pads, game["play"] == "single"))
        rows.update(dict(overrides.get(rom, [])))
        if rows:
            for name in game.get("mame") or [rom]:
                out.setdefault(name, {}).update(rows)
    return {name: list(rows.items()) for name, rows in out.items()}


def mame_ctrlr(panel, joy1=1, joy2=2, pads=None, games=None):
    """The ctrlr file for human mode (/home/pi/.mame/ctrlr/panel.cfg): only the default section; MAME's own defaults
    still apply to everything not listed (players 3 and 4, analog controls, service keys)."""
    out = ['<?xml version="1.0"?>', '<mameconfig version="10">', '    <system name="default">', "        <input>"]
    for port, seq in mame_ports(panel, joy1, joy2, pads):
        out += [f'            <port type="{port}">', f'                <newseq type="standard">{seq}</newseq>', "            </port>"]
    out += ["        </input>", "    </system>"]
    for game, ports in game_sections(panel, joy1, joy2, pads, games).items():
        out += [f'    <system name="{game}">', "        <input>"]
        for port, seq in ports:
            out += [f'            <port type="{port}">', f'                <newseq type="standard">{seq}</newseq>', "            </port>"]
        out += ["        </input>", "    </system>"]
    out += ["</mameconfig>", ""]
    return "\n".join(out)


def mame_ini_with_ctrlr(ini, name):
    """mame.ini with its ctrlr line changed to `name`."""
    new, count = re.subn(r"^(ctrlr\s+)\S+", lambda m: m.group(1) + name, ini, count=1, flags=re.M)
    if not count:
        raise ValueError("mame.ini has no ctrlr line")
    return new


# MAME 0.251's default audio_latency (2) gives the Pi's USB audio adapter nothing but silence: measured on 19 October 2026
# by capturing what MAME hands ALSA during a Battlezone game (latency 2: all zeros; 3, 4 and 5: full-level sound, in every
# repeat). 4 leaves a margin over the smallest value that works.
AUDIO_LATENCY = 4


def mame_ini_set(ini, key, value, comment=None):
    """mame.ini with `key value` set: the line replaced if it is there, or added at the end (after a comment line)."""
    line = f"{key:<25} {value}"
    new, count = re.subn(rf"^{re.escape(key)}\s+\S+.*$", lambda m: line, ini, count=1, flags=re.M)
    if count:
        return new
    extra = ("\n# " + comment if comment else "") + "\n" + line + "\n"
    return ini.rstrip("\n") + "\n" + extra


def expected_mame_fields(panel):
    """What each physical control should make MAME's input fields do: {(player, control): MAME field name(s)}. The test
    that presses the panel reads the fields back."""
    out = {}
    for player in ("P1", "P2"):
        num = player[1]
        for direction in ("up", "down", "left", "right"):
            out[(player, direction.upper())] = [f"{player} {direction.capitalize()}"]
        for n, idx in actions(panel, player).items():
            for control in panel["layout"]["action_order"][n - 1:n]:
                out[(player, control)] = [f"{player} Button {n}"]
            if player == "P2" and n in (1, 2):
                out[(player, f"FLIGHT{n}")] = [f"{player} Button {n}"]
        out[(player, "COIN")] = [f"Coin {num}"]
        out[(player, "START")] = ["1 Player Start" if player == "P1" else "2 Players Start"]
    return out


# ---------------------------------------------------------------- AdvanceMAME 3
#
# AdvanceMAME's default joystick driver ("event") treats this encoder as a gamepad and shows only six of its twelve buttons
# (the codes 292 to 297), so Tab and Esc could not be used. Its "sdl" driver shows all twelve, named button1 to button12 (the
# SDL button number plus one), and names the joysticks by their name with _2 for the second of a kind. That driver handles at
# most four joysticks, and the AI Arcade pads would take two, so AdvanceMAME is started with those two hidden from SDL
# (ADV_HIDE_AI_PADS, in the launcher line): the panel's two encoders and two more controllers fit.

ADV_JOY = "dragonrise_inc_generic_usb_joystick"
ADV_OPTIONS = {"device_joystick": "sdl"}
ADV_HIDE_AI_PADS = "SDL_GAMECONTROLLER_IGNORE_DEVICES=0x1209/0xa101,0x1209/0xa102"


def _adv_button(joy, button):
    return f"joystick_button[{joy},button{button + 1}]"


def _adv_direction(joy, direction_sign):
    """joystick_digital[...] for a stick reading: abs 0 is x, abs 1 is y; a negative reading is left or up."""
    axis, sign = direction_sign
    if axis == 0:
        word = "left" if sign < 0 else "right"
        return f"joystick_digital[{joy},stick,x,{word}]"
    word = "up" if sign < 0 else "down"
    return f"joystick_digital[{joy},stick,y,{word}]"


def advmame_inputs(panel, joy1=ADV_JOY, joy2=ADV_JOY + "_2"):
    """[(input_map name, value)] for advmame.rc."""
    joy = {"P1": joy1, "P2": joy2}
    keys = {"P1": {"up": "up", "down": "down", "left": "left", "right": "right"},
            "P2": {"up": "r", "down": "f", "left": "d", "right": "g"}}
    button_keys = {"P1": ["lcontrol", "lalt", "space", "lshift", "z", "x"], "P2": ["a", "s", "q", "w", "e", "i"]}
    out = []
    for player in ("P1", "P2"):
        p = player.lower()
        stick = panel["players"][player]["stick"]
        for direction in ("up", "down", "left", "right"):
            out.append((f"{p}_{direction}", f"{_adv_direction(joy[player], stick[direction][1:])} or keyboard[0,{keys[player][direction]}]"))
        for n, idx in actions(panel, player).items():
            joys = " or ".join(_adv_button(joy[player], i) for i in idx)
            out.append((f"{p}_button{n}", f"{joys} or keyboard[0,{button_keys[player][n - 1]}]"))
    # twin-stick games (Ultra Tank): the left stick is Player 1's, the right stick is Player 2's
    for side, player in (("left", "P1"), ("right", "P2")):
        stick = panel["players"][player]["stick"]
        for direction in ("up", "down", "left", "right"):
            out.append((f"p1_double{side}_{direction}", _adv_direction(joy[player], stick[direction][1:])))
    out += [("coin1", f"{_adv_button(joy1, index(panel, 'P1', 'COIN'))} or keyboard[0,5]"),
            ("start1", f"{_adv_button(joy1, index(panel, 'P1', 'START'))} or keyboard[0,1]"),
            ("coin2", f"{_adv_button(joy2, index(panel, 'P2', 'COIN'))} or keyboard[0,6]"),
            ("start2", f"{_adv_button(joy2, index(panel, 'P2', 'START'))} or keyboard[0,2]")]
    ui = panel["layout"]["ui"]
    ui_map = {"menu": [("ui_configure", "tab")], "back": [("ui_cancel", "esc"), ("safequit", "esc")],
              "select": [("ui_select", "enter")], "pause": [("ui_pause", "p")]}
    for name, targets in ui_map.items():
        player, control = ui[name]
        for target, key in targets:
            out.append((target, f"{_adv_button(joy[player], index(panel, player, control))} or keyboard[0,{key}]"))
    stick1 = panel["players"]["P1"]["stick"]
    for direction in ("up", "down", "left", "right"):
        out.append((f"ui_{direction}", f"{_adv_direction(joy1, stick1[direction][1:])} or keyboard[0,{direction}]"))
    return out


def merge_advmame_rc(text, inputs, options=None):
    """advmame.rc with each input_map[name] line (and each option) replaced by the new value, or added at the end.
    Everything else stays."""
    options = ADV_OPTIONS if options is None else options
    lines = text.splitlines()
    wanted = {f"input_map[{name}]": value for name, value in inputs}
    wanted.update(options)
    seen = set()
    for i, line in enumerate(lines):
        key = line.split(" ", 1)[0]
        if key in wanted:
            lines[i] = f"{key} {wanted[key]}"
            seen.add(key)
    lines += [f"{key} {value}" for key, value in wanted.items() if key not in seen]
    return "\n".join(lines) + "\n"


def advmame_launcher(text, hide=ADV_HIDE_AI_PADS):
    """An emulators.cfg with the advmame line starting AdvanceMAME with `hide` in its environment. Other lines stay."""
    out = []
    for line in text.splitlines():
        m = re.match(r'^(advmame\s*=\s*")(?:env [A-Z_]+=\S+ )?(/opt/retropie/emulators/advmame/bin/advmame.*)$', line)
        out.append(f"{m.group(1)}env {hide} {m.group(2)}" if m else line)
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------- which emulator runs which game

# A game whose controls.json names an "emulator" runs on it instead of the one it has. The panel's map is complete and
# tested in MAME 0.251; AdvanceMAME shows the panel's encoders with only six of their twelve buttons and no way to exit
# with the panel, and has no per-device mouse. RetroArch's lr-mame2003 picks the mouse a game wants (pad_map.py).


def launcher_moves(games):
    """{emulators.cfg key (<system>_<rom>): emulator} for every game whose controls.json asks for one."""
    return {f"{g['_system']}_{key.split('/', 1)[1]}": g["emulator"] for key, g in sorted(games.items()) if g.get("emulator")}


def move_launchers(text, moves):
    """/opt/retropie/configs/all/emulators.cfg with each game's launcher set as `moves` says ({key: emulator}, from
    launcher_moves). Other lines stay."""
    lines = text.splitlines()
    wanted = dict(moves)
    seen = set()
    for i, line in enumerate(lines):
        key = line.split("=", 1)[0].strip()
        if key in wanted and "=" in line:
            lines[i] = f'{key} = "{wanted[key]}"'
            seen.add(key)
    lines += [f'{key} = "{value}"' for key, value in wanted.items() if key not in seen]
    return "\n".join(lines) + "\n"


def set_game_dip(cfg, system, tag, mask, defvalue, value):
    """A MAME game's cfg file (/opt/retropie/configs/mame-0251/cfg/<game>.cfg) with one DIP switch setting. `cfg` may be
    None (no file yet) or MAME's own file, which keeps its coin counters and other settings."""
    line = f'            <port tag="{tag}" type="DIPSWITCH" mask="{mask}" defvalue="{defvalue}" value="{value}" />'
    if not cfg:
        return ('<?xml version="1.0"?>\n<mameconfig version="10">\n    <system name="%s">\n        <input>\n%s\n        </input>\n'
                '    </system>\n</mameconfig>\n' % (system, line))
    cfg = cfg.lstrip("\ufeff")
    pattern = re.compile(r'[ \t]*<port tag="%s" type="DIPSWITCH" mask="%s"[^>]*/>\n?' % (re.escape(tag), mask))
    if pattern.search(cfg):
        return pattern.sub(lambda m: line + "\n", cfg, count=1)
    if "<input>" in cfg:
        return cfg.replace("<input>", "<input>\n" + line, 1)
    return cfg.replace("</system>", "        <input>\n" + line + "\n        </input>\n    </system>", 1)
