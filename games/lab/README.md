# Training lab

Six seats, one game from the cabinet, one model per seat. Training runs on this PC.
The page opens on six different learners: pixel PPO, an LSTM, DQN, RAM PPO, a
high-entropy pixel PPO, and a low-entropy pixel PPO. Each one keeps its own parent.
The Pi is only where the ROMs already are.

This package is not an arcadekit game. Pac-Man's deciders, the controller broker, and the
Observatory on port 8780 are unchanged. The lab page is http://localhost:8790/.

## Setup (Windows)

Cores, ROMs, and runs go under `%USERPROFILE%\mario-lab` and `%USERPROFILE%\mario-runs`,
not in this repository. The working interpreter is Python 3.12 in that venv.
Start the server with it. Child seats inherit `sys.executable`.

```powershell
cd C:\Users\Mike\Documents\Code\ai-arcade
uv venv --python 3.12 C:\Users\Mike\mario-lab\venv
uv pip install --python C:\Users\Mike\mario-lab\venv\Scripts\python.exe -r games/lab/requirements.txt
uv pip install --python C:\Users\Mike\mario-lab\venv\Scripts\python.exe --reinstall-package torch torch --index-url https://download.pytorch.org/whl/cu130
```

The CUDA reinstall is last on purpose. Installing the requirements afterward pulls
the CPU wheel of torch from PyPI and `torch.cuda.is_available()` comes back false.

`C:\Users\Mike\mario-lab\venv\Scripts\python.exe -m games.lab.smoke` boots Super Mario Bros.
for 1,000 steps. The same interpreter with `-m games.lab.server` serves the page.

Each seat writes a GIF of the life that went furthest (`best.gif`) and the weights
from that moment (`best.zip`). After the round the page plays those six lives.
The latest checkpoint is a different file. It is the final policy, and for Mario
that policy can walk left even when an earlier life went a long way right.

A round's default budget is 200,000 steps per seat. The page can set a smaller one.
Super Mario Bros. scores progress through the game. Clearing 1-1 continues into 1-2,
and a higher progress score is the parent of the next round for that model. Weights
from the old seven-button 1-1 score are not loaded. Training also pays more for the
same ground while the clock is high, and a step that gains nothing while Mario is
alive costs a small demerit. The six seats share the button run of a life once that run reaches the score
the generation started from. A shorter run is left alone. Each new life plays
that run and then goes on, so a clear of 1-1 is repeated and that life can
continue into 1-2. A higher score replaces the shared run, and so does a faster
pass of the same ground. Every eighth life plays its own buttons, so a shortcut
can replace the slower run. Clicking a seat
opens that seat's own best run in a separate window, at full game speed, in
its own game. The page also draws each network and can store a hint for a
later route, such as a warp. A hint with no buttons is only a note.
Bootable games (anything NES or Atari 2600 without a scored integration) rank by steps
survived. That is not the same as beating the game. Arcade, 32X, ports, TRS-80, and Zork
are listed and cannot be started.

PPO / RAM is only offered on a scored game. Super Mario Bros. is the first one.

## Docker

The same page can run as one Linux container on this PC's GPU. The repo, the lab
home (ROM and cores), and the runs folder are mounted in, so the weights stay on
the Windows disks. The container reuses `mario-lab\roms\smb.nes` when that file
is the pinned World ROM. A Linux core is downloaded beside the Windows DLL the
first time a seat starts.

From `games/lab`:

```powershell
docker compose build
docker compose up -d
docker compose stop
docker compose start
```

`docker compose stop` stops the page and every seat the page started. Port 8790
stays http://localhost:8790/. Bring the container up only when the Windows
training processes are finished. Two copies would share the GPU and the runs folder.
