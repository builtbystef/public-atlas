"""What the process holds in memory, for the parse worker's retire threshold and its logs."""

from pathlib import Path


def rss_mb() -> int | None:
    """Resident memory of this process in MB, from `/proc`; None where there is none."""
    try:
        with Path("/proc/self/status").open() as status:
            for line in status:
                if line.startswith("VmRSS"):
                    return int(line.split()[1]) >> 10
    except OSError, ValueError:
        pass
    return None
