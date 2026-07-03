from __future__ import annotations

import sys

from modnews.cli.main import main


def report_main() -> None:
    sys.argv.insert(1, "report")
    main()


if __name__ == "__main__":
    report_main()
