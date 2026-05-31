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
