# Offline STT Model Download Guide

Taskify is a **privacy-first application** that runs all speech-to-text (STT) models locally on your system. No audio data or transcriptions are ever sent online.

---

## 1. Storage Directories

Local model files are stored in the following platform-specific application directories:

| OS | Default Download Directory |
|---|---|
| **Windows** | `C:\Users\<Username>\.local\share\taskify\models\` |
| **macOS** | `/Users/<Username>/.local/share/taskify/models/` |
| **Linux** | `/home/<Username>/.local/share/taskify/models/` |

---

## 2. Vosk Models Setup

### Automatic Download
If you are connected to the internet, run the CLI utility to download and extract automatically:
```bash
# Download the default small english model
taskify download-model vosk en-small
```

### Manual Offline Setup (Air-gapped)
If you are setting up Taskify on an offline machine, follow these steps:
1. **Download the model ZIP** from the official Vosk repository:
   - **en-small** (Lightweight, default): [vosk-model-small-en-us-0.15.zip](https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip) (Approx. 40 MB)
   - **en-large** (High accuracy): [vosk-model-en-us-0.22-lgraph.zip](https://alphacephei.com/vosk/models/vosk-model-en-us-0.22-lgraph.zip) (Approx. 120 MB)
2. **Extract the ZIP file** into your local Taskify model directory:
   - Path for `en-small`: `.../taskify/models/vosk/vosk-model-small-en-us-0.15/`
3. **Verify directory structure**:
   - Ensure the directory contains database folders like `am/`, `graph/`, and description files such as `README`.

---

## 3. Whisper Models Setup

### Automatic Download
To automatically download standard HuggingFace quantized model parameters via `faster-whisper`:
```bash
# Downloads and registers the "base" model
taskify download-model whisper base
```
Supported configurations: `tiny`, `base`, `small`.

### Manual Offline Setup (Air-gapped)
Huggingface Whisper weights are resolved via the `huggingface_hub` caching mechanism:
1. On an online machine, download the model files using python:
   ```python
   from faster_whisper import WhisperModel
   model = WhisperModel("base", device="cpu", compute_type="int8")
   ```
2. Copy the cached Hugging Face hub folders from your online machine to the offline machine:
   - Cache Directory (default): `~/.cache/huggingface/hub/`
3. Ensure the target directory layout is replicated exactly. Taskify will automatically detect the cache on start.
