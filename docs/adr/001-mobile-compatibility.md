# ADR 001 — Mobile Compatibility Strategy (Android via Chaquopy / Kivy)

| Field | Value |
|-------|-------|
| **Status** | Accepted |
| **Date** | 2026-07-18 |
| **Deciders** | Nihal Rodge |
| **Issue** | [#21 — Refactor core pipeline to support Android deployment](https://github.com/MrSpideyNihal/Taskify/issues/21) |

---

## Context

Taskify's desktop implementation depends on several packages that are not available or
appropriate on Android:

| Package | Reason for desktop-only classification |
|---------|---------------------------------------|
| `sounddevice` | Wraps PortAudio — not available on Android |
| `soundfile` | Wraps libsndfile — not packaged for Android |
| `vosk` (PyPI wheel) | Desktop CPython wheel; Android uses the Vosk Android AAR |
| `customtkinter` | Wraps Tkinter/Tk — not available on Android |
| `httpx` | Used only for Ollama LLM backend (network calls) — not needed in mobile-only NLP mode |

The goal is to allow the pure-Python pipeline logic (scheduler, storage, NLP/rule-based
extraction, export) to be installed and used on Android without pulling in any of the
above packages.

---

## Decision

### 1. `core_mobile` extras group in `pyproject.toml`

A new optional-dependency group `core_mobile` is introduced:

```toml
[project.optional-dependencies]
core_mobile = [
    "numpy>=1.24.0",   # Used by audio DSP helpers and NLP numeric ops
    "click>=8.1.0",    # CLI entry-point (headless / shell usage)
]
```

Installing with:
```bash
pip install taskify[core_mobile]
```
…pulls **only** `numpy` and `click` alongside the pure-Python core, without
`sounddevice`, `soundfile`, `vosk`, `customtkinter`, or `httpx`.

### 2. Dependency boundaries per subsystem

```
taskify/
├── audio/          # DESKTOP ONLY — wraps sounddevice / soundfile
│                     Android replacement: AudioRecord via Chaquopy Java bridge
├── stt/
│   ├── vosk_engine.py    # DESKTOP ONLY — PyPI vosk wheel
│   ├── whisper_engine.py # DESKTOP ONLY — faster-whisper
│   └── base.py           # MOBILE SAFE — abstract STTEngine interface
│                           Android target: Vosk Android AAR via Chaquopy JNI
├── llm/
│   ├── ollama_backend.py # DESKTOP ONLY — requires httpx + running Ollama daemon
│   ├── nlp_backend.py    # MOBILE SAFE — pure spaCy / rule-based, no network
│   └── base.py           # MOBILE SAFE — abstract LLMBackend interface
├── pipeline/       # MOBILE SAFE — scheduler is platform-agnostic threading
├── storage/        # MOBILE SAFE — sqlite3 is built into CPython/Chaquopy
├── export/         # MOBILE SAFE — file I/O only
├── config/         # MOBILE SAFE — TOML parsing, stdlib only
├── ui/             # DESKTOP ONLY — CustomTkinter / Tkinter
│                     Android replacement: Kivy layout or native Android XML
└── cli/            # MOBILE SAFE — Click commands work headlessly
```

### 3. Recommended mobile STT target

Use the [Vosk Android AAR](https://alphacephei.com/vosk/android) via Chaquopy's Java
interop bridge. The existing `STTEngine` abstract base class in `stt/base.py` already
defines the interface; a `VoskAndroidEngine` adapter should:

1. Accept audio bytes from `AudioRecord` via Chaquopy.
2. Call `model.recognize(bytes)` through the AAR JNI bridge.
3. Return a `TranscriptSegment` — identical to the desktop flow.

### 4. Recommended mobile LLM/NLP target

Use **rule-based NLP only** (`nlp_backend.py`). The spaCy model (`en_core_web_sm`) must
be bundled as a `.whl` asset inside the APK via Chaquopy's `requirements`. Ollama
backend is excluded — no outbound network calls are permitted under the privacy policy.

### 5. GUI strategy

Two viable paths:

| Option | Trade-offs |
|--------|-----------|
| **Kivy** | Pure-Python, cross-platform, mature widget set. Requires porting UI from CustomTkinter. |
| **Native Android XML + Chaquopy** | Native look and feel, better performance. Requires Java/Kotlin UI layer calling Python pipeline via Chaquopy. Recommended for production. |

---

## Consequences

### Positive
- `pip install taskify[core_mobile]` works without any native audio or GUI libraries.
- The abstract `STTEngine` and `LLMBackend` interfaces mean no core pipeline changes
  are needed to swap in Android-native implementations.
- `storage/`, `pipeline/`, and `export/` are already fully mobile-safe.

### Negative / Risks
- Vosk Android AAR bridge requires Chaquopy in the Android build; this is a one-time
  setup cost but is well-documented.
- spaCy `en_core_web_sm` is ~12 MB; bundling it in the APK increases app size.
- A `VoskAndroidEngine` adapter class must be written and tested on-device.

### Deferred
- The actual Kivy or native Android UI implementation.
- The `VoskAndroidEngine` adapter class.
- Play Store packaging and signing.

---

## Compliance Check

```
pip install taskify[core_mobile]   # numpy, click only — no desktop packages
pip install taskify[nlp]           # adds spaCy for NLP extraction
pip install taskify[whisper]       # adds faster-whisper (desktop only)
pip install taskify[dev]           # full development toolchain
pip install taskify                # full desktop install
```

The `core_mobile` extras group satisfies the acceptance criterion:
> *`pip install taskify[core_mobile]` installs without any desktop-only packages.*

---

## References

- [Vosk Android AAR documentation](https://alphacephei.com/vosk/android)
- [Chaquopy — Python for Android](https://chaquo.com/chaquopy/)
- [Kivy cross-platform framework](https://kivy.org/)
- [ADR format — Michael Nygard](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions)
