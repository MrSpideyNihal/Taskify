# Taskify User Guide

Welcome to **Taskify**, a fully offline, privacy-first, voice-driven task manager. Taskify processes your spoken conversations locally to extract and organize tasks into the **Eisenhower Matrix** quadrants.

---

## 1. Quick Start

1. **Launch the Application**: Run `taskify` from your terminal or double-click the `taskify.exe` binary.
2. **First-Run STT Model Setup**:
   - On the first startup, Taskify will check for local Speech-to-Text (STT) models.
   - If missing, download a lightweight model by clicking the prompt or running:
     ```bash
     taskify download-model vosk en-small
     ```
3. **Record a Session**:
   - Click the green **Record** button in the control panel.
   - Speak naturally: *"I must email the project proposal to Alice by end of day today."*
   - Click the red **Stop** button when finished.
4. **View Extracted Tasks**:
   - The background scheduler runs every 5 minutes (default) to process new transcript segments.
   - Within seconds of processing, your task will automatically appear in the **Do First** matrix quadrant!

---

## 2. Interface Layout

The interface is divided into three key layout panels:

```
+-----------------------------------------------------------+
| [Control Panel] Record Button | Timer | Level | Preview    |
+-----------------------------+-----------------------------+
| DO FIRST (Urgent+Important) | SCHEDULE (Important+Not)    |
| - Email Alice today         | - Plan roadmap next week    |
|                             |                             |
+-----------------------------+-----------------------------+
| DELEGATE (Urgent+Not)       | ELIMINATE (Neither)         |
| - Have John fix website     | - Maybe read comic later    |
|                             |                             |
+-----------------------------+-----------------------------+
```

### Control Panel
- **Record/Stop Action Button**: Toggles voice capture.
- **Session Duration Timer**: Tracks real-time elapsed recording duration (`MM:SS`).
- **Audio Level Meter**: Visualizes microphone input volume amplitude (energy).
- **Live Transcript Preview**: Displays the last 500 characters of local speech recognition text.

### Eisenhower Matrix Dashboard
- **Do First (Urgent & Important)**: Immediate tasks requiring focus today.
- **Schedule (Important & Not Urgent)**: Strategic objectives, planning, or future deadlines.
- **Delegate (Urgent & Not Important)**: Action items that should be assigned to others.
- **Eliminate (Not Urgent & Not Important)**: Low-priority items, distractions, or "nice to haves".

### Settings Modal
Access the Settings gear icon to configure:
- **Audio Input Device**: Selects target microphone hardware.
- **STT Engine**: Choose between **Vosk** (fast, CPU-light) and **Whisper** (high accuracy, resource-heavy).
- **LLM Backend**: Choose **Ollama** (offline local LLM) or **NLP Fallback** (fast regex rules).
- **Extraction Interval**: Slider controlling how frequently the background task extractor runs.

---

## 3. Editing Tasks & Overrides

Clicking any task card opens the **Task Detail Panel**:
- **Title & Notes**: Inline editing of task summaries and descriptions.
- **Due Date Picker**: Modify deadlines.
- **Quadrant Dropdown**: Manually override task category.
- **Auto-Save**: Changes save automatically on field blur (focus loss).
- **Manual Overrides**: Changing a quadrant manually flags the task as `user_override = 1`. The local LLM/NLP parser will never overwrite your manual categorizations on subsequent sync runs.

---

## 4. Keyboard Shortcuts

Boost your productivity with the following app keyboard shortcuts:

| Shortcut | Description | Scope |
|---|---|---|
| `Spacebar` | Toggle voice capture recording | Global Application |
| `Escape` | Close Settings Dialog or Task Detail Panel | Window Overlay |
| `Enter` | Save edits / confirm | Text Entries |
