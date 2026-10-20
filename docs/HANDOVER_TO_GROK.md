# Handover to Grok: what happened to your branches (20 October 2026)

You were paused after accepting `smb-tiles-v1` (draft PR #5, commit `7460d9d`, generation 145 left paused, no training
run). While you were paused the repository was tidied. **Your work is intact; nothing of yours was rewritten or lost.** This
note says where each branch went, what is still open, and what changed on `main` that you should know before you resume.

## Your branches

| Branch | PR | What happened | Now |
|---|---|---|---|
| `training-lab` | #1 | merged earlier (13 Oct) | **deleted** on the remote and locally |
| `lab/challenge-learning` | #2 | merged earlier (14 Oct) | **deleted** |
| `lab/game-agnostic` | #3 | merged earlier (14 Oct) | **deleted** |
| `lab/objective-reward` | #4 | merged into `main` (`68ff830`) | kept: it also carries #5, see below |
| `lab/tile-observation` | #5 | merged, **but into `lab/objective-reward`, not `main`** | kept until #8 lands |

**The #5 trap.** #5 was stacked on #4, so its base was `lab/objective-reward`. When it was merged (`8d919d8`) it went into that
branch, not into `main`. Your tile observation (`d6dcc59`, `7460d9d`, the `smb-tiles-v1` acceptance) is therefore **not on
`main` yet**. **PR #8** (`lab/objective-reward` to `main`, 3 commits: your two plus the #5 merge commit) brings it there. It
adds nothing of mine. When you stack PRs again, either retarget the upper one to `main` after the lower one merges, or merge
the stack from the top.

## What to do when you resume

1. `git fetch --all --prune`. Your local copies of `training-lab`, `lab/challenge-learning` and `lab/game-agnostic` are gone
   from the remote; delete them locally too (`git branch -d <name>`; they are merged).
2. Once #8 is merged: delete `lab/objective-reward` and `lab/tile-observation` (remote and local), and remove the
   `ai-arcade-objective` worktree. Until then leave them.
3. Start any new work from the current `origin/main`, on a new branch, in its own worktree. One task, one branch, one PR; delete
   the branch and worktree when it merges.
4. `main` is now 42 commits ahead of where your last work started (see below). Rebase or branch fresh; your branches had no
   conflicts with the new files.

## What changed on `main` while you were paused

- **Cabinet controls (PR #6, mine):** the arcade panel (P1/P2 encoders), any USB gamepad, the keyboard and the AI virtual pads
  now coexist. `docs/CABINET_CONTROLS.md` is the plan and the results.
- **AI runs now ignore everything but the AI pads** (`tools/start_pi_game.py`): before this, the panel's encoders took
  joysticks 1 and 2 and the AI's coin and start presses went nowhere. If you start games on the Pi from your tools, use
  that launcher, or hide other pads the same way (`SDL_GAMECONTROLLER_IGNORE_DEVICES_EXCEPT=0x1209/0xa101,0x1209/0xa102`).
- **Per-game controls live in the game's own folder:** `games/<system>/<game>/controls.json` (ROM names it covers, emulator,
  MAME port changes, DIP, RetroArch gamepad changes). The framework names no game and a test enforces that. If your
  game adapters need game-specific controls, put them in the game's folder the same way.
- **README (PR #7):** how to start the arcade day to day (the Pi, the Observatory, the model server).
- Observatory autoplay and the Vanguard findings (`games/arcade/vanguard/`) were already on `main`.

## Standing rules (from the project owner)

- Do not merge without approval; the owner merges. Commit and push on your own branch.
- Do not touch `scripts/` or `infra/`.
- ai-arcade's Ollama is on port 11435; Zork's 11434 must never change.
- The paused Learning Lab (`games/lab/`) is yours; the cabinet work did not touch it.
- S1M makes every decision; code supplies data, tools and execution only (labelled controls excepted).
