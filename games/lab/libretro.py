"""A headless libretro frontend: one core, one ROM, software pixels, joypad, RAM.

Callbacks are kept on the instance. If they are garbage-collected the core
segfaults the next time it draws a frame. Unknown environment commands return
false, which is the libretro way of saying "use your default".
"""
from __future__ import annotations

import ctypes
import os
import sys
from pathlib import Path

import numpy as np

# Environment commands this frontend understands. Numbers are append-only in libretro.h.
_SET_PIXEL_FORMAT = 10
_GET_CAN_DUPE = 3
_GET_SYSTEM_DIRECTORY = 9
_SET_INPUT_DESCRIPTORS = 11
_SET_VARIABLES = 16
_GET_VARIABLE_UPDATE = 17
_GET_SAVE_DIRECTORY = 31
_GET_LANGUAGE = 39
_SHUTDOWN = 7

_MEMORY_SYSTEM_RAM = 2
_DEVICE_JOYPAD = 1

_ENV_FUN = ctypes.CFUNCTYPE(ctypes.c_bool, ctypes.c_uint, ctypes.c_void_p)
_VIDEO_FUN = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_uint, ctypes.c_uint, ctypes.c_size_t)
_AUDIO_SAMPLE_FUN = ctypes.CFUNCTYPE(None, ctypes.c_int16, ctypes.c_int16)
_AUDIO_BATCH_FUN = ctypes.CFUNCTYPE(ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t)
_INPUT_POLL_FUN = ctypes.CFUNCTYPE(None)
_INPUT_STATE_FUN = ctypes.CFUNCTYPE(ctypes.c_int16, ctypes.c_uint, ctypes.c_uint, ctypes.c_uint, ctypes.c_uint)


class _SystemInfo(ctypes.Structure):
    _fields_ = [
        ("library_name", ctypes.c_char_p),
        ("library_version", ctypes.c_char_p),
        ("valid_extensions", ctypes.c_char_p),
        ("need_fullpath", ctypes.c_bool),
        ("block_extract", ctypes.c_bool),
    ]


class _GameGeometry(ctypes.Structure):
    _fields_ = [
        ("base_width", ctypes.c_uint),
        ("base_height", ctypes.c_uint),
        ("max_width", ctypes.c_uint),
        ("max_height", ctypes.c_uint),
        ("aspect_ratio", ctypes.c_float),
    ]


class _SystemTiming(ctypes.Structure):
    _fields_ = [("fps", ctypes.c_double), ("sample_rate", ctypes.c_double)]


class _AVInfo(ctypes.Structure):
    _fields_ = [("geometry", _GameGeometry), ("timing", _SystemTiming)]


class _GameInfo(ctypes.Structure):
    _fields_ = [
        ("path", ctypes.c_char_p),
        ("data", ctypes.c_void_p),
        ("size", ctypes.c_size_t),
        ("meta", ctypes.c_char_p),
    ]


def _decode(buf: bytes, width: int, height: int, pitch: int, fmt: int) -> np.ndarray:
    if fmt == 1:
        rows = np.frombuffer(buf, dtype=np.uint8).reshape(height, pitch)
        pix = rows.reshape(height, pitch // 4, 4)[:, :width]
        return np.ascontiguousarray(pix[:, :, [2, 1, 0]])
    if fmt == 2:
        rows = np.frombuffer(buf, dtype="<u2").reshape(height, pitch // 2)[:, :width]
        red = ((rows >> 11) & 31).astype(np.uint8) << 3
        green = ((rows >> 5) & 63).astype(np.uint8) << 2
        blue = (rows & 31).astype(np.uint8) << 3
        return np.dstack((red, green, blue))
    rows = np.frombuffer(buf, dtype="<u2").reshape(height, pitch // 2)[:, :width]
    red = ((rows >> 10) & 31).astype(np.uint8) << 3
    green = ((rows >> 5) & 31).astype(np.uint8) << 3
    blue = (rows & 31).astype(np.uint8) << 3
    return np.dstack((red, green, blue))


class LibretroRunner:
    """One loaded core. Not safe to share across threads or to open twice in one process."""

    def __init__(self, core_path: Path, rom_path: Path, buttons: dict[str, int]):
        os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
        self.buttons = buttons
        self.held: set[str] = set()
        self.pixel_format = 0
        self.shutdown = False
        self.core_path = Path(core_path)
        self.rom_path = Path(rom_path)
        self._seen_commands: set[int] = set()
        system = self.core_path.parent.parent / "system"
        saves = system / "saves"
        system.mkdir(parents=True, exist_ok=True)
        saves.mkdir(parents=True, exist_ok=True)
        # The core keeps these char* values. A c_char_p assignment copies into a
        # temporary that dies when the callback returns, so hand it the buffer address.
        self._system_dir = ctypes.create_string_buffer(os.fsencode(str(system)))
        self._save_dir = ctypes.create_string_buffer(os.fsencode(str(saves)))
        self.rgb: np.ndarray | None = None
        self.width = 0
        self.height = 0

        self._env_cb = _ENV_FUN(self._environment)
        self._video_cb = _VIDEO_FUN(self._video)
        self._audio_sample_cb = _AUDIO_SAMPLE_FUN(self._audio_sample)
        self._audio_batch_cb = _AUDIO_BATCH_FUN(self._audio_batch)
        self._poll_cb = _INPUT_POLL_FUN(self._poll)
        self._state_cb = _INPUT_STATE_FUN(self._state)

        if sys.platform == "win32" and hasattr(os, "add_dll_directory"):
            os.add_dll_directory(str(self.core_path.parent))
        self.lib = ctypes.CDLL(str(self.core_path))
        self._bind()
        self.lib.retro_set_environment(self._env_cb)
        self.lib.retro_init()
        self.lib.retro_set_video_refresh(self._video_cb)
        self.lib.retro_set_audio_sample(self._audio_sample_cb)
        self.lib.retro_set_audio_sample_batch(self._audio_batch_cb)
        self.lib.retro_set_input_poll(self._poll_cb)
        self.lib.retro_set_input_state(self._state_cb)
        try:
            self.lib.retro_set_controller_port_device(0, _DEVICE_JOYPAD)
        except AttributeError:
            pass

        info = _SystemInfo()
        self.lib.retro_get_system_info(ctypes.byref(info))
        rom = self.rom_path.read_bytes()
        self._rom_buf = ctypes.create_string_buffer(rom)
        self._rom_path_p = ctypes.c_char_p(str(self.rom_path).encode())
        game = _GameInfo()
        game.path = self._rom_path_p
        game.meta = None
        if info.need_fullpath:
            game.data = None
            game.size = 0
        else:
            game.data = ctypes.cast(self._rom_buf, ctypes.c_void_p)
            game.size = len(rom)
        if not self.lib.retro_load_game(ctypes.byref(game)):
            raise RuntimeError(f"{self.core_path.name} refused {self.rom_path.name}")

        av = _AVInfo()
        self.lib.retro_get_system_av_info(ctypes.byref(av))
        self.width = int(av.geometry.base_width) or 256
        self.height = int(av.geometry.base_height) or 240
        self.fps = float(av.timing.fps) or 60.0
        self.library_name = (info.library_name or b"").decode(errors="replace")
        self._closed = False

    def _bind(self) -> None:
        lib = self.lib
        lib.retro_api_version.restype = ctypes.c_uint
        lib.retro_set_environment.argtypes = [_ENV_FUN]
        lib.retro_init.argtypes = []
        lib.retro_deinit.argtypes = []
        lib.retro_set_video_refresh.argtypes = [_VIDEO_FUN]
        lib.retro_set_audio_sample.argtypes = [_AUDIO_SAMPLE_FUN]
        lib.retro_set_audio_sample_batch.argtypes = [_AUDIO_BATCH_FUN]
        lib.retro_set_input_poll.argtypes = [_INPUT_POLL_FUN]
        lib.retro_set_input_state.argtypes = [_INPUT_STATE_FUN]
        lib.retro_get_system_info.argtypes = [ctypes.POINTER(_SystemInfo)]
        lib.retro_get_system_av_info.argtypes = [ctypes.POINTER(_AVInfo)]
        lib.retro_load_game.argtypes = [ctypes.POINTER(_GameInfo)]
        lib.retro_load_game.restype = ctypes.c_bool
        lib.retro_unload_game.argtypes = []
        lib.retro_run.argtypes = []
        lib.retro_reset.argtypes = []
        lib.retro_serialize_size.restype = ctypes.c_size_t
        lib.retro_serialize.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
        lib.retro_serialize.restype = ctypes.c_bool
        lib.retro_unserialize.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
        lib.retro_unserialize.restype = ctypes.c_bool
        lib.retro_get_memory_data.argtypes = [ctypes.c_uint]
        lib.retro_get_memory_data.restype = ctypes.c_void_p
        lib.retro_get_memory_size.argtypes = [ctypes.c_uint]
        lib.retro_get_memory_size.restype = ctypes.c_size_t
        try:
            lib.retro_set_controller_port_device.argtypes = [ctypes.c_uint, ctypes.c_uint]
        except AttributeError:
            pass

    def _environment(self, command: int, data) -> bool:
        try:
            if command == _SET_PIXEL_FORMAT and data:
                fmt = int(ctypes.cast(data, ctypes.POINTER(ctypes.c_int))[0])
                if fmt not in (0, 1, 2):
                    return False
                self.pixel_format = fmt
                return True
            if command == _GET_CAN_DUPE and data:
                ctypes.cast(data, ctypes.POINTER(ctypes.c_bool))[0] = True
                return True
            if command == _GET_SYSTEM_DIRECTORY and data:
                ctypes.cast(data, ctypes.POINTER(ctypes.c_void_p))[0] = ctypes.addressof(self._system_dir)
                return True
            if command == _GET_SAVE_DIRECTORY and data:
                ctypes.cast(data, ctypes.POINTER(ctypes.c_void_p))[0] = ctypes.addressof(self._save_dir)
                return True
            if command == _GET_VARIABLE_UPDATE and data:
                ctypes.cast(data, ctypes.POINTER(ctypes.c_bool))[0] = False
                return True
            if command == _GET_LANGUAGE and data:
                ctypes.cast(data, ctypes.POINTER(ctypes.c_uint))[0] = 0
                return True
            if command in (_SET_VARIABLES, _SET_INPUT_DESCRIPTORS):
                return True
            if command == _SHUTDOWN:
                self.shutdown = True
                return True
        except Exception as exc:
            if os.environ.get("LAB_LIBRETRO_DEBUG"):
                print(f"libretro command {command} failed: {exc}", flush=True)
            return False
        if os.environ.get("LAB_LIBRETRO_DEBUG") and command not in self._seen_commands:
            self._seen_commands.add(command)
            print(f"libretro command {command} not handled", flush=True)
        return False

    def _video(self, data, width: int, height: int, pitch: int) -> None:
        if not data or width == 0 or height == 0 or pitch == 0:
            return
        nbytes = pitch * height
        if nbytes <= 0 or nbytes > 8_000_000:
            return
        raw = ctypes.string_at(data, nbytes)
        rgb = _decode(raw, width, height, pitch, self.pixel_format)
        fitted = np.zeros((self.height, self.width, 3), dtype=np.uint8)
        hh = min(self.height, rgb.shape[0])
        ww = min(self.width, rgb.shape[1])
        fitted[:hh, :ww] = rgb[:hh, :ww]
        self.rgb = fitted

    def _audio_sample(self, _left: int, _right: int) -> None:
        return None

    def _audio_batch(self, _data, frames: int) -> int:
        return frames

    def _poll(self) -> None:
        return None

    def _state(self, port: int, device: int, index: int, ident: int) -> int:
        if port != 0 or device != _DEVICE_JOYPAD or index != 0:
            return 0
        for name, button in self.buttons.items():
            if button == ident and name in self.held:
                return 1
        return 0

    def frame(self, held: set[str]) -> np.ndarray:
        self.held = set(held)
        self.lib.retro_run()
        if self.rgb is None:
            self.rgb = np.zeros((self.height, self.width, 3), dtype=np.uint8)
        return self.rgb

    def ram_bytes(self) -> bytes:
        pointer = self.lib.retro_get_memory_data(_MEMORY_SYSTEM_RAM)
        size = int(self.lib.retro_get_memory_size(_MEMORY_SYSTEM_RAM))
        if not pointer or size <= 0:
            return b""
        return ctypes.string_at(pointer, size)

    def poke(self, address: int, value: int) -> None:
        pointer = self.lib.retro_get_memory_data(_MEMORY_SYSTEM_RAM)
        size = int(self.lib.retro_get_memory_size(_MEMORY_SYSTEM_RAM))
        if not pointer or address < 0 or address >= size:
            return
        ctypes.cast(pointer, ctypes.POINTER(ctypes.c_uint8))[address] = value & 0xFF

    def serialize(self) -> bytes | None:
        size = int(self.lib.retro_serialize_size())
        if size <= 0:
            return None
        buf = ctypes.create_string_buffer(size)
        if not self.lib.retro_serialize(buf, size):
            return None
        return buf.raw

    def unserialize(self, blob: bytes) -> None:
        buf = ctypes.create_string_buffer(blob, len(blob))
        if not self.lib.retro_unserialize(buf, len(blob)):
            raise RuntimeError("core refused the savestate")

    def reset_core(self) -> None:
        self.lib.retro_reset()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self.lib.retro_unload_game()
            self.lib.retro_deinit()
        except Exception:
            pass
