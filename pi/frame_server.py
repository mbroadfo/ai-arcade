#!/usr/bin/env python3
"""Stream the game's video frames from the Pi to the PC's Observatory, the way state_server.py streams its state.

tools/mame_video_export.lua writes /dev/shm/ai-arcade-frame.bin a few times a second (frame counter, width, height,
quarter turns, B G R X pixels). This process sends each new one to connected clients, compressed (a Pac-Man frame is
252 KB raw and a few KB compressed, so the video does not crowd the state stream on the LAN). As in state_server.py a
slow client gets the newest frame, never a backlog.

Wire format: state_server.py's framing (1 byte kind, 4 byte big-endian length, payload).
  kind "H": JSON hello: {"stream": "frames", "compression": "zlib"}
  kind "S": the file's first 10 bytes as they are, then the pixels zlib-compressed

The video is for people watching; the decider never reads it. Standard library only.
"""
import argparse
import sys
import zlib

from state_server import StateServer

DEFAULT_PORT = 8767
FRAME_FILE = "/dev/shm/ai-arcade-frame.bin"
HEADER = 10  # frame (4), width (2), height (2), quarter turns (2)
HELLO = {"stream": "frames", "compression": "zlib"}


def compress(raw):
    return raw[:HEADER] + zlib.compress(raw[HEADER:], 1)


def make_server(frame_file=FRAME_FILE, port=DEFAULT_PORT, host="0.0.0.0", poll=0.01):
    return StateServer(frame_file, None, port=port, host=host, poll=poll, hello=HELLO, encode=compress)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--frame-file", default=FRAME_FILE)
    args = parser.parse_args()
    server = make_server(args.frame_file, args.port)
    sys.stderr.write("frame server listening on %d\n" % server.port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.close()


if __name__ == "__main__":
    main()
