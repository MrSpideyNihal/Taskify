"""Programmatic execution of PyInstaller builds for standalone executables."""

import os
import subprocess
import sys
from pathlib import Path


def main() -> None:
    """Execute the PyInstaller command pointing to packaging spec file."""
    workspace_dir = Path(__file__).parent.parent.resolve()
    spec_file = workspace_dir / "packaging" / "taskify.spec"

    if not spec_file.exists():
        print(f"Error: Specification file not found at: {spec_file}", file=sys.stderr)
        sys.exit(1)

    print("=== Taskify Packaging Builder ===")
    print(f"Targeting Specification: {spec_file}")
    print(f"Working Directory: {workspace_dir}")

    # Build the PyInstaller command list
    cmd = [
        "pyinstaller",
        "--clean",
        "--noconfirm",
        "--distpath",
        str(workspace_dir / "dist"),
        "--workpath",
        str(workspace_dir / "build"),
        str(spec_file),
    ]

    print(f"Executing: {' '.join(cmd)}")
    try:
        # Run pyinstaller build process
        result = subprocess.run(
            cmd, cwd=str(workspace_dir), check=True, capture_output=False
        )
        print("=== Build process finished successfully. ===")
        sys.exit(result.returncode)
    except subprocess.CalledProcessError as e:
        print(f"Error: PyInstaller build failed with status {e.returncode}", file=sys.stderr)
        sys.exit(e.returncode)
    except FileNotFoundError:
        print(
            "Error: PyInstaller command not found. Please install the dev packages: "
            "pip install -e .[dev]",
            file=sys.stderr,
        )
        sys.exit(127)


if __name__ == "__main__":
    main()
