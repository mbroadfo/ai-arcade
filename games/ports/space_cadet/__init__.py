"""3D Pinball for Windows - Space Cadet, played by the S1M model (see README.md).

The Observatory's AI setup reads this package like any game's: LAB says what can be run, lab_policies() the players, lab_main()
starts a run. The game is not a MAME game: it runs headless on the cabinet Pi (bridge/), so `own_screen` tells the Observatory
not to start MAME for it, and the run sends its own picture (observe.py).
"""

LAB = {"ai_player": True, "own_screen": True, "cabinet_screen": True,
       "ai_modes": [
           {"value": "model", "policy": "model", "model": "nimble", "label": "AI plays (thinking time)",
            "help": "The model chooses the flippers, nudges and plunger pull every 80 ms of game time; the game waits for each "
                    "answer, so the model's speed costs the game nothing. The picture is drawn from the game's state."}],
       "ai_help": "S1M plays: every window of game time the model chooses which flippers are up, or a nudge; the code only "
                  "describes the table and presses what was chosen. Every decision says whose it was.",
       "default_policy": "reflex", "default_hz": 12.5, "hz_range": (2, 50)}

LAB_GROUPS = ("Controls (code)",)
LAB_MEASURES = ["Score", "Balls lost", "Game time", "Decisions by source"]


def lab_policies():
    return [{"value": "reflex", "label": "reflex", "group": "Controls (code)", "tag": "control",
             "help": "Flips a flipper while the ball is in its reach, lets it down after three windows.",
             "purpose": "The comparison for any model's play.", "limitation": "Plain code, never reported as AI play."},
            {"value": "idle", "label": "idle", "group": "Controls (code)", "tag": "control",
             "help": "Never touches a flipper; launches the ball.", "purpose": "The floor: what a launch alone scores.",
             "limitation": "Plain code, never reported as AI play."}]


def lab_main(argv):
    """Run one game with these arguments (tools/run_lab.py)."""
    from .run import main
    return main(argv)
