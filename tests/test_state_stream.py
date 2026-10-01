from pathlib import Path
import struct
import sys
import threading
import time

from games.arcade import pacman
from games.arcade.pacman import state as ps
import state_client
import state_server


def write_state(path, frame, **cells):
    """Write a compact export file for ps.AGENT_REGIONS with the given absolute-address cells set."""
    image = bytearray(0x1000)
    for addr, value in cells.items():
        image[int(addr[1:], 16) - ps.BASE] = value
    body = b"".join(bytes(image[s - ps.BASE:e - ps.BASE + 1]) for s, e, _ in ps.AGENT_REGIONS)
    tmp = Path(str(path) + ".tmp")
    tmp.write_bytes(struct.pack("<I", frame) + body)
    for _ in range(200):  # Windows refuses to replace a file another thread has open; Linux does not
        try:
            tmp.replace(path)
            return
        except PermissionError:
            time.sleep(0.002)
    raise PermissionError(path)


def start_server(tmp_path):
    state_file = tmp_path / "state.bin"
    write_state(state_file, 1, a4E6E=1, a4E00=1)
    regions = [list(r) for r in ps.AGENT_REGIONS]
    server = state_server.StateServer(str(state_file), regions, port=0, host="127.0.0.1", poll=0.001)
    stop = threading.Event()
    thread = threading.Thread(target=server.serve_forever, kwargs={"stop": stop.is_set}, daemon=True)
    thread.start()
    return server, state_file, stop, thread


def test_client_receives_hello_and_decoded_state(tmp_path):
    server, _, stop, thread = start_server(tmp_path)
    try:
        stream = state_client.StateStream("127.0.0.1", server.port, game=pacman)
        assert stream.regions == list(ps.AGENT_REGIONS)
        frame, state, _ = stream.next_state()
        assert frame == 1 and state.credits == 1 and state.mode == "attract"
        stream.close()
    finally:
        stop.set()
        thread.join(1)
        server.close()


def test_new_frames_are_pushed_and_unchanged_frames_are_not(tmp_path):
    server, state_file, stop, thread = start_server(tmp_path)
    try:
        stream = state_client.StateStream("127.0.0.1", server.port, game=pacman)
        stream.next_state()
        write_state(state_file, 2, a4E6E=2, a4E00=3)
        frame, state, _ = stream.next_state()
        assert (frame, state.credits, state.mode) == (2, 2, "playing")
        stream.close()
    finally:
        stop.set()
        thread.join(1)
        server.close()


def test_latest_returns_newest_and_waits_for_newer(tmp_path):
    server, state_file, stop, thread = start_server(tmp_path)
    try:
        stream = state_client.StateStream("127.0.0.1", server.port, game=pacman)
        stream.start_latest()
        assert stream.latest()[0] == 1
        write_state(state_file, 5, a4E6E=4)
        frame, state, _ = stream.latest(newer_than=1)
        assert frame == 5 and state.credits == 4
        try:
            stream.latest(newer_than=5, timeout=0.2)
            assert False, "should time out when nothing newer arrives"
        except TimeoutError:
            pass
        stream.close()
    finally:
        stop.set()
        thread.join(1)
        server.close()


def test_server_survives_a_client_disconnecting(tmp_path):
    server, state_file, stop, thread = start_server(tmp_path)
    try:
        first = state_client.StateStream("127.0.0.1", server.port, game=pacman)
        first.close()
        write_state(state_file, 2)
        second = state_client.StateStream("127.0.0.1", server.port, game=pacman)
        assert second.next_state()[0] == 2
        second.close()
    finally:
        stop.set()
        thread.join(1)
        server.close()


def test_slow_reader_is_not_dropped_and_sees_fresh_data(tmp_path):
    server, state_file, stop, thread = start_server(tmp_path)
    try:
        stream = state_client.StateStream("127.0.0.1", server.port, game=pacman)
        stream.next_state()
        for frame in range(2, 400):  # the reader stalls (no recv) while many snapshots are produced
            write_state(state_file, frame, a4E6E=frame % 100)
            time.sleep(0.001)
        time.sleep(0.4)
        newest = 0
        stream.sock.settimeout(0.5)
        try:
            while True:
                newest = stream.next_state()[0]
        except OSError:
            pass
        assert newest > 100, "reader should catch up to recent frames, not be disconnected"
        stream.close()
    finally:
        stop.set()
        thread.join(1)
        server.close()
