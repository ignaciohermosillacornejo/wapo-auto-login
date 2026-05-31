import shutil
from pathlib import Path


def format_log_line(*, timestamp: str, status: str, kind: str, detail: str) -> str:
    """Return one tab-separated log line. Reject tabs inside `detail` to keep TSV parseable."""
    if "\t" in detail:
        raise ValueError("detail must not contain tabs")
    return f"{timestamp}\t{status}\t{kind}\t{detail}"


def rotate_debug(debug_dir: Path, *, keep: int) -> None:
    """Delete oldest timestamped subdirs of `debug_dir`, keeping the `keep` most recent.

    Subdirs are sorted lexicographically by name — our timestamp format (ISO-8601 with
    `-` instead of `:`) sorts the same as chronologically, so lexicographic == newest-first.
    """
    subdirs = sorted(
        (p for p in debug_dir.iterdir() if p.is_dir()),
        key=lambda p: p.name,
    )
    to_delete = subdirs[:-keep] if keep > 0 else subdirs
    for p in to_delete:
        shutil.rmtree(p)
