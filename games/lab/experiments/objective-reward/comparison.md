# Speed reward comparison

Neither trained policy learned to release A, cross the first pipe, and continue. Completions are 0. Deterministic A-releases are 0 on every evaluated checkpoint and start. The speed run's training high-water of x=1673 is a stochastic training score. Its buttons were not saved, so that score is not a verified crossing. The 16384-decision budget was not extended.

## What was compared

Both runs used PPO/CNN, seed 0, frame skip 4, and the same initialization weights. The parent is the progress champion `20261012T011344Z` seat 0, sha256 `0d31d9fd5ae3cdab1531f72e33938a584e93f7549061e9de49ed26b2a18cf7ec`, loaded with `--bare --init-from`. Bare training skips tapes, hints, and the shared route. The new stamp records the objective that was trained. The parent zip was left in place, with role `initialization`.

| | Progress | smb-1-1-speed |
|---|---:|---:|
| Decisions | 16384 | 16384 |
| Emulator frames | 65536 | 65536 |
| Wall clock | 110.214 s | 110.242 s |
| Device | CPU, CUDA hidden | CPU, CUDA hidden |
| Episodes | 34 | 160 |
| Deaths | 34 | 90 |
| Training score (x high-water) | 899 | 1673 |
| Flag | false | false |
| Exit code | 0 | 0 |

The speed objective ends an episode after 24 decisions with no new progress maximum, so it records more and shorter episodes. About 70 of its 160 episodes ended on that cutoff. The progress objective has no cutoff, so all 34 of its episodes ended in death. The last logged episode is the seat status, not the peak: progress died after 9576 emulator frames with components progress 0, stall 2393, death 256, time 0, total −2649. Speed died after 212 emulator frames with progress 1.880, completion 0, stall 0.500, death 1, time 0.212, total 0.168.

Training reset only from the title. Evaluation used the title, the saved pipe approach (`state.bin`, sha256 `72c3ea8bd337c489e2a0c1adb3253de22457c8617c8162816dfbd25ae014a97e`), and two held-out states that training never reset from. Each checkpoint was rolled out once per start, deterministically, for at most 800 decisions, under both reward formulas. No tape, hint, forced button, or demonstration was applied.

## Deterministic behavior

Initialization, the progress best checkpoint, the speed final checkpoint, and the speed best checkpoint press RIGHT+A+B on every decision. Opening A is held. Releases are 0.

| Start | Max x | Decisions | Frames | End | Past the pipe |
|---|---:|---:|---:|---|---|
| Title (x=40) | 313 | 37 | 148 | death | no |
| Pipe approach (x=197) | 434 | 54 on the speed cutoff, 800 on the progress limit | 216 or 3200 | stall or limit, still alive | no |
| Held-out ground past the pipe (eval start x=508) | 680 | 18 | 72 | death | already past at the start |
| Held-out later (x=594) | 705 | 21 | 84 | death | already past at the start |

Past the pipe means the episode started before x=505 and reached x=505. The two held-out starts are already on the ground beyond that line. Their extra movement is the same held-A run, and it ends in a death. It is not a learned pipe crossing.

The progress final weights diverged. sha256 `855dbe4688bd93bb909571bf0867df99d5c86cef1c9cd819499a4cfafe1bddee`. Every decision is LEFT+B, and A is never pressed. From the title, x stays 40. From the pipe approach, x reaches 223. From the later held-out state, x stays 594.

| Checkpoint | sha256 | Deterministic action |
|---|---|---|
| Initialization | `0d31d9fd5ae3cdab1531f72e33938a584e93f7549061e9de49ed26b2a18cf7ec` | RIGHT+A+B |
| Progress best | `046ffd5b98a9dc2d1b27ee1b1739bcfbd230640f85a30fab832a43014317a185` | RIGHT+A+B |
| Progress final | `855dbe4688bd93bb909571bf0867df99d5c86cef1c9cd819499a4cfafe1bddee` | LEFT+B |
| Speed final | `26c565c4959d727a13a6bf3794c0b3ad528f5faab8abd75f1ec5a2c5d20a4b6a` | RIGHT+A+B |
| Speed best | `6b790b5935f53f50b72c6999e96bcabe7a6c07c6f0545ddc21dd6ae5cd1a2155` | RIGHT+A+B |

Speed final and speed best differ as weight files. Their deterministic argmax matches the parent on all four starts. World 1-1 completion is 0. Independent success at releasing A and crossing the pipe is 0.

The speed formula on the title death totals 0.923, matching the calibration row. On the pipe stall it totals 0.370 (progress 1.836, stall 1.250, death 0, time 0.216) across 54 decisions. The worker named a `best.tape.json` for each seat. Neither file is on disk, so the buttons of the x=1673 training life were not recovered.

## Ranking and provenance

A verified World 1-1 completion outranks every failure. Among successes, fewer emulator frames wins. Among failures, greater verified progress is diagnostic only. None of these checkpoints completed the level, so none is a speedrun champion. `promoted_parent` on the speed protocol skips a failed evaluation. These runs were not submitted to it.

Copies of the four trained zips sit under `mario-runs/artifacts/smb-1-1-speed-ab/` and stay out of git. The historical champion, its stamp, its tape, and `results.json` were not rewritten. Generation 145 was not resumed.

## Separate measurements

`calibration.md` locks the reward magnitudes that were computed from the Gate A traces before this training. A constructed World 1-1 clear scores above a pipe stall and above an early death. `action-edge.md` records that the 84×84 image and the 9-float vector are identical when A is held and when it is released at the pipe. Four raw RAM bytes carry the button bit. They were not added to the observation. The 12-action set is unchanged.

`smb-points`, enemy kills, question blocks, shortcuts, and neuroevolution were not started.
