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


def merge_es_input(existing, entry, device_name):
    """es_input.cfg with this device's <inputConfig> replaced (or added). Other devices are left byte for byte."""
    pattern = re.compile(r'[ \t]*<inputConfig [^>]*deviceName=("|\')' + re.escape(device_name) + r'\1[^>]*>.*?</inputConfig>\n?', re.S)
    if pattern.search(existing):
        return pattern.sub(lambda m: entry, existing, count=1)
    return existing.replace("</inputList>", entry + "</inputList>", 1)


# ---------------------------------------------------------------- RetroArch

def retroarch_autoconfig(panel):
    """The joypad autoconfig. RetroPad B, A, Y, X, L, R are the arcade BUTTON_1..6 (as mame2003 reads them); Select is
    Coin and Start is Start. Esc is the hotkey and the exit (alone, as on the keyboard), Tab with Esc held opens the menu."""
    d = panel["device"]
    names = {1: "b", 2: "a", 3: "y", 4: "x", 5: "l", 6: "r"}
    first = actions(panel, "P1")
    lines = [f'input_device = "{d["evdev_name"]}"', 'input_driver = "udev"',
             f'input_vendor_id = "{int(d["vendor_id"], 16)}"', f'input_product_id = "{int(d["product_id"], 16)}"', ""]
    stick = panel["players"]["P1"]["stick"]
    for direction in ("left", "right", "up", "down"):
        _, axis, sign = stick[direction]
        lines.append(f'input_{direction}_axis = "{"+" if sign > 0 else "-"}{axis}"')
    lines.append("")
    for n, retro in names.items():
        lines.append(f'input_{retro}_btn = "{first[n][0]}"')
    lines += ["", f'input_select_btn = "{index(panel, "P1", "COIN")}"', f'input_start_btn = "{index(panel, "P1", "START")}"', "",
              f'input_enable_hotkey_btn = "{index(panel, "P1", "ESC")}"',
              f'input_exit_emulator_btn = "{index(panel, "P1", "ESC")}"',
              f'input_menu_toggle_btn = "{index(panel, "P1", "TAB")}"', ""]
    return "\n".join(lines)


# ---------------------------------------------------------------- MAME 0.251

def _direction_code(joy, direction_sign):
    axis, sign = direction_sign
    name = "XAXIS" if axis == 0 else "YAXIS"
    if axis == 0:
        side = "LEFT" if sign < 0 else "RIGHT"
    else:
        side = "UP" if sign < 0 else "DOWN"
    return f"JOYCODE_{joy}_{name}_{side}_SWITCH"


def mame_ports(panel, joy1=1, joy2=2):
    """[(MAME port type, input sequence)] for the default section: both players' sticks, six buttons, coin, start, and
    MAME's menu keys. joy1 and joy2 are MAME's joystick numbers for the P1 and P2 encoders (1 and 2 when the panel's
    encoders are the first two joysticks, which the order checks must confirm)."""
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


def mame_ctrlr(panel, joy1=1, joy2=2):
    """The ctrlr file for human mode (/home/pi/.mame/ctrlr/panel.cfg): only the default section; MAME's own defaults
    still apply to everything not listed (players 3 and 4, analog controls, service keys)."""
    out = ['<?xml version="1.0"?>', '<mameconfig version="10">', '    <system name="default">', "        <input>"]
    for port, seq in mame_ports(panel, joy1, joy2):
        out += [f'            <port type="{port}">', f'                <newseq type="standard">{seq}</newseq>', "            </port>"]
    out += ["        </input>", "    </system>", "</mameconfig>", ""]
    return "\n".join(out)


def mame_ini_with_ctrlr(ini, name):
    """mame.ini with its ctrlr line changed to `name`."""
    new, count = re.subn(r"^(ctrlr\s+)\S+", lambda m: m.group(1) + name, ini, count=1, flags=re.M)
    if not count:
        raise ValueError("mame.ini has no ctrlr line")
    return new


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
# AdvanceMAME's default joystick driver ("event") treats this encoder as a gamepad and shows only six of its twelve buttons,
# the codes 292 to 297, named y, b, tl, tr, tl2 and start (checked with the pretend panel on 17 October 2026). The other six
# cannot be used. Its "sdl" driver shows all twelve but seems to see only four joysticks in all, and the AI Arcade pads take
# two of those, so the event driver is kept. Each encoder is a joystick named vendor_product, the second with _2.
# So each player gets the action buttons that are visible (in the panel's A, B, X, Y, Snowflake, Star order), coin and
# start are on visible buttons, and menu and exit are chords of the visible coin and start buttons.

ADV_EVENT_BUTTONS = {292: "y", 293: "b", 294: "tl", 295: "tr", 296: "tl2", 297: "start"}
ADV_JOY = "0079_0006"
ADV_OPTIONS = {}


def _adv_name(panel, player, control):
    """AdvanceMAME's name for a player's control, or None when its button is one the event driver does not show."""
    return ADV_EVENT_BUTTONS.get(panel["players"][player]["buttons"].get(control))


def _adv_direction(joy, direction_sign):
    """joystick_digital[...] for a stick reading: abs 0 is x, abs 1 is y; a negative reading is left or up."""
    axis, sign = direction_sign
    if axis == 0:
        word = "left" if sign < 0 else "right"
        return f"joystick_digital[{joy},stick,x,{word}]"
    word = "up" if sign < 0 else "down"
    return f"joystick_digital[{joy},stick,y,{word}]"


def advmame_visible_actions(panel, player):
    """[control names] of a player's action buttons that AdvanceMAME can see, in the panel's order: BUTTON_1 first."""
    return [c for c in panel["layout"]["action_order"] if _adv_name(panel, player, c)]


def advmame_inputs(panel, joy1=ADV_JOY, joy2=ADV_JOY + "_2"):
    """[(input_map name, value)] for advmame.rc."""
    joy = {"P1": joy1, "P2": joy2}
    keys = {"P1": {"up": "up", "down": "down", "left": "left", "right": "right"},
            "P2": {"up": "r", "down": "f", "left": "d", "right": "g"}}
    button_keys = {"P1": ["lcontrol", "lalt", "space", "lshift", "z", "x"], "P2": ["a", "s", "q", "w", "e", "i"]}

    def button(player, control):
        return f"joystick_button[{joy[player]},{_adv_name(panel, player, control)}]"

    out = []
    for player in ("P1", "P2"):
        p = player.lower()
        stick = panel["players"][player]["stick"]
        for direction in ("up", "down", "left", "right"):
            out.append((f"{p}_{direction}", f"{_adv_direction(joy[player], stick[direction][1:])} or keyboard[0,{keys[player][direction]}]"))
        for n, control in enumerate(advmame_visible_actions(panel, player), 1):
            out.append((f"{p}_button{n}", f"{button(player, control)} or keyboard[0,{button_keys[player][n - 1]}]"))
    # twin-stick games (Battlezone, Ultra Tank): the left stick is Player 1's, the right stick is Player 2's
    for side, player in (("left", "P1"), ("right", "P2")):
        stick = panel["players"][player]["stick"]
        for direction in ("up", "down", "left", "right"):
            out.append((f"p1_double{side}_{direction}", _adv_direction(joy[player], stick[direction][1:])))
    out += [("coin1", f"{button('P1', 'COIN')} or keyboard[0,5]"), ("start1", f"{button('P1', 'START')} or keyboard[0,1]"),
            ("coin2", f"{button('P2', 'COIN')} or keyboard[0,6]"), ("start2", f"{button('P2', 'START')} or keyboard[0,2]")]
    # P2's Enter and Pause are visible; Tab and Esc (on the P1 encoder) are not, so those two are chords
    out += [("ui_select", f"{button('P2', 'ENTER')} or keyboard[0,enter]"),
            ("ui_pause", f"{button('P2', 'PAUSE')} or keyboard[0,p]"),
            ("ui_cancel", f"{button('P1', 'COIN')} {button('P1', 'START')} or keyboard[0,esc]"),
            ("ui_configure", f"{button('P2', 'COIN')} {button('P2', 'START')} or keyboard[0,tab]")]
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


# ---------------------------------------------------------------- which emulator runs which game

# AdvanceMAME shows the panel's encoders with only six of their twelve buttons and no way to exit with the panel, so the
# games it ran that MAME 0.251 can also run from the cabinet's ROMs (checked with `mame -verifyroms` on 17 October 2026)
# move to MAME 0.251, whose panel map is complete and was tested. The other AdvanceMAME games stay on it.
MOVE_TO_MAME251 = ["bzone", "bradley", "dkong", "pisces"]


def move_launchers(text, games=MOVE_TO_MAME251, emulator="mame-0.251"):
    """/opt/retropie/configs/all/emulators.cfg with each arcade game's launcher set to `emulator`. Other lines stay."""
    lines = text.splitlines()
    wanted = {f"arcade_{g}": emulator for g in games}
    seen = set()
    for i, line in enumerate(lines):
        key = line.split("=", 1)[0].strip()
        if key in wanted and "=" in line:
            lines[i] = f'{key} = "{wanted[key]}"'
            seen.add(key)
    lines += [f'{key} = "{value}"' for key, value in wanted.items() if key not in seen]
    return "\n".join(lines) + "\n"
