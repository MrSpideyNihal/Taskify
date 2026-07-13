# Taskify

**A fully offline, privacy-first, voice-driven personal task management application.**

Taskify captures spoken input via your microphone, transcribes it locally, and automatically
extracts and classifies actionable tasks into the Eisenhower Matrix — all without sending a single
byte of data outside your device.

---

## Table of Contents

1. [About](#about)
2. [Features](#features)
3. [Privacy](#privacy)
4. [Requirements](#requirements)
5. [Installation](#installation)
6. [Model Downloads](#model-downloads)
7. [Usage](#usage)
8. [Configuration](#configuration)
9. [Architecture Overview](#architecture-overview)
10. [Contributing](#contributing)
11. [Roadmap](#roadmap)
12. [License](#license)

---

## About

Modern task management tools demand an internet connection, a subscription, and trust in a
third-party cloud. Taskify is built on the opposite premise: your voice, your hardware, your
data — nothing else.

Speak naturally while working, thinking, or planning. Taskify listens, transcribes in near
real-time, and periodically runs a local AI pipeline to extract discrete tasks from the transcript.
Each task is automatically placed in one of the four Eisenhower Matrix quadrants:

| Quadrant | Description |
|---|---|
| Urgent and Important | Do immediately |
| Important but Not Urgent | Schedule it |
| Urgent but Not Important | Delegate or batch |
| Neither Urgent Nor Important | Eliminate or defer |

The application is designed for mid-range consumer hardware (Intel Core i5 / 8 GB RAM or
equivalent). It anticipates future Android deployment and is architected to swap in lightweight
components with minimal code changes.

---

## Features

- **100% offline operation** after initial model downloads.
- **Voice capture** via system microphone with energy-based silence detection.
- **Multilingual speech-to-text** using Vosk (primary) and faster-whisper (fallback).
- **Local AI task extraction** via Ollama (Phi-4-mini, Gemma 3 2B, Qwen2.5 quantized) or
  spaCy/rule-based NLP when a GPU/LLM is unavailable.
- **Eisenhower Matrix dashboard** with drag-and-drop quadrant management.
- **Automatic daily logs** saved as Markdown and JSON (human-readable, version-control-friendly).
- **SQLite persistence** — no hidden databases, no external servers.
- **Configurable extraction interval** (default: every 5 minutes).
- **Cross-platform** — Windows 10+, macOS 12+, Linux (Ubuntu 22.04+ tested).
- **PyInstaller distribution** — single executable, no Python installation required for end users.

---

## Privacy

**Taskify is a privacy-first application. The following statements are guarantees, not
marketing language:**

- No network requests are made after initial model downloads. The application contains no
  telemetry, analytics, crash reporting, or update checks that contact external servers.
- All speech audio is processed in memory on your local CPU. No audio is written to disk
  unless you explicitly enable debug logging.
- All transcripts and extracted tasks are stored exclusively in your local SQLite database and
  log files, located at paths you control (see Configuration).
- The Ollama LLM integration communicates only with a process running on `localhost`. No
  cloud API key is required or accepted.
- The source code is fully auditable. You are encouraged to review
  `src/taskify/audio/`, `src/taskify/stt/`, and `src/taskify/llm/` to verify these claims.

**Data locations:**

| Data Type | Default Location |
|---|---|
| Database | `~/.local/share/taskify/taskify.db` |
| Daily transcripts | `~/.local/share/taskify/logs/YYYY-MM-DD.md` and `.json` |
| Application log | `~/.local/share/taskify/app.log` |
| Downloaded models | `~/.local/share/taskify/models/` |
| User configuration | `~/.config/taskify/config.toml` |

To delete all application data, remove the directories listed above.

---

## Requirements

**Runtime:**

- Python 3.11 or higher
- A working microphone
- 4 GB RAM minimum (8 GB recommended when running a local LLM)
- Approximately 1–4 GB free disk space for models, depending on selections

**Optional (for LLM-based task extraction):**

- [Ollama](https://ollama.com) installed and running locally
- One of the supported models pulled: `phi4-mini`, `gemma3:2b`, `qwen2.5:1.5b`

---

## Installation

### From Source (Recommended for Development)

```bash
# Clone the repository
git clone https://github.com/MrSpideyNihal/Taskify.git
cd Taskify

# Create and activate a virtual environment
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate

# Install the package with all dependencies
pip install -e ".[dev]"
```

### Minimal Install (Core Only, No LLM)

```bash
pip install -e ".[nlp]"
```

### From a Pre-built Executable

Pre-built executables are available on the [Releases](https://github.com/MrSpideyNihal/Taskify/releases)
page for Windows, macOS, and Linux. Download the archive for your platform, extract it, and run
the `taskify` executable. No Python installation is required.

---

## Model Downloads

Taskify does not bundle speech or language models. They are downloaded once on first run
(or manually) and stored locally.

### Vosk Speech-to-Text Models

Vosk models are available from [alphacephei.com/vosk/models](https://alphacephei.com/vosk/models).
The application will prompt you to download a model on first launch if none is found.

To download manually:

```bash
# English (small, ~50 MB) — recommended for most users
python -m taskify download-model --engine vosk --lang en --size small

# English (large, ~1.8 GB) — higher accuracy
python -m taskify download-model --engine vosk --lang en --size large
```

Supported language codes follow the Vosk model naming convention (`en`, `de`, `fr`, `es`, `zh`,
`hi`, and others). See `docs/model_download.md` for the full list.

### faster-whisper Models

```bash
python -m taskify download-model --engine whisper --model tiny
python -m taskify download-model --engine whisper --model base
python -m taskify download-model --engine whisper --model small
```

### Ollama Language Models (Optional)

Install [Ollama](https://ollama.com/download) and pull a supported model:

```bash
ollama pull phi4-mini
# or
ollama pull gemma3:2b
# or
ollama pull qwen2.5:1.5b
```

If Ollama is not running, Taskify falls back automatically to the NLP backend.

---

## Usage

### Launch the GUI

```bash
taskify
# or
python -m taskify
```

### Quick Start

1. Launch Taskify.
2. Select your microphone in **Settings** if the default device is incorrect.
3. Click **Start Recording**.
4. Speak naturally. The live transcript preview updates in real time.
5. Click **Stop Recording** when finished.
6. Task extraction runs automatically (or immediately via the **Extract Now** button).
7. Extracted tasks appear in the Eisenhower Matrix dashboard.

### Command-Line Interface

```bash
# Run in CLI-only mode (no GUI, outputs tasks to stdout)
taskify --no-gui --duration 60

# Process an existing audio file
taskify process-file path/to/recording.wav

# Export tasks to Markdown
taskify export --format markdown --output tasks.md

# Show current configuration
taskify config show
```

---

## Configuration

Copy the default configuration to your user config directory:

```bash
python -m taskify config init
```

This creates `~/.config/taskify/config.toml`. All available options with their defaults:

```toml
[audio]
device = "default"          # Input device name or index
sample_rate = 16000         # Hz — Vosk and Whisper expect 16000
chunk_duration_ms = 200     # Audio chunk size fed to STT
silence_threshold = 0.01    # RMS energy threshold for silence detection
silence_duration_s = 1.5    # Seconds of silence before pausing capture

[stt]
engine = "vosk"             # "vosk" or "whisper"
vosk_model = "en-small"     # Vosk model identifier
whisper_model = "base"      # Whisper model size: tiny, base, small
language = "en"             # BCP-47 language code

[llm]
backend = "ollama"          # "ollama" or "nlp"
ollama_host = "http://localhost:11434"
ollama_model = "phi4-mini"
extraction_interval_s = 300 # Seconds between automatic extraction runs

[storage]
data_dir = ""               # Defaults to ~/.local/share/taskify
log_dir = ""                # Defaults to data_dir/logs

[logging]
level = "INFO"              # DEBUG, INFO, WARNING, ERROR
debug_llm = false           # Log full prompts and responses (verbose)
```

---

## Architecture Overview

```
taskify/
  audio/          Audio capture, silence detection, chunk queue
  stt/            STT engine abstraction, Vosk backend, Whisper backend
  llm/            LLM abstraction, Ollama backend, NLP/rule-based backend
  pipeline/       Scheduler, segment processor, event bus
  storage/        DatabaseManager, transcript writer, migration runner
  export/         Markdown and JSON exporters
  ui/             Main window, matrix dashboard, settings dialog, widgets
  config/         Settings loader and validator
  cli/            Click-based CLI entry points
```

The core modules (`audio`, `stt`, `llm`, `pipeline`, `storage`) are intentionally free of any GUI
dependency, enabling future headless and mobile deployments.

**Data flow:**

```
Microphone -> AudioCapture (sounddevice)
           -> STT Engine (Vosk / Whisper)  [daemon thread]
           -> TranscriptSegment queue
           -> TranscriptWriter             [background thread]
           -> SQLite + daily log files
           -> Scheduler (every N minutes)
           -> LLM / NLP Backend
           -> TaskItem list
           -> DatabaseManager
           -> EventBus -> UI refresh
```

---

## Contributing

Contributions are welcome. Please read `CONTRIBUTING.md` before opening a pull request.

**Development setup:**

```bash
pip install -e ".[dev]"
pre-commit install
```

**Running tests:**

```bash
pytest --cov=src/taskify --cov-report=term-missing
```

**Linting and type checking:**

```bash
ruff check src/ tests/
mypy src/
```

**Commit style:** Conventional Commits (`feat:`, `fix:`, `docs:`, `test:`, `chore:`). No emojis
in commit messages, code comments, or documentation.

---

## Roadmap

See the [GitHub Issues](https://github.com/MrSpideyNihal/Taskify/issues) for the full backlog.
High-level milestones:

| Milestone | Target | Status |
|---|---|---|
| v0.1 — Core pipeline (audio, STT, storage) | TBD | In progress |
| v0.2 — LLM extraction and matrix dashboard | TBD | Planned |
| v0.3 — Settings, export, and packaging | TBD | Planned |
| v1.0 — Stable release with full documentation | TBD | Planned |
| v1.x — Android prototype via Chaquopy/Kivy | TBD | Research |

---

## License

MIT License. See [LICENSE](LICENSE) for full text.

Copyright (c) 2026 Nihal