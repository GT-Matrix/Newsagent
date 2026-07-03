"""Compatibility entry point for the legacy report CLI."""

from modnews.cli.commands.report_entry import report_main


def main() -> None:
    report_main()


if __name__ == "__main__":
    main()

