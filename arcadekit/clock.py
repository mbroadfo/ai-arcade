"""A fixed-rate clock for games decided on a beat instead of at events. Timing only: it never sees the game.

    clock = TickClock(hz=10)
    while running:
        tick = clock.wait()      # sleeps until the next tick is due
        ...observe, decide, act...
        clock.done(tick)         # how long the work took, against the tick's budget

Each Tick says when it was due, when it began, the interval since the previous one and how late it began. A tick
whose work overruns the budget is not made up with a burst: the next one is due a full interval after the overrun,
and the ticks that never ran are counted as `skipped`. summary() gives what a run needs to judge its timing.
"""
import time
from dataclasses import dataclass


@dataclass
class Tick:
    index: int
    due: float  # when it was scheduled (clock seconds)
    began: float  # when wait() returned
    interval: float  # since the previous tick began (0 for the first)
    late_ms: float  # began - due
    work_ms: float | None = None  # set by done()


def _quantile(values, q):
    return sorted(values)[int(q * (len(values) - 1))] if values else None


class TickClock:
    def __init__(self, hz, clock=time.monotonic, sleep=time.sleep):
        if hz <= 0:
            raise ValueError("hz must be positive")
        self.hz, self.period, self.clock, self.sleep = hz, 1.0 / hz, clock, sleep
        self.next_due, self.index, self.previous = None, 0, None
        self.intervals, self.lates, self.works, self.skipped, self.overruns = [], [], [], 0, 0

    def wait(self):
        now = self.clock()
        if self.next_due is None:
            self.next_due = now
        if now < self.next_due:
            self.sleep(self.next_due - now)
            now = self.clock()
        missed = int((now - self.next_due) // self.period)
        if missed > 0:  # the work overran by whole periods: do not burst to catch up
            self.skipped += missed
            self.next_due += missed * self.period
        tick = Tick(self.index, self.next_due, now, 0.0 if self.previous is None else now - self.previous,
                    (now - self.next_due) * 1000)
        if self.previous is not None:
            self.intervals.append(tick.interval)
        self.lates.append(tick.late_ms)
        self.previous, self.index = now, self.index + 1
        self.next_due += self.period
        return tick

    def done(self, tick):
        tick.work_ms = (self.clock() - tick.began) * 1000
        self.works.append(tick.work_ms)
        if tick.work_ms > self.period * 1000:
            self.overruns += 1
        return tick.work_ms

    def summary(self):
        ms = [i * 1000 for i in self.intervals]
        return {"hz": self.hz, "ticks": self.index, "skipped": self.skipped, "overruns": self.overruns,
                "interval_ms_p50": _quantile(ms, 0.5), "interval_ms_p90": _quantile(ms, 0.9),
                "interval_ms_max": max(ms) if ms else None,
                "late_ms_p50": _quantile(self.lates, 0.5), "late_ms_p90": _quantile(self.lates, 0.9),
                "work_ms_p50": _quantile(self.works, 0.5), "work_ms_p90": _quantile(self.works, 0.9)}
