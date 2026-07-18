# Taskify standalone packaging instructions

This directory holds the specifications and tooling to bundle the Python codebase, CustomTkinter frontend styling, and dependency components into a single standalone binary.

## Requirements

Ensure development dependencies are installed:
```bash
pip install -e .[dev]
```

## Building stand-alone executables

To compile the binary for your active platform:

```bash
python packaging/build.py
```

Or run via the Makefile:
```bash
make dist
```

Upon success, PyInstaller generates output directories:
- `build/`: Temporary files generated during build time.
- `dist/`: Stands for distribution. Contains the single executable `taskify` (or `taskify.exe` on Windows).

## Local model dependency setup

Because Taskify is a fully offline application, speech-to-text models must be available locally. The compiled binary does not include model directories by default to save executable file footprint.

If model directories are missing, the application downloads defaults to the user directory on first launch, or they can be downloaded manually via:

```bash
# Download default Vosk english model
dist/taskify download-model --engine vosk

# Download default Whisper model
dist/taskify download-model --engine whisper
```

Offline models are stored at:
- **Vosk:** `~/.local/share/taskify/models/vosk/` (on Windows `~` refers to `C:\Users\<username>`)
- **Whisper:** standard cache path managed by `huggingface_hub`.
