#!/usr/bin/env python3
"""
AI Arcade virtual controller proof-of-concept for RetroPie / EmulationStation.

Run on the Raspberry Pi with:
    sudo python3 ai_arcade_controller_test.py

This creates a virtual gamepad named "AI Arcade Controller" using /dev/uinput.
It stays alive while the script is running and lets you inject a few test
controller events from the terminal.
"""

import sys
import time

from evdev import AbsInfo, UInput, ecodes as e


CAPABILITIES = {
    e.EV_KEY: [
        e.BTN_SOUTH,   # A
        e.BTN_EAST,    # B
        e.BTN_NORTH,   # X
        e.BTN_WEST,    # Y
        e.BTN_START,
        e.BTN_SELECT,
    ],
    e.EV_ABS: [
        (e.ABS_HAT0X, AbsInfo(value=0, min=-1, max=1, fuzz=0, flat=0, resolution=0)),
        (e.ABS_HAT0Y, AbsInfo(value=0, min=-1, max=1, fuzz=0, flat=0, resolution=0)),
    ],
}


def tap_key(ui, key_code, duration=0.12):
    ui.write(e.EV_KEY, key_code, 1)
    ui.syn()
    time.sleep(duration)
    ui.write(e.EV_KEY, key_code, 0)
    ui.syn()


def tap_hat(ui, axis, value, duration=0.16):
    ui.write(e.EV_ABS, axis, value)
    ui.syn()
    time.sleep(duration)
    ui.write(e.EV_ABS, axis, 0)
    ui.syn()


def main():
    try:
        ui = UInput(
            CAPABILITIES,
            name="AI Arcade Controller",
            bustype=e.BUS_USB,
            vendor=0x1209,
            product=0xA1A1,
            version=0x0001,
        )
    except PermissionError:
        print("Permission denied opening /dev/uinput.")
        print("Run this script with sudo for the first test.")
        return 1
    except Exception as exc:
        print(f"Could not create virtual controller: {exc}")
        return 1

    print()
    print("Virtual controller created: AI Arcade Controller")
    print(f"Linux device: {ui.device.path}")
    print()
    print("Leave this script running while testing EmulationStation.")
    print("Commands:")
    print("  l = tap LEFT")
    print("  r = tap RIGHT")
    print("  u = tap UP")
    print("  d = tap DOWN")
    print("  a = tap A / BTN_SOUTH")
    print("  b = tap B / BTN_EAST")
    print("  s = tap START")
    print("  e = tap SELECT")
    print("  q = quit")
    print()

    try:
        while True:
            cmd = input("AI Arcade> ").strip().lower()

            if cmd == "q":
                break
            elif cmd == "l":
                tap_hat(ui, e.ABS_HAT0X, -1)
            elif cmd == "r":
                tap_hat(ui, e.ABS_HAT0X, 1)
            elif cmd == "u":
                tap_hat(ui, e.ABS_HAT0Y, -1)
            elif cmd == "d":
                tap_hat(ui, e.ABS_HAT0Y, 1)
            elif cmd == "a":
                tap_key(ui, e.BTN_SOUTH)
            elif cmd == "b":
                tap_key(ui, e.BTN_EAST)
            elif cmd == "s":
                tap_key(ui, e.BTN_START)
            elif cmd == "e":
                tap_key(ui, e.BTN_SELECT)
            elif not cmd:
                continue
            else:
                print("Unknown command.")
    finally:
        ui.close()
        print("Virtual controller closed.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
