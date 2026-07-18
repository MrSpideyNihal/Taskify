"""Modal settings dialog window for configuration management."""

from __future__ import annotations

import logging
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import TYPE_CHECKING

import customtkinter as ctk

from taskify.config import (
    AudioSettings,
    LLMSettings,
    LoggingSettings,
    Settings,
    StorageSettings,
    STTSettings,
    save_settings,
)

try:
    import sounddevice as sd
except Exception:
    sd = None

if TYPE_CHECKING:
    from taskify.ui.main_window import MainWindow

logger = logging.getLogger(__name__)

# Style constants to match MainWindow theme
BG_COLOR = "#121214"
CARD_BG = "#1A1A1E"
TEXT_PRIMARY = "#FFFFFF"
TEXT_SECONDARY = "#9999A1"
BORDER_COLOR = "#2D2D34"


class SettingsDialog(ctk.CTkToplevel):
    """Modal dialog for editing application-wide configurations."""

    def __init__(self, parent: MainWindow, settings: Settings) -> None:
        """Initialize modal settings window.

        Args:
            parent (MainWindow): Main application window.
            settings (Settings): Active settings reference.
        """
        super().__init__(parent)
        self.parent = parent
        self.settings = settings

        self.title("Configuration Settings")
        self.geometry("520x460")
        self.resizable(False, False)
        self.configure(fg_color=BG_COLOR)

        # Make it modal
        self.transient(parent)
        self.grab_set()
        self.focus_set()

        # Master grid layout
        self.grid_rowconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=0)
        self.grid_columnconfigure(0, weight=1)

        # Tabview for layout categorization
        self.tabview = ctk.CTkTabview(
            self,
            fg_color=CARD_BG,
            segmented_button_selected_color="#5F9FFF",
            segmented_button_selected_hover_color="#4F8FEE",
            segmented_button_unselected_color=BG_COLOR,
            text_color=TEXT_PRIMARY,
        )
        self.tabview.grid(row=0, column=0, padx=12, pady=12, sticky="nsew")

        self.tabview.add("Audio")
        self.tabview.add("Speech-to-Text")
        self.tabview.add("LLM Backend")
        self.tabview.add("Storage & Logs")

        # ----------------------------------------------------
        # Tab 1: Audio Configuration
        # ----------------------------------------------------
        audio_tab = self.tabview.tab("Audio")
        audio_tab.grid_columnconfigure(1, weight=1)

        # Device Selection
        ctk.CTkLabel(audio_tab, text="Input Device:", text_color=TEXT_SECONDARY).grid(
            row=0, column=0, padx=16, pady=8, sticky="w"
        )
        self.device_var = tk.StringVar(value=self.settings.audio.device)
        devices = self._get_input_devices()
        self.device_menu = ctk.CTkOptionMenu(
            audio_tab,
            variable=self.device_var,
            values=devices,
            width=220,
        )
        self.device_menu.grid(row=0, column=1, padx=16, pady=8, sticky="w")

        # Sample Rate
        ctk.CTkLabel(
            audio_tab, text="Sample Rate (Hz):", text_color=TEXT_SECONDARY
        ).grid(row=1, column=0, padx=16, pady=8, sticky="w")
        self.sample_rate_var = tk.StringVar(value=str(self.settings.audio.sample_rate))
        self.sample_rate_entry = ctk.CTkEntry(
            audio_tab, textvariable=self.sample_rate_var, width=120
        )
        self.sample_rate_entry.grid(row=1, column=1, padx=16, pady=8, sticky="w")

        # Chunk Duration
        ctk.CTkLabel(
            audio_tab, text="Chunk Duration (ms):", text_color=TEXT_SECONDARY
        ).grid(row=2, column=0, padx=16, pady=8, sticky="w")
        self.chunk_duration_var = tk.StringVar(
            value=str(self.settings.audio.chunk_duration_ms)
        )
        self.chunk_duration_entry = ctk.CTkEntry(
            audio_tab, textvariable=self.chunk_duration_var, width=120
        )
        self.chunk_duration_entry.grid(row=2, column=1, padx=16, pady=8, sticky="w")

        # Silence Threshold
        ctk.CTkLabel(
            audio_tab, text="Silence Threshold:", text_color=TEXT_SECONDARY
        ).grid(row=3, column=0, padx=16, pady=8, sticky="w")
        self.silence_threshold_var = tk.StringVar(
            value=str(self.settings.audio.silence_threshold)
        )
        self.silence_threshold_entry = ctk.CTkEntry(
            audio_tab, textvariable=self.silence_threshold_var, width=120
        )
        self.silence_threshold_entry.grid(row=3, column=1, padx=16, pady=8, sticky="w")

        # Silence Duration
        ctk.CTkLabel(
            audio_tab, text="Silence Duration (s):", text_color=TEXT_SECONDARY
        ).grid(row=4, column=0, padx=16, pady=8, sticky="w")
        self.silence_duration_var = tk.StringVar(
            value=str(self.settings.audio.silence_duration_s)
        )
        self.silence_duration_entry = ctk.CTkEntry(
            audio_tab, textvariable=self.silence_duration_var, width=120
        )
        self.silence_duration_entry.grid(row=4, column=1, padx=16, pady=8, sticky="w")

        # ----------------------------------------------------
        # Tab 2: Speech-to-Text Settings
        # ----------------------------------------------------
        stt_tab = self.tabview.tab("Speech-to-Text")
        stt_tab.grid_columnconfigure(1, weight=1)

        # STT Engine
        ctk.CTkLabel(stt_tab, text="STT Engine:", text_color=TEXT_SECONDARY).grid(
            row=0, column=0, padx=16, pady=8, sticky="w"
        )
        self.stt_engine_var = tk.StringVar(value=self.settings.stt.engine)
        self.stt_engine_menu = ctk.CTkOptionMenu(
            stt_tab,
            variable=self.stt_engine_var,
            values=["vosk", "whisper"],
            command=self._on_stt_engine_changed,
            width=160,
        )
        self.stt_engine_menu.grid(row=0, column=1, padx=16, pady=8, sticky="w")

        # Vosk Model Name
        self.vosk_lbl = ctk.CTkLabel(
            stt_tab, text="Vosk Model:", text_color=TEXT_SECONDARY
        )
        self.vosk_lbl.grid(row=1, column=0, padx=16, pady=8, sticky="w")
        self.vosk_model_var = tk.StringVar(value=self.settings.stt.vosk_model)
        self.vosk_model_combo = ctk.CTkComboBox(
            stt_tab,
            variable=self.vosk_model_var,
            values=["en-small", "en-large", "de-small", "fr-small", "es-small"],
            width=180,
        )
        self.vosk_model_combo.grid(row=1, column=1, padx=16, pady=8, sticky="w")

        # Whisper Model Size
        self.whisper_lbl = ctk.CTkLabel(
            stt_tab, text="Whisper Model:", text_color=TEXT_SECONDARY
        )
        self.whisper_lbl.grid(row=2, column=0, padx=16, pady=8, sticky="w")
        self.whisper_model_var = tk.StringVar(value=self.settings.stt.whisper_model)
        self.whisper_model_combo = ctk.CTkComboBox(
            stt_tab,
            variable=self.whisper_model_var,
            values=["tiny", "base", "small", "medium", "large"],
            width=180,
        )
        self.whisper_model_combo.grid(row=2, column=1, padx=16, pady=8, sticky="w")

        # Language
        ctk.CTkLabel(stt_tab, text="Language Code:", text_color=TEXT_SECONDARY).grid(
            row=3, column=0, padx=16, pady=8, sticky="w"
        )
        self.language_var = tk.StringVar(value=self.settings.stt.language)
        self.language_entry = ctk.CTkEntry(
            stt_tab, textvariable=self.language_var, width=80
        )
        self.language_entry.grid(row=3, column=1, padx=16, pady=8, sticky="w")

        # Initialize visibility based on setting
        self._on_stt_engine_changed(self.settings.stt.engine)

        # ----------------------------------------------------
        # Tab 3: LLM / Pipeline Configuration
        # ----------------------------------------------------
        llm_tab = self.tabview.tab("LLM Backend")
        llm_tab.grid_columnconfigure(1, weight=1)

        # LLM Backend Selection
        ctk.CTkLabel(
            llm_tab, text="Extraction Backend:", text_color=TEXT_SECONDARY
        ).grid(row=0, column=0, padx=16, pady=8, sticky="w")
        self.llm_backend_var = tk.StringVar(value=self.settings.llm.backend)
        self.llm_backend_menu = ctk.CTkOptionMenu(
            llm_tab,
            variable=self.llm_backend_var,
            values=["ollama", "nlp"],
            command=self._on_llm_backend_changed,
            width=160,
        )
        self.llm_backend_menu.grid(row=0, column=1, padx=16, pady=8, sticky="w")

        # Ollama Host
        self.ollama_host_lbl = ctk.CTkLabel(
            llm_tab, text="Ollama Host URL:", text_color=TEXT_SECONDARY
        )
        self.ollama_host_lbl.grid(row=1, column=0, padx=16, pady=8, sticky="w")
        self.ollama_host_var = tk.StringVar(value=self.settings.llm.ollama_host)
        self.ollama_host_entry = ctk.CTkEntry(
            llm_tab, textvariable=self.ollama_host_var, width=220
        )
        self.ollama_host_entry.grid(row=1, column=1, padx=16, pady=8, sticky="w")

        # Ollama Model Name
        self.ollama_model_lbl = ctk.CTkLabel(
            llm_tab, text="Ollama Model:", text_color=TEXT_SECONDARY
        )
        self.ollama_model_lbl.grid(row=2, column=0, padx=16, pady=8, sticky="w")
        self.ollama_model_var = tk.StringVar(value=self.settings.llm.ollama_model)
        self.ollama_model_entry = ctk.CTkEntry(
            llm_tab, textvariable=self.ollama_model_var, width=180
        )
        self.ollama_model_entry.grid(row=2, column=1, padx=16, pady=8, sticky="w")

        # Sync/Extraction Interval
        ctk.CTkLabel(
            llm_tab, text="Extraction Interval (s):", text_color=TEXT_SECONDARY
        ).grid(row=3, column=0, padx=16, pady=8, sticky="w")
        self.interval_var = tk.StringVar(
            value=str(self.settings.llm.extraction_interval_s)
        )
        self.interval_entry = ctk.CTkEntry(
            llm_tab, textvariable=self.interval_var, width=100
        )
        self.interval_entry.grid(row=3, column=1, padx=16, pady=8, sticky="w")

        # Initialize LLM fields visibility
        self._on_llm_backend_changed(self.settings.llm.backend)

        # ----------------------------------------------------
        # Tab 4: Storage & Logs
        # ----------------------------------------------------
        storage_tab = self.tabview.tab("Storage & Logs")
        storage_tab.grid_columnconfigure(1, weight=1)

        # Data Dir Directory
        ctk.CTkLabel(
            storage_tab, text="Data Directory:", text_color=TEXT_SECONDARY
        ).grid(row=0, column=0, padx=16, pady=8, sticky="w")
        self.data_dir_var = tk.StringVar(value=str(self.settings.storage.data_dir))
        data_frame = ctk.CTkFrame(storage_tab, fg_color="transparent")
        data_frame.grid(row=0, column=1, padx=16, pady=8, sticky="ew")
        data_frame.grid_columnconfigure(0, weight=1)

        self.data_dir_entry = ctk.CTkEntry(
            data_frame, textvariable=self.data_dir_var, state="normal"
        )
        self.data_dir_entry.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ctk.CTkButton(
            data_frame,
            text="Browse...",
            width=80,
            command=self._browse_data_dir,
        ).grid(row=0, column=1, sticky="e")

        # Log Dir Directory
        ctk.CTkLabel(
            storage_tab, text="Log Directory:", text_color=TEXT_SECONDARY
        ).grid(row=1, column=0, padx=16, pady=8, sticky="w")
        self.log_dir_var = tk.StringVar(value=str(self.settings.storage.log_dir))
        log_frame = ctk.CTkFrame(storage_tab, fg_color="transparent")
        log_frame.grid(row=1, column=1, padx=16, pady=8, sticky="ew")
        log_frame.grid_columnconfigure(0, weight=1)

        self.log_dir_entry = ctk.CTkEntry(
            log_frame, textvariable=self.log_dir_var, state="normal"
        )
        self.log_dir_entry.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ctk.CTkButton(
            log_frame,
            text="Browse...",
            width=80,
            command=self._browse_log_dir,
        ).grid(row=0, column=1, sticky="e")

        # Log Level
        ctk.CTkLabel(storage_tab, text="Log Level:", text_color=TEXT_SECONDARY).grid(
            row=2, column=0, padx=16, pady=8, sticky="w"
        )
        self.log_level_var = tk.StringVar(value=self.settings.logging.level)
        self.log_level_menu = ctk.CTkOptionMenu(
            storage_tab,
            variable=self.log_level_var,
            values=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
            width=120,
        )
        self.log_level_menu.grid(row=2, column=1, padx=16, pady=8, sticky="w")

        # Debug LLM Checkbox
        self.debug_llm_var = tk.BooleanVar(value=self.settings.logging.debug_llm)
        self.debug_llm_check = ctk.CTkCheckBox(
            storage_tab,
            text="Enable LLM Diagnostics Logging",
            variable=self.debug_llm_var,
            text_color=TEXT_SECONDARY,
        )
        self.debug_llm_check.grid(
            row=3, column=0, columnspan=2, padx=16, pady=12, sticky="w"
        )

        # ----------------------------------------------------
        # Action Buttons (Save/Cancel) at the bottom
        # ----------------------------------------------------
        actions_frame = ctk.CTkFrame(self, fg_color="transparent")
        actions_frame.grid(row=1, column=0, padx=16, pady=(0, 16), sticky="ew")
        actions_frame.grid_columnconfigure(0, weight=1)

        self.cancel_btn = ctk.CTkButton(
            actions_frame,
            text="Cancel",
            fg_color="#3A3A3C",
            hover_color="#48484A",
            text_color=TEXT_PRIMARY,
            width=90,
            command=self.destroy,
        )
        self.cancel_btn.pack(side="right", padx=(8, 0))

        self.save_btn = ctk.CTkButton(
            actions_frame,
            text="Save Settings",
            fg_color="#5F9FFF",
            hover_color="#4F8FEE",
            text_color="#FFFFFF",
            width=110,
            command=self.save,
        )
        self.save_btn.pack(side="right")

    def _get_input_devices(self) -> list[str]:
        """Fetch all input-enabled devices from system sound interfaces."""
        devs = []
        if sd is not None:
            try:
                all_devs = sd.query_devices()
                for d in all_devs:
                    if d.get("max_input_channels", 0) > 0:
                        devs.append(d.get("name"))
            except Exception:
                pass
        unique_devs = list(dict.fromkeys(devs))
        if not unique_devs:
            unique_devs.append("default")
        return unique_devs

    def _on_stt_engine_changed(self, choice: str) -> None:
        """Toggle model input visibility dependent on chosen STT engine."""
        if choice == "vosk":
            self.vosk_lbl.grid()
            self.vosk_model_combo.grid()
            self.whisper_lbl.grid_remove()
            self.whisper_model_combo.grid_remove()
        else:
            self.vosk_lbl.grid_remove()
            self.vosk_model_combo.grid_remove()
            self.whisper_lbl.grid()
            self.whisper_model_combo.grid()

    def _on_llm_backend_changed(self, choice: str) -> None:
        """Toggle Ollama parameter widgets visibility based on backend choice."""
        if choice == "ollama":
            self.ollama_host_lbl.grid()
            self.ollama_host_entry.grid()
            self.ollama_model_lbl.grid()
            self.ollama_model_entry.grid()
        else:
            self.ollama_host_lbl.grid_remove()
            self.ollama_host_entry.grid_remove()
            self.ollama_model_lbl.grid_remove()
            self.ollama_model_entry.grid_remove()

    def _browse_data_dir(self) -> None:
        """Open directory picker modal for database data path."""
        chosen = filedialog.askdirectory(initialdir=self.data_dir_var.get())
        if chosen:
            self.data_dir_var.set(chosen)

    def _browse_log_dir(self) -> None:
        """Open directory picker modal for log folder location."""
        chosen = filedialog.askdirectory(initialdir=self.log_dir_var.get())
        if chosen:
            self.log_dir_var.set(chosen)

    def save(self) -> None:
        """Validate dialog fields, serialize to config.toml, and notify parent."""
        try:
            # 1. Parse and validate audio configs
            try:
                sample_rate = int(self.sample_rate_var.get())
                chunk_duration = int(self.chunk_duration_var.get())
                silence_threshold = float(self.silence_threshold_var.get())
                silence_duration = float(self.silence_duration_var.get())
            except ValueError as ve:
                raise ValueError(
                    f"Invalid format in Audio numeric values: {ve}"
                ) from ve

            audio_settings = AudioSettings(
                device=self.device_var.get(),
                sample_rate=sample_rate,
                chunk_duration_ms=chunk_duration,
                silence_threshold=silence_threshold,
                silence_duration_s=silence_duration,
            )
            audio_settings.validate()

            # 2. Parse and validate STT configs
            stt_engine = self.stt_engine_var.get()
            stt_settings = STTSettings(
                engine=stt_engine,
                vosk_model=self.vosk_model_var.get(),
                whisper_model=self.whisper_model_var.get(),
                language=self.language_var.get(),
            )
            stt_settings.validate()

            # Engine dependency validation
            if stt_engine == "whisper":
                try:
                    import faster_whisper  # noqa: F401
                except ImportError as ie:
                    raise ValueError(
                        "Whisper engine selected but 'faster-whisper' "
                        "is not installed. Please run: "
                        'pip install "taskify[whisper]"'
                    ) from ie

                valid_whisper_models = {
                    "tiny", "tiny.en", "base", "base.en", "small", "small.en",
                    "medium", "medium.en", "large-v1", "large-v2", "large-v3", "large"
                }
                w_val = stt_settings.whisper_model
                if w_val not in valid_whisper_models:
                    model_path = Path(w_val)
                    if not model_path.exists():
                        raise ValueError(
                            f"Whisper model size '{w_val}' is invalid, "
                            "and no such local model folder exists."
                        )
            else:
                try:
                    import vosk  # noqa: F401
                except ImportError as ie:
                    raise ValueError(
                        "Vosk engine selected but 'vosk' package is not installed."
                    ) from ie

                # Check if selected Vosk model downloaded locally
                from taskify.stt.vosk_engine import VoskEngine
                temp_s = Settings(
                    audio=audio_settings,
                    stt=stt_settings,
                    llm=self.settings.llm,
                    storage=self.settings.storage,
                    logging=self.settings.logging,
                )
                v_engine = VoskEngine(temp_s)
                model_dir = v_engine.model_path
                if not model_dir.exists() or not model_dir.is_dir():
                    raise ValueError(
                        f"Vosk model '{stt_settings.vosk_model}' not found "
                        f"locally at:\n{model_dir}\n"
                        f"Please download it first using CLI command:\n"
                        f"taskify download-model --engine vosk --model "
                        f"{stt_settings.vosk_model}"
                    )

            # 3. Parse and validate LLM configs
            try:
                interval = int(self.interval_var.get())
            except ValueError as ve:
                raise ValueError(
                    "Extraction interval must be an integer."
                ) from ve

            llm_settings = LLMSettings(
                backend=self.llm_backend_var.get(),
                ollama_host=self.ollama_host_var.get(),
                ollama_model=self.ollama_model_var.get(),
                extraction_interval_s=interval,
            )
            llm_settings.validate()

            # 4. Parse and validate Storage configs
            storage_settings = StorageSettings(
                data_dir=Path(self.data_dir_var.get()),
                log_dir=Path(self.log_dir_var.get()),
            )
            storage_settings.validate()

            # 5. Parse and validate Logging configs
            logging_settings = LoggingSettings(
                level=self.log_level_var.get(),
                debug_llm=self.debug_llm_var.get(),
            )
            logging_settings.validate()

            # Apply settings to the config reference
            self.settings.audio = audio_settings
            self.settings.stt = stt_settings
            self.settings.llm = llm_settings
            self.settings.storage = storage_settings
            self.settings.logging = logging_settings

            # Save to disk
            save_settings(self.settings)

            # Notify parent window
            self.parent.apply_settings()

            # Success message and close
            logger.info("Successfully updated configuration parameters.")
            self.destroy()

        except Exception as e:
            logger.warning("Configuration validation failed: %s", e)
            messagebox.showerror(
                title="Configuration Error",
                message=str(e),
                parent=self,
            )
