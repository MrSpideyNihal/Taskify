"""Main entry point for running Taskify as a module."""

import sys

from taskify.cli.main import main

if __name__ == "__main__":
    # Ensure correct status code on exit
    sys.exit(main())
