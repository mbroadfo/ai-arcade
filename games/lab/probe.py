"""Play a saved button sequence on one restored state.

Each step carries its own frame count. Playback does not assume a training
frame skip. One frame is a legal hold. The adapter decodes the state.
"""
from __future__ import annotations

from games.lab.contract import capabilities_of


class EmulatorProbe:
    """restore() then the buttons. replay([]) is the saved start.

    The adapter must declare savestate support and a describe() decoder.
    note_frame, when the adapter has one, may add signals such as a jump.
    """

    def __init__(self, runner, start_state: bytes, *, adapter, empty_frame: bool = False):
        if not capabilities_of(adapter).get("savestate"):
            raise ValueError("this adapter cannot restore a state")
        describe = getattr(adapter, "describe", None)
        if not callable(describe):
            raise ValueError("this adapter cannot decode a state")
        self.runner = runner
        self.start_state = bytes(start_state)
        self.adapter = adapter
        self.empty_frame = bool(empty_frame)

    def _facts(self, memory: dict) -> tuple[dict, dict]:
        ram = self.runner.ram_bytes()
        facts = dict(self.adapter.describe(ram))
        diagnose = getattr(self.adapter, "diagnose", None)
        diag = diagnose(ram) if callable(diagnose) else {}
        if diag:
            facts["diagnose"] = diag
        note = getattr(self.adapter, "note_frame", None)
        if callable(note):
            memory = note(facts, diag, memory) or memory
        return facts, memory

    def restore(self) -> dict:
        self.runner.unserialize(self.start_state)
        if self.empty_frame:
            self.runner.frame(set())
        facts, _memory = self._facts({})
        return facts

    def replay(self, trajectory) -> dict:
        self.runner.unserialize(self.start_state)
        if self.empty_frame:
            self.runner.frame(set())
        facts, memory = self._facts({})
        for step in trajectory:
            buttons = set(step.get("buttons") or [])
            frames = int(step.get("frames") or 1)
            for _ in range(max(frames, 0)):
                self.runner.frame(buttons)
                facts, memory = self._facts(memory)
                if facts.get("dead") or facts.get("dying"):
                    return facts
        return facts
