"""Play a saved button sequence on one restored emulator state.

Each step carries its own frame count. Playback does not assume the training
frame skip of 4. One frame is a legal hold.
"""
from __future__ import annotations


class EmulatorProbe:
    """restore() then the buttons. replay([]) is the saved start."""

    def __init__(self, runner, start_state: bytes, *, empty_frame: bool = False):
        self.runner = runner
        self.start_state = bytes(start_state)
        self.empty_frame = bool(empty_frame)

    def restore(self) -> dict:
        from games.lab.integrations.smb_1_1 import describe, diagnose
        self.runner.unserialize(self.start_state)
        if self.empty_frame:
            self.runner.frame(set())
        ram = self.runner.ram_bytes()
        facts = describe(ram)
        facts["diagnose"] = diagnose(ram)
        facts["saw_jump"] = False
        return facts

    def replay(self, trajectory) -> dict:
        from games.lab.integrations.smb_1_1 import describe, diagnose
        facts = self.restore()
        start_y = int(facts.get("y_pos") or 0)
        saw_jump = False
        for step in trajectory:
            buttons = set(step.get("buttons") or [])
            frames = int(step.get("frames") or 1)
            for _ in range(max(frames, 0)):
                self.runner.frame(buttons)
                ram = self.runner.ram_bytes()
                facts = describe(ram)
                diag = diagnose(ram)
                if int(diag.get("y_speed") or 0) < 0 or int(facts.get("y_pos") or 0) > start_y + 2:
                    saw_jump = True
                if facts.get("dead") or facts.get("dying"):
                    facts["diagnose"] = diag
                    facts["saw_jump"] = saw_jump
                    return facts
        ram = self.runner.ram_bytes()
        facts = describe(ram)
        facts["diagnose"] = diagnose(ram)
        facts["saw_jump"] = saw_jump
        return facts
