"""Microphone audio capture module with RMS-based silence detection."""

import collections
import queue
import sys
from typing import Any

import numpy as np
import sounddevice as sd

from taskify.config import Settings


class AudioCapture:
    """Handles cross-platform audio stream capture and real-time silence filtering."""

    def __init__(self, settings: Settings) -> None:
        """Initialize audio capture settings.

        Args:
            settings (Settings): Application configurations.
        """
        self._device_name = settings.audio.device
        self._sample_rate = settings.audio.sample_rate
        self._chunk_duration_ms = settings.audio.chunk_duration_ms
        self._silence_threshold = settings.audio.silence_threshold
        self._silence_duration_s = settings.audio.silence_duration_s

        # Calculate chunk dimensions
        self._blocksize = int(self._sample_rate * self._chunk_duration_ms / 1000)

        # State machine configurations
        # 0 = SILENT, 1 = ACTIVE
        self._state = 0
        self._silence_counter = 0
        self._silence_limit = int(
            self._silence_duration_s * 1000 / self._chunk_duration_ms
        )

        # 0.6 seconds of history to prevent clipping initial syllables
        # (0.6s / 0.2s = 3 chunks)
        self._preroll_maxlen = max(1, int(600 / self._chunk_duration_ms))
        self._preroll_buffer: collections.deque[np.ndarray] = collections.deque(
            maxlen=self._preroll_maxlen
        )

        # Thread-safe queue containing only ACTIVE audio chunks
        self._queue: queue.Queue[np.ndarray] = queue.Queue()
        self._stream: sd.InputStream | None = None
        self._is_recording = False

    @property
    def is_recording(self) -> bool:
        """Check if audio input stream is active.

        Returns:
            bool: True if recording.
        """
        return self._is_recording

    @classmethod
    def get_available_devices(cls) -> list[dict[str, Any]]:
        """Query host hardware and list all available recording input devices.

        Returns:
            list[dict]: Available devices catalog.
        """
        devices = sd.query_devices()
        input_devices = []
        for idx, dev in enumerate(devices):
            if dev.get("max_input_channels", 0) > 0:
                input_devices.append(
                    {
                        "index": idx,
                        "name": str(dev.get("name", "Unknown")),
                        "max_input_channels": int(dev.get("max_input_channels", 0)),
                        "default_samplerate": float(
                            dev.get("default_samplerate", 16000.0)
                        ),
                    }
                )
        return input_devices

    def _resolve_device_index(self) -> Any:
        """Resolve device name/identifier to index string or None (default).

        Returns:
            Any: Resolved PortAudio device identifier.
        """
        if self._device_name == "default":
            return None

        try:
            return int(self._device_name)
        except ValueError:
            pass

        # Substring lookup
        devices = sd.query_devices()
        for idx, dev in enumerate(devices):
            if self._device_name in str(dev.get("name", "")):
                return idx

        # Fallback to default
        print(
            f"Warning: Audio device '{self._device_name}' not found. "
            "Falling back to default input.",
            file=sys.stderr,
        )
        return None

    def _audio_callback(
        self, indata: np.ndarray, frames: int, time_info: Any, status: Any
    ) -> None:
        """Process incoming audio buffers inside the PortAudio callback thread.

        Args:
            indata (np.ndarray): Input float32 matrix (frames, channels).
            frames (int): Buffer chunk size in frames.
            time_info (Any): PortAudio time statistics.
            status (Any): Callback warnings or errors.
        """
        # Exclude stereo, extract mono channel
        audio_data = indata[:, 0].copy()

        # Compute Root Mean Square (RMS) energy
        rms = np.sqrt(np.mean(audio_data**2)) if len(audio_data) > 0 else 0.0

        if self._state == 0:  # SILENT state
            if rms >= self._silence_threshold:
                # Transition to ACTIVE
                self._state = 1
                self._silence_counter = 0

                # Flush history pre-roll to downstream queue
                while self._preroll_buffer:
                    self._queue.put(self._preroll_buffer.popleft())
                self._queue.put(audio_data)
            else:
                # Retain sliding window history
                self._preroll_buffer.append(audio_data)
        else:  # ACTIVE state
            if rms < self._silence_threshold:
                self._silence_counter += 1
                if self._silence_counter >= self._silence_limit:
                    # Transition to SILENT
                    self._state = 0
                    self._silence_counter = 0
                    self._preroll_buffer.clear()
                    self._preroll_buffer.append(audio_data)
                else:
                    self._queue.put(audio_data)
            else:
                self._silence_counter = 0
                self._queue.put(audio_data)

    def start(self) -> None:
        """Open audio input stream and begin recording."""
        if self._is_recording:
            return

        device_index = self._resolve_device_index()

        self._state = 0
        self._silence_counter = 0
        self._preroll_buffer.clear()
        # Drain queue
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break

        try:
            self._stream = sd.InputStream(
                device=device_index,
                channels=1,
                samplerate=self._sample_rate,
                blocksize=self._blocksize,
                dtype="float32",
                callback=self._audio_callback,
            )
            self._stream.start()
            self._is_recording = True
        except Exception as e:
            self._is_recording = False
            self._stream = None
            raise RuntimeError(f"Failed to start audio input stream: {e}") from e

    def stop(self) -> None:
        """Close audio input stream and stop recording."""
        if not self._is_recording:
            return

        self._is_recording = False

        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None

    def get_chunk(self, timeout: float | None = None) -> np.ndarray | None:
        """Retrieve the next active audio chunk from queue.

        Args:
            timeout (float, optional): Block time in seconds.

        Returns:
            np.ndarray, optional: Mono float32 array or None if empty.
        """
        try:
            return self._queue.get(timeout=timeout)
        except queue.Empty:
            return None
