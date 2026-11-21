"""run.py's last resort for a freeze (frozen_dump): faulthandler's own timer writes where every thread is when Python is
stuck as a whole, unless the watchdog keeps pushing it back or cancels it."""
import time

import run


def _written(f) -> str:
    f.flush()
    f.seek(0)
    return f.read()


def test_the_freeze_dump_says_where_every_thread_is_unless_pushed_back(tmp_path):
    with (tmp_path / "log.txt").open("w+", encoding="utf-8") as f:
        try:
            assert run.frozen_dump(True, False, file=f, after=0.2)
            time.sleep(0.8)  # nobody pushes it back, as when Python is frozen
            text = _written(f)
        finally:
            run.frozen_dump(False, True)
    assert "most recent call first" in text and "test_watchdog.py" in text


def test_pushing_the_freeze_dump_back_keeps_it_quiet(tmp_path):
    with (tmp_path / "log.txt").open("w+", encoding="utf-8") as f:
        armed = False
        try:
            for _ in range(8):  # the watchdog, while the video loop goes round
                armed = run.frozen_dump(True, armed, file=f, after=0.3)
                time.sleep(0.1)
        finally:
            assert not run.frozen_dump(False, armed)  # the loop stuck (the watchdog speaks) or the session ended
        time.sleep(0.5)
        assert _written(f) == ""


def test_a_freeze_dump_never_armed_isnt_cancelled():
    assert not run.frozen_dump(False, False)


def test_the_watchdog_speaks_before_windows_calls_the_window_not_responding():
    assert run.WATCHDOG_S < 5.0 and run.FROZEN_S < 5.0  # Windows: "not responding" after 5 s without messages
    assert run.STARVED_S > run.WATCHDOG_S  # a stream stall alone isn't a freeze: it gets longer
