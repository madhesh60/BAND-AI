"""Main entry point for the coding assistant."""

import sys
from pathlib import Path

from code_assistant.interfaces.cli import cli
from code_assistant.utils.logging import setup_logging


def main():
    """Main entry point."""
    import sys
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stderr.reconfigure(encoding="utf-8")
        except Exception:
            pass

    setup_logging()
    cli(obj={})


if __name__ == "__main__":
    main()