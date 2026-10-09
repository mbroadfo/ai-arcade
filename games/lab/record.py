"""Save a life as a GIF. The gym plays the life that went furthest, not a replay of the final weights."""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import numpy as np


def _base_gym(vec):
    while hasattr(vec, "venv"):
        vec = vec.venv
    return vec.envs[0]


def _ffmpeg(width: int, height: int, dest: Path) -> subprocess.Popen | None:
    if shutil.which("ffmpeg") is None:
        return None
    return subprocess.Popen(
        [
            "ffmpeg", "-y", "-loglevel", "error",
            "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{width}x{height}", "-r", "60",
            "-i", "-", "-an",
            "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "23", str(dest),
        ],
        stdin=subprocess.PIPE,
    )


def save_gif(frames: list, dest: Path, stride: int = 1) -> None:
    """Write one looping GIF. `stride` is how many agent steps passed between frames."""
    from PIL import Image

    if not frames:
        raise ValueError("no frames")
    images = [Image.fromarray(frame) for frame in frames]
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    images[0].save(
        tmp,
        format="GIF",
        save_all=True,
        append_images=images[1:],
        duration=max(67, 67 * int(stride)),
        loop=0,
    )
    os.replace(tmp, dest)


def record_episode(model_id: str, checkpoint: Path, system: str, rom: Path, integration, dest_dir: Path,
                   max_steps: int = 2000) -> Path:
    from games.lab.env import make_env
    from games.lab.models import registry

    env = make_env(system, rom, integration)
    model = registry.load(model_id, str(checkpoint), env)
    vec = model.get_env()
    gym_env = _base_gym(vec)
    width, height = gym_env.unwrapped.runner.width, gym_env.unwrapped.runner.height
    mp4 = dest_dir / "best.mp4"
    process = _ffmpeg(width, height, mp4)
    gif_frames: list[bytes] = []

    if process is not None:
        gym_env.unwrapped.record_sink = process.stdin
    else:
        class _Gif:
            def __init__(self):
                self.n = 0

            def write(self, data: bytes) -> None:
                self.n += 1
                if self.n % 4 == 0 and len(gif_frames) < 600:
                    gif_frames.append(data)

        gym_env.unwrapped.record_sink = _Gif()

    try:
        obs = vec.reset()
        state = None
        starts = np.ones((vec.num_envs,), dtype=bool)
        for _ in range(max_steps):
            action, state = model.predict(obs, state=state, episode_start=starts, deterministic=True)
            obs, _rewards, dones, _infos = vec.step(action)
            starts = np.asarray(dones, dtype=bool)
            if bool(dones[0]):
                break
    finally:
        gym_env.unwrapped.record_sink = None
        env.close()
        if process is not None and process.stdin is not None:
            process.stdin.close()
            code = process.wait(timeout=120)
            if code != 0:
                raise RuntimeError(f"ffmpeg exited {code}")

    if process is not None:
        return mp4

    from PIL import Image
    gif = dest_dir / "best.gif"
    if not gif_frames:
        raise RuntimeError("the episode produced no frames")
    images = [Image.frombytes("RGB", (width, height), frame) for frame in gif_frames]
    images[0].save(gif, save_all=True, append_images=images[1:], duration=67, loop=0)
    return gif
