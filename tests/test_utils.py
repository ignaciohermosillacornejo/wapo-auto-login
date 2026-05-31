import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "docker"))

from utils import format_log_line


def test_format_log_line_ok():
    line = format_log_line(
        timestamp="2026-05-30T04:17:33Z",
        status="ok",
        kind="skip-still-active",
        detail="probe=200 selector=active-badge",
    )
    assert line == (
        "2026-05-30T04:17:33Z\tok\tskip-still-active\tprobe=200 selector=active-badge"
    )


def test_format_log_line_fail_with_debug():
    line = format_log_line(
        timestamp="2026-06-07T04:09:50Z",
        status="fail",
        kind="spl-login-timeout",
        detail="debug=/debug/2026-06-07T04-09-50/",
    )
    assert line == (
        "2026-06-07T04:09:50Z\tfail\tspl-login-timeout\tdebug=/debug/2026-06-07T04-09-50/"
    )


def test_format_log_line_rejects_tab_in_detail():
    # Tabs in detail would break TSV parsing — reject at the boundary.
    import pytest
    with pytest.raises(ValueError):
        format_log_line(
            timestamp="2026-05-30T04:17:33Z",
            status="ok",
            kind="reauth-success",
            detail="duration=23s\tunexpected",
        )


def test_rotate_debug_keeps_n_most_recent(tmp_path):
    from utils import rotate_debug

    # Create 7 timestamped subdirs; rotate to keep 5.
    for ts in ["2026-01-01T00-00-00", "2026-01-02T00-00-00", "2026-01-03T00-00-00",
               "2026-01-04T00-00-00", "2026-01-05T00-00-00", "2026-01-06T00-00-00",
               "2026-01-07T00-00-00"]:
        (tmp_path / ts).mkdir()

    rotate_debug(tmp_path, keep=5)

    remaining = sorted(p.name for p in tmp_path.iterdir())
    assert remaining == [
        "2026-01-03T00-00-00",
        "2026-01-04T00-00-00",
        "2026-01-05T00-00-00",
        "2026-01-06T00-00-00",
        "2026-01-07T00-00-00",
    ]


def test_rotate_debug_noop_when_under_limit(tmp_path):
    from utils import rotate_debug
    (tmp_path / "2026-01-01T00-00-00").mkdir()
    (tmp_path / "2026-01-02T00-00-00").mkdir()
    rotate_debug(tmp_path, keep=5)
    assert len(list(tmp_path.iterdir())) == 2


def test_rotate_debug_ignores_non_directories(tmp_path):
    from utils import rotate_debug
    (tmp_path / "2026-01-01T00-00-00").mkdir()
    (tmp_path / "stray.txt").write_text("ignore me")
    rotate_debug(tmp_path, keep=1)
    assert (tmp_path / "stray.txt").exists()
