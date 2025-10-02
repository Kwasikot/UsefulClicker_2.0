#!/usr/bin/env python
"""One-shot keyboard layout switcher to English (Windows only).

Runs as a separate short-lived process to perform the switch before
starting the main application (e.g., before Qt initializes).
"""
from __future__ import annotations
import sys
import time

try:
    from .keyboard_layout import ensure_english_layout
except Exception:
    def ensure_english_layout(*args, **kwargs):  # type: ignore
        return


def main(argv: list[str] | None = None) -> int:
    try:
        ensure_english_layout()
        # brief pause to let system apply the layout switch
        time.sleep(0.15)
    except Exception:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

