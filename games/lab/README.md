# Training lab

Six seats, one game from the cabinet, one model per seat. Training runs on this PC.
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
Bootable games (anything NES or Atari 2600 without a scored integration) rank by steps
survived. That is not the same as beating the game. Arcade, 32X, ports, TRS-80, and Zork
are listed and cannot be started.

PPO / RAM is only offered on a scored game. Super Mario Bros. World 1-1 is the first one.
