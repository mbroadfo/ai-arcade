# Speed reward calibration

Computed before the comparison training. The magnitudes below are what `smb-1-1-speed` pays. The progress objective's numbers are unchanged.

## Formula

One decision is 4 emulator frames. Distance uses the new maximum x, divided by 256, multiplied by `1 + time_left / 400`, and capped at 1.0. The other terms are:

| Term | Amount |
|---|---|
| World 1-1 flag, once | +5 |
| Death | −1 |
| Decision with no new maximum, while alive | −0.05 |
| Every emulator frame | −0.001 |

A decision therefore costs 0.004 in time even while Mario is moving. Twenty-four decisions with no new maximum end the episode. That cutoff is 0 on the progress objective. The World 1-2 rising platform (`smb-1-2-ceiling-lift`) sets its own cutoff at 64 decisions, because that challenge waits on purpose.

## Episodes

The goomba death is the Gate A title trace: 37 decisions, death at x=313. The pipe episode follows that trace through x=308, then the traced 10-pixel running pace to x=434, then 24 stationary decisions. The further episode continues 300 pixels past the pipe at that same pace. x=458 is on top of the pipe, so it is not counted as clearing it. The two clears are constructed. No saved policy has finished World 1-1 unassisted. The slow clear splits each brisk gain across two decisions.

| Episode | Progress | Completion | Stall | Death | Time | Total | Final x |
|---|---:|---:|---:|---:|---:|---:|---:|
| Die at the first goomba | 2.121 | 0 | 0.050 | 1 | 0.148 | 0.923 | 313 |
| Reach the pipe and stall | 3.057 | 0 | 1.250 | 0 | 0.292 | 1.515 | 434 |
| Cross the pipe and gain 300 pixels | 5.368 | 0 | 0.050 | 0 | 0.316 | 5.002 | 734 |
| Die one step short of the flag | 23.501 | 0 | 0.050 | 1 | 1.288 | 21.163 | 3158 |
| Clear World 1-1, half pace | 22.699 | 5 | 0.050 | 0 | 2.564 | 25.085 | 3161 |
| Clear World 1-1, traced pace | 23.523 | 5 | 0.050 | 0 | 1.288 | 27.185 | 3161 |

The stall on the pipe row is 25 decisions: the traced opening step also gains nothing, and then the pipe stands still for 24. A slow clear outranks a brisk death at the flag. A brisk clear outranks the slow clear. Either clear is more than three times the pipe stall and more than three times the goomba death. The largest single distance term is 1.0. The completion bonus is 5, not a million-point fitness term.

`games/lab/tests/test_objective.py` recomputes this table from the formula and fails if the totals move.
