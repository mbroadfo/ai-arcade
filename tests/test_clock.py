"""The fixed-rate clock, on a fake clock: ticks on time, sleeping only until the next one is due, no catch-up burst."""
from arcadekit.clock import TickClock


class FakeTime:
    def __init__(self):
        self.now, self.slept = 100.0, []

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.slept.append(seconds)
        self.now += seconds


def test_ticks_come_every_period_and_sleep_only_the_remainder():
    t = FakeTime()
    clock = TickClock(10, clock=t, sleep=t.sleep)
    first = clock.wait()
    t.now += 0.03  # 30 ms of work
    clock.done(first)
    second = clock.wait()
    assert abs(second.interval - 0.1) < 1e-9 and abs(t.slept[-1] - 0.07) < 1e-9 and second.late_ms < 1e-6
    assert abs(first.work_ms - 30.0) < 1e-6


def test_an_overrun_is_counted_and_not_made_up_with_a_burst():
    t = FakeTime()
    clock = TickClock(10, clock=t, sleep=t.sleep)
    tick = clock.wait()
    t.now += 0.35  # work took three and a half periods
    clock.done(tick)
    late = clock.wait()
    assert clock.overruns == 1 and clock.skipped == 2 and abs(late.late_ms - 50) < 1e-6
    t.now += 0.01
    after = clock.wait()  # the next tick is a full period after the late one's slot, not at once
    assert abs(after.began - late.due - 0.1) < 1e-9
    s = clock.summary()
    assert s["ticks"] == 3 and s["skipped"] == 2 and s["overruns"] == 1
