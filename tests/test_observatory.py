import io
import json
import socket
import struct
import threading
import time
from pathlib import Path


import frame_server
import observatory
from arcadekit.observatory import EventSink, LiveSink


def frame_file_bytes(frame, width, height, turns, colour_at):
    """A video export file: header, then B G R X pixels, colour_at(x, y) -> (r, g, b)."""
    pixels = bytearray()
    for y in range(height):
        for x in range(width):
            r, g, b = colour_at(x, y)
            pixels += bytes((b, g, r, 255))
    return struct.pack("<IHHH", frame, width, height, turns) + bytes(pixels)


def red_top_left(x, y):
    return (255, 0, 0) if (x, y) == (0, 0) else (0, 0, 0)


def test_compressed_frame_decodes_to_the_same_upright_image():
    raw = frame_file_bytes(7, 4, 2, 0, red_top_left)
    frame, image = observatory.decode_frame(frame_server.compress(raw))
    assert frame == 7 and image.size == (4, 2)
    assert image.getpixel((0, 0)) == (255, 0, 0) and image.getpixel((1, 0)) == (0, 0, 0)


def test_a_rot90_machine_is_turned_clockwise():
    # Pac-Man's bitmap is wider than tall and the machine is rot90: upright, the top-left pixel ends at the top right
    _, image = observatory.decode_frame(frame_server.compress(frame_file_bytes(1, 4, 2, 1, red_top_left)))
    assert image.size == (2, 4)
    assert image.getpixel((1, 0)) == (255, 0, 0)


def read_message(conn):
    def exact(n):
        data = b""
        while len(data) < n:
            chunk = conn.recv(n - len(data))
            assert chunk, "server closed"
            data += chunk
        return data
    kind = exact(1)
    return kind, exact(struct.unpack(">I", exact(4))[0])


def test_frame_server_says_hello_and_sends_new_frames_compressed(tmp_path):
    path = tmp_path / "frame.bin"
    path.write_bytes(frame_file_bytes(3, 8, 8, 0, red_top_left))
    server = frame_server.make_server(str(path), port=0, host="127.0.0.1", poll=0.001)
    stop = threading.Event()
    thread = threading.Thread(target=server.serve_forever, kwargs={"stop": stop.is_set}, daemon=True)
    thread.start()
    try:
        with socket.create_connection(("127.0.0.1", server.port), timeout=2) as conn:
            kind, hello = read_message(conn)
            assert kind == b"H" and json.loads(hello) == frame_server.HELLO
            kind, payload = read_message(conn)
            assert kind == b"S" and len(payload) < 8 * 8 * 4  # compressed
            frame, image = observatory.decode_frame(payload)
            assert frame == 3 and image.getpixel((0, 0)) == (255, 0, 0)
    finally:
        stop.set()
        thread.join(1)
        server.close()


class FakeFile(io.StringIO):
    def close(self):
        self.closed_flag = True


def listener():
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    sock.listen(1)
    return sock


def test_event_sink_writes_the_file_and_the_live_sink():
    sock = listener()
    live = LiveSink(sock.getsockname())
    log = FakeFile()
    sink = EventSink(log, live)
    sink.write(json.dumps({"event": "goal", "goal": "hunt"}) + "\n")
    conn, _ = sock.accept()
    conn.settimeout(2)
    received = conn.makefile("r").readline()
    assert json.loads(received) == {"event": "goal", "goal": "hunt"}
    assert log.getvalue() == received
    sink.close()
    conn.close()
    sock.close()


def test_live_sink_never_blocks_and_drops_when_nobody_listens():
    sock = listener()
    address = sock.getsockname()
    sock.close()  # nothing listening there now
    live = LiveSink(address)
    started = time.time()
    for i in range(5000):
        live.send({"event": "x", "i": i})
    assert time.time() - started < 1.0
    deadline = time.time() + 3
    while live.dropped == 0 and time.time() < deadline:
        time.sleep(0.05)
    assert live.dropped > 0
    live.close(drain_seconds=0)


def test_hub_keeps_events_in_order_and_only_the_newest_status():
    hub = observatory.Hub()
    hub.add_event({"event": "goal", "goal": "a"})
    hub.add_event({"event": "status", "score": 10})
    hub.add_event({"event": "status", "score": 20})
    hub.add_event({"event": "goal", "goal": "b"})
    assert [r["goal"] for _, r in hub.events] == ["a", "b"]
    assert hub.status == {"event": "status", "score": 20}
    hub.add_event({"event": "run", "label": "next"})
    assert [r["event"] for _, r in hub.events] == ["run"]  # a new run starts the timeline afresh


def test_page_exists_and_reads_the_event_stream():
    page = Path(observatory.PAGE).read_text(encoding="utf-8")
    assert 'new EventSource("/events")' in page
    for kind in ("event", "status", "frame", "video"):
        assert f'addEventListener("{kind}"' in page


def test_hub_remembers_the_run_for_pages_opened_later():
    hub = observatory.Hub()
    hub.add_event({"event": "run", "label": "x"})
    for i in range(observatory.KEEP_EVENTS + 5):
        hub.add_event({"event": "move", "i": i})
    assert hub.run == {"event": "run", "label": "x"}
    assert all(r["event"] == "move" for _, r in hub.events)  # the run event itself has scrolled out


def test_pacman_tiles_map_onto_the_upright_screen():
    from arcadekit.kits.pacman_board import screen
    # tile (0x20, 0x20) is the playfield's top-right cell: column 27, row 2 (the score rows are above it)
    assert screen.apply(screen.TILE_TO_PX, (0x20, 0x20)) == (27 * 8 + 4, 2 * 8 + 4)
    # h rises leftward: tile 0x3B is column 0
    assert screen.apply(screen.TILE_TO_PX, (0x20, 0x3B))[0] == 4
