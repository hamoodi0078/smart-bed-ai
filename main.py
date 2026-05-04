"""Thin launcher — delegates startup to app_entry.main().

All module functionality is accessed via explicit imports in each file.
No global namespace pollution.
"""

from __future__ import annotations


def _run() -> None:
    from app_entry import main
    main()


if __name__ == "__main__":
    _run()
