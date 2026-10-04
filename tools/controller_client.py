#!/usr/bin/env python3
"""
Small Windows/Linux client for the AI Arcade Controller Broker.

Examples:
    python controller_client.py ping
    python controller_client.py tap 1 LEFT
    python controller_client.py tap 1 BUTTON_1
    python controller_client.py press 1 RIGHT
    python controller_client.py release 1 RIGHT
    python controller_client.py release-all
"""

from __future__ import print_function

import argparse
import json
import socket
import sys
from gamelib import DEFAULT_PI_HOST


def send(host, port, payload):
    data = (json.dumps(payload) + "\n").encode("utf-8")

    sock = socket.create_connection((host, port), timeout=5)
    try:
        sock.sendall(data)
        response = b""
        while not response.endswith(b"\n"):
            chunk = sock.recv(4096)
            if not chunk:
                break
            response += chunk
    finally:
        sock.close()

    if not response:
        raise RuntimeError("No response from broker")

    return json.loads(response.decode("utf-8").strip())


def dismiss_warning(host, port=8765):
    """Tap Player 1's button 1 once. MAME shows a warning screen before a game its driver marks imperfect (Vanguard) and
    runs no Lua script until a key is pressed; start-up code calls this when the game has not begun reporting."""
    return send(host, port, {"op": "tap", "player": 1, "action": "BUTTON_1", "ms": 120})


def main():
    parser = argparse.ArgumentParser(description="AI Arcade controller client")
    parser.add_argument("--host", default=DEFAULT_PI_HOST)
    parser.add_argument("--port", type=int, default=8765)

    sub = parser.add_subparsers(dest="command")

    sub.add_parser("ping")
    sub.add_parser("status")
    sub.add_parser("release-all")

    for name in ("tap", "press", "release"):
        p = sub.add_parser(name)
        p.add_argument("player", type=int, choices=(1, 2))
        p.add_argument("action")
        if name == "tap":
            p.add_argument("--ms", type=int, default=120)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 2

    if args.command == "ping":
        payload = {"op": "ping"}
    elif args.command == "status":
        payload = {"op": "status"}
    elif args.command == "release-all":
        payload = {"op": "release_all"}
    else:
        payload = {
            "op": args.command,
            "player": args.player,
            "action": args.action.upper(),
        }
        if args.command == "tap":
            payload["ms"] = args.ms

    try:
        response = send(args.host, args.port, payload)
    except Exception as exc:
        print("ERROR:", exc, file=sys.stderr)
        return 1

    print(json.dumps(response, indent=2, sort_keys=True))
    return 0 if response.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
