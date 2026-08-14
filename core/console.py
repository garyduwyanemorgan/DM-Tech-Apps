"""Makes command-line output survive a Windows console.

Every tool in this repo prints characters that are not ASCII — em dashes, §,
degree signs, µ, and whatever a DM guideline happens to call a parameter. On
Windows, stdout defaults to the system ANSI codepage (cp1252 here), and writing
one character it cannot encode raises UnicodeEncodeError.

That failure is worse than it sounds, and it is why this module exists rather
than the problem being left to the caller. `scripts/validate_extractions.py` hit
it part-way through the corpus: the process died with exit 1 after printing
forty-three plausible-looking lines, so the run *looked* like a clean report with
few findings. It had actually stopped before two thirds of the files. A tool that
silently under-reports findings is far more dangerous than one that crashes
visibly, and in a compliance product the finding it skips might be the one that
mattered.

`errors="replace"` rather than "strict": a parameter label we cannot render is a
cosmetic problem, and losing the whole report over one character is not a trade
worth making. The underlying data is never touched — this only affects what is
written to a terminal.
"""
from __future__ import annotations

import sys


def use_utf8_stdout() -> None:
    """Force UTF-8 on stdout/stderr. Safe to call more than once, and a no-op
    where the stream does not support reconfiguration (a pipe under some
    runners, or a stream already replaced by a test harness)."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            # Detached, closed, or already wrapped. Not worth failing a whole
            # run over the encoding of its own progress messages.
            pass
