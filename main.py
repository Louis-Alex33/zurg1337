from __future__ import annotations

import sys

from prospect_machine import main


if __name__ == "__main__":
    argv = sys.argv[1:]
    if argv and argv[0].startswith("-"):
        argv = ["audit", *argv]
    raise SystemExit(main(argv))
