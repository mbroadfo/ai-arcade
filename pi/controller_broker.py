#!/usr/bin/env python3
"""
AI Arcade Controller Broker

Runs on the RetroPie Raspberry Pi. Creates two stable virtual Linux gamepads:

    AI Arcade Player 1
    AI Arcade Player 2

and exposes a small newline-delimited JSON TCP API so another machine can
control them.

Designed for older RetroPie/Raspbian Buster Python 3.x.

Protocol examples (one JSON object per line):

    {"player":1,"action":"LEFT","op":"tap","ms":120}
    {"player":1,"action":"BUTTON_1","op":"press"}
    {"player":1,"action":"BUTTON_1","op":"release"}
    {"player":1,"action":"START","op":"tap"}
    {"player":1,"action":"COIN","op":"tap"}
    {"op":"release_all"}

Responses are also one JSON object per line.
"""

from __future__ import print_function

import argparse
import json
import signal
import socketserver
import sys
import threading
import time

from evdev import AbsInfo, UInput, ecodes as e


# ---------------------------------------------------------------------------
# Canonical arcade controller contract
#
# Linux joystick button ordering is intentionally chosen to match a conventional
# 10-button gamepad layout:
#
#   button 0  BUTTON_1
#   button 1  BUTTON_2
#   button 2  BUTTON_3
#   button 3  BUTTON_4
#   button 4  BUTTON_5
#   button 5  BUTTON_6
#   button 6  STICK_1
#   button 7  STICK_2
#   button 8  COIN / SELECT
#   button 9  START
#
# Joystick:
#   axis 0 = horizontal (left - / right +)
#   axis 1 = vertical   (up   - / down  +)
# ---------------------------------------------------------------------------

BUTTON_CODES = {
    "BUTTON_1": e.BTN_SOUTH,   # joystick button 0
    "BUTTON_2": e.BTN_EAST,    # joystick button 1
    "BUTTON_3": e.BTN_C,       # joystick button 2
    "BUTTON_4": e.BTN_NORTH,   # joystick button 3
    "BUTTON_5": e.BTN_WEST,    # joystick button 4
    "BUTTON_6": e.BTN_Z,       # joystick button 5
    "STICK_1": e.BTN_TL,       # joystick button 6
    "STICK_2": e.BTN_TR,       # joystick button 7
    "COIN": e.BTN_SELECT,      # joystick button 8
    "START": e.BTN_START,      # joystick button 9
}

DIRECTION_AXES = {
    "LEFT":  (e.ABS_X, -32767),
    "RIGHT": (e.ABS_X,  32767),
    "UP":    (e.ABS_Y, -32767),
    "DOWN":  (e.ABS_Y,  32767),
}

ALL_ACTIONS = sorted(list(BUTTON_CODES.keys()) + list(DIRECTION_AXES.keys()))


def make_capabilities():
    return {
        e.EV_KEY: [
            e.BTN_SOUTH,
            e.BTN_EAST,
            e.BTN_C,
            e.BTN_NORTH,
            e.BTN_WEST,
            e.BTN_Z,
            e.BTN_TL,
            e.BTN_TR,
            e.BTN_SELECT,
            e.BTN_START,
        ],
        e.EV_ABS: [
            (e.ABS_X, AbsInfo(value=0, min=-32767, max=32767,
                              fuzz=0, flat=128, resolution=0)),
            (e.ABS_Y, AbsInfo(value=0, min=-32767, max=32767,
                              fuzz=0, flat=128, resolution=0)),
        ],
    }


class VirtualArcadeController(object):
    def __init__(self, player_number):
        self.player_number = player_number
        self.name = "AI Arcade Player %d" % player_number
        self.lock = threading.RLock()
        self.pressed_buttons = set()
        self.axis_state = {e.ABS_X: 0, e.ABS_Y: 0}

        # Stable project-owned test IDs. P1/P2 get distinct product IDs.
        product = 0xA101 if player_number == 1 else 0xA102

        self.ui = UInput(
            make_capabilities(),
            name=self.name,
            bustype=e.BUS_USB,
            vendor=0x1209,
            product=product,
            version=0x0001,
        )

    @property
    def device_path(self):
        return self.ui.device.path

    def _sync(self):
        self.ui.syn()

    def press(self, action):
        action = action.upper()
        with self.lock:
            if action in BUTTON_CODES:
                code = BUTTON_CODES[action]
                self.ui.write(e.EV_KEY, code, 1)
                self.pressed_buttons.add(code)
                self._sync()
                return

            if action in DIRECTION_AXES:
                axis, value = DIRECTION_AXES[action]

                # One direction on an axis replaces the opposite direction.
                self.ui.write(e.EV_ABS, axis, value)
                self.axis_state[axis] = value
                self._sync()
                return

            raise ValueError("Unknown action: %s" % action)

    def release(self, action):
        action = action.upper()
        with self.lock:
            if action in BUTTON_CODES:
                code = BUTTON_CODES[action]
                self.ui.write(e.EV_KEY, code, 0)
                self.pressed_buttons.discard(code)
                self._sync()
                return

            if action in DIRECTION_AXES:
                axis, value = DIRECTION_AXES[action]

                # Only center the axis if this action currently owns it.
                if self.axis_state.get(axis) == value:
                    self.ui.write(e.EV_ABS, axis, 0)
                    self.axis_state[axis] = 0
                    self._sync()
                return

            raise ValueError("Unknown action: %s" % action)

    def tap(self, action, duration_ms=120):
        self.press(action)
        time.sleep(max(1, int(duration_ms)) / 1000.0)
        self.release(action)

    def release_all(self):
        with self.lock:
            for code in list(self.pressed_buttons):
                self.ui.write(e.EV_KEY, code, 0)
            self.pressed_buttons.clear()

            self.ui.write(e.EV_ABS, e.ABS_X, 0)
            self.ui.write(e.EV_ABS, e.ABS_Y, 0)
            self.axis_state[e.ABS_X] = 0
            self.axis_state[e.ABS_Y] = 0
            self._sync()

    def close(self):
        try:
            self.release_all()
        finally:
            self.ui.close()


class ControllerBroker(object):
    def __init__(self):
        self.controllers = {
            1: VirtualArcadeController(1),
            2: VirtualArcadeController(2),
        }

    def execute(self, message):
        op = str(message.get("op", "")).lower()

        if op == "ping":
            return {
                "ok": True,
                "service": "ai-arcade-controller-broker",
                "players": [1, 2],
                "actions": ALL_ACTIONS,
            }

        if op == "status":
            return {
                "ok": True,
                "controllers": {
                    "1": {
                        "name": self.controllers[1].name,
                        "device": self.controllers[1].device_path,
                    },
                    "2": {
                        "name": self.controllers[2].name,
                        "device": self.controllers[2].device_path,
                    },
                },
            }

        if op == "release_all":
            for controller in self.controllers.values():
                controller.release_all()
            return {"ok": True, "op": "release_all"}

        try:
            player = int(message.get("player"))
        except Exception:
            raise ValueError("player must be 1 or 2")

        if player not in self.controllers:
            raise ValueError("player must be 1 or 2")

        action = str(message.get("action", "")).upper()
        if action not in ALL_ACTIONS:
            raise ValueError(
                "Unknown action '%s'. Valid actions: %s"
                % (action, ", ".join(ALL_ACTIONS))
            )

        controller = self.controllers[player]

        if op == "press":
            controller.press(action)
        elif op == "release":
            controller.release(action)
        elif op == "tap":
            ms = int(message.get("ms", 120))
            controller.tap(action, ms)
        else:
            raise ValueError("op must be press, release, tap, ping, status, or release_all")

        return {
            "ok": True,
            "player": player,
            "action": action,
            "op": op,
        }

    def close(self):
        for controller in self.controllers.values():
            controller.close()


BROKER = None


class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True


class RequestHandler(socketserver.StreamRequestHandler):
    def handle(self):
        peer = "%s:%s" % self.client_address
        print("Client connected:", peer)

        while True:
            raw = self.rfile.readline()
            if not raw:
                break

            try:
                text = raw.decode("utf-8").strip()
                if not text:
                    continue

                message = json.loads(text)
                result = BROKER.execute(message)
            except Exception as exc:
                result = {"ok": False, "error": str(exc)}

            encoded = (json.dumps(result, sort_keys=True) + "\n").encode("utf-8")
            self.wfile.write(encoded)
            self.wfile.flush()

        print("Client disconnected:", peer)


def main():
    global BROKER

    parser = argparse.ArgumentParser(description="AI Arcade virtual controller broker")
    parser.add_argument("--host", default="0.0.0.0",
                        help="Address to listen on (default: 0.0.0.0)")
    parser.add_argument("--port", default=8765, type=int,
                        help="TCP port (default: 8765)")
    args = parser.parse_args()

    try:
        BROKER = ControllerBroker()
    except PermissionError:
        print("Permission denied opening /dev/uinput.", file=sys.stderr)
        print("For the first test, run with sudo.", file=sys.stderr)
        return 1
    except Exception as exc:
        print("Could not create virtual controllers: %s" % exc, file=sys.stderr)
        return 1

    print("")
    print("AI Arcade Controller Broker")
    print("---------------------------")
    print("P1: %s -> %s" % (
        BROKER.controllers[1].name,
        BROKER.controllers[1].device_path,
    ))
    print("P2: %s -> %s" % (
        BROKER.controllers[2].name,
        BROKER.controllers[2].device_path,
    ))
    print("Listening on %s:%d" % (args.host, args.port))
    print("")

    server = ThreadedTCPServer((args.host, args.port), RequestHandler)

    stopping = {"value": False}

    def shutdown_handler(signum, frame):
        if stopping["value"]:
            return
        stopping["value"] = True
        print("\nStopping broker...")
        # shutdown() must be called from another thread than serve_forever()
        threading.Thread(target=server.shutdown).start()

    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)

    try:
        server.serve_forever(poll_interval=0.25)
    finally:
        server.server_close()
        if BROKER is not None:
            BROKER.close()

    print("Broker stopped.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
