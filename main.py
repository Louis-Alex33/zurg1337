from __future__ import annotations

import sys

from prospect_machine import main


if __name__ == "__main__":
    argv = sys.argv[1:]
    if "--report-type" in argv:
        index = argv.index("--report-type")
        if index + 1 < len(argv) and argv[index + 1] == "gsc":
            argv = [item for pos, item in enumerate(argv) if pos not in {index, index + 1}]
            argv = ["gsc", *argv]
    if argv and argv[0].startswith("-"):
        argv = ["audit", *argv]
    raise SystemExit(main(argv))
