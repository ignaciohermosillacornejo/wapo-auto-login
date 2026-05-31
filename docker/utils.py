def format_log_line(*, timestamp: str, status: str, kind: str, detail: str) -> str:
    """Return one tab-separated log line. Reject tabs inside `detail` to keep TSV parseable."""
    if "\t" in detail:
        raise ValueError("detail must not contain tabs")
    return f"{timestamp}\t{status}\t{kind}\t{detail}"
